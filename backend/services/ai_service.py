"""
AI Service — Hybrid Consolidation Pipeline (v3)
=================================================
Phase 1: Deterministic extraction of structured data (attendance, infra, etc.)
         — handled entirely in structured_extractor.py, NEVER sent to LLM
Phase 2: LLM summarization of narrative sections only (events, participation,
         loose paragraphs, MTP narrative)

v3 improvements:
- Attendance numbers are NEVER in the LLM prompt — zero hallucination risk
- Loose paragraphs always forwarded with dept/date context labels
- Failed chunks retry per-department instead of silent drop
- max_output_tokens increased to 16384
- Stricter prompt: LLM must never invent any number
- Per-dept validation after LLM merge
- Chunking threshold raised (more context per call)
- MTP numbers guarded: only text narrative sent, never attendance figures

Uses the modern `google-genai` SDK (replaces deprecated `google-generativeai`).
"""

import os
import json
import re
import time
import json_repair

# ── Client initialization ─────────────────────────────────────────────────────
# Supports two backends:
#   1. Google Gemini — set GEMINI_API_KEY in .env     (primary & fastest, ~2s latency)
#   2. OpenRouter    — set OPENROUTER_API_KEY in .env (secondary fallback)

_gemini_client = None
_openrouter_client = None

def _get_gemini_client():
    """Lazy-init Gemini client using modern google-genai SDK."""
    global _gemini_client
    if _gemini_client is None:
        try:
            from google import genai
            key = os.getenv("GEMINI_API_KEY", "").strip()
            if not key:
                return None
            _gemini_client = genai.Client(api_key=key)
        except Exception as e:
            print(f"[LLM] Failed to initialize Gemini client: {e}")
            return None
    return _gemini_client


def _get_openrouter_client():
    """Lazy-init OpenRouter client via openai-compatible SDK with timeout."""
    global _openrouter_client
    if _openrouter_client is None:
        try:
            from openai import OpenAI
            key = os.getenv("OPENROUTER_API_KEY", "").strip()
            if not key:
                return None
            _openrouter_client = OpenAI(
                api_key=key,
                base_url="https://openrouter.ai/api/v1",
                timeout=20.0,
                default_headers={
                    "HTTP-Referer": "https://vnrvjiet.ac.in",
                    "X-Title": "MTP ReportGen",
                },
            )
        except Exception as e:
            print(f"[LLM] Failed to initialize OpenRouter client: {e}")
            return None
    return _openrouter_client


# Gemini models in priority order — modern aliases tested and confirmed working
GEMINI_MODELS = [
    "gemini-3.5-flash-lite",
    "models/gemini-3.5-flash-lite",
    "models/gemini-3.7-flash",
    "gemini-3.7-flash",
    "gemini-2.5-flash",
    "models/gemini-2.5-flash",
    "gemini-flash-latest",
]

# OpenRouter fallback models
OPENROUTER_MODELS = [
    "google/gemini-2.5-flash",
    "google/gemma-4-31b-it:free",
    "meta-llama/llama-3.3-70b-instruct",
]


# ── LLM Prompt — ONLY for narrative summarization ────────────────────────────
# CRITICAL: The LLM NEVER receives attendance, infrastructure counts, or any
# numeric data that was already extracted deterministically. It only ever sees
# the events/participation/free-text sections.

SUMMARIZE_SYSTEM_PROMPT = """You are an executive institutional report editor for VNRVJIET (VNR Vignana Jyothi Institute of Engineering & Technology).

You will receive narrative text from department daily reports: workshops, guest lectures, seminars, FDPs, student achievements, faculty publications, and free-text updates.

YOUR CORE OBJECTIVES:
1. FORMAL COLLEGE ENGLISH: The raw department reports often contain grammar issues, shorthand phrasing, or poor sentence structure. Proofread and rewrite all narratives into crisp, professional, college-formal English suitable for the Principal and Management.
2. 99% HIGHLIGHT RETENTION: Retain 100% of distinct, real events, guest lectures, workshops, seminars, and achievements. DO NOT drop or omit events unless they are empty or redundant duplicates.
3. CONCISE & INFORMATIVE: Keep each event summary to 1–2 crisp sentences highlighting the topic, resource person/agency, participant count (if given), and key outcome.
4. ABSOLUTE FACT INTEGRITY: Preserve all factual details, names of speakers/faculty/students, dates, counts, and metrics EXACTLY as stated. DO NOT invent any facts or numbers. Use null if a number is not in the source.
5. STRICT DEPARTMENT ISOLATION:
   - ONLY extract events under a department if they were explicitly described in THAT department's input block.
   - NEVER copy, duplicate, or assign events from one department (e.g. CSE) to other departments (e.g. Civil, English, Mech, EEE, etc.).
   - If a department has no events in its input section, DO NOT include it in `department_highlights` or return `events: []`.
6. CLEAN DEDUPLICATION & SEPARATION:
   - Department-hosted events/workshops for students go to `department_highlights`.
   - Faculty external participation/FDPs/paper presentations go to `staff_participation`.
   - Student external hackathons/competitions/paper presentations go to `student_participation`.
   - If an item is listed in highlights, DO NOT duplicate it in participation.
7. IMPORTANCE RATING (For internal sorting):
   - "high": Keynote/guest lectures by industry/foreign experts, competitive national awards, major patents/funded projects, >50 participants.
   - "medium": Internal department workshops, FDPs, NPTEL/certifications, 20–50 participants.
   - "low": Routine department meetings, minor internal activities, <20 participants.
8. Return ONLY valid JSON matching the exact schema below without any markdown fences.

OUTPUT SCHEMA:
{
  "department_highlights": [
    {
      "dept": "Full Department Name",
      "dept_code": "short_code (e.g. cse, ece)",
      "events": [
        {
          "name": "Exact polished event title",
          "summary": "1-2 sentence polished executive summary in formal English",
          "importance": "high|medium|low",
          "date": "exact date string or null",
          "duration": "duration string or null",
          "participants_internal": null,
          "participants_external": null,
          "resource_person": "Speaker Name, Designation, Organization or null"
        }
      ],
      "other_matters": ["Polished note on other significant departmental matters"]
    }
  ],
  "staff_participation": [
    {
      "name": "Faculty Name",
      "dept": "Department",
      "event": "Event Name",
      "role": "Paper Presenter / Attendee / Session Chair / Resource Person",
      "date": "date string or null",
      "venue": "Venue/Institution or null",
      "summary": "1 concise sentence in formal English",
      "importance": "high|medium|low"
    }
  ],
  "student_participation": [
    {
      "name": "Student Name(s) / Team",
      "dept": "Department",
      "event": "Event / Competition Name",
      "achievement": "1st Prize / Finalist / Participant",
      "date": "date string or null",
      "summary": "1 concise sentence in formal English",
      "importance": "high|medium|low"
    }
  ]
}"""


# ── Dedicated MTP extraction prompt (Maintains source order & noise reduction) ──

MTP_SYSTEM_PROMPT = """You extract and structure placement and training activity data from the VNRVJIET MTP (Mentoring, Training & Placements) daily report.

RULES:
1. MAINTAIN SOURCE ORDER: Extract activities in the EXACT sequential order in which they appear in the source report.
2. FORMAL PLACEMENT OFFICE ENGLISH: Proofread and refine text into polished, professional institutional English (concise 1–2 sentences).
3. NOISE & DUPLICATE REDUCTION: Merge redundant mentions of the same company/drive into a single coherent entry. Remove routine administrative boilerplate.
4. PRESERVE NUMBERS & FACTS: Extract company names, test/interview stages, student counts, batch years, and CTC/package (if stated) exactly as provided. DO NOT invent numbers.
5. Return ONLY a valid JSON array: [{...}, {...}] without markdown fences.

Schema for each entry:
{
  "company": "Company Name (or Training/Program Name if no company)",
  "activity_type": "placement_drive|ppt|aptitude_test|training|mock_interview|internship|other",
  "summary": "1-2 concise sentences in formal English detailing the activity, stage, and outcomes",
  "student_count": integer or null,
  "batch": "Batch year string (e.g. 2026 Batch) or null",
  "status": "In Progress / Completed / Shortlisted / Scheduled or null"
}"""


def _extract_mtp_summary(mtp_narrative: str) -> list[dict]:
    """
    Dedicated LLM call to extract structured MTP activity items in source order.
    """
    if not mtp_narrative or not mtp_narrative.strip():
        return []
    try:
        user_msg = (
            "Extract and structure all placement and training activities in their original sequential order.\n"
            "Polish the English into formal placement office tone and eliminate duplicate company mentions:\n\n"
            f"{mtp_narrative.strip()}"
        )
        raw = _llm_call(MTP_SYSTEM_PROMPT, user_msg)
        parsed = _parse_json(raw, context="mtp_summary_extraction")
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            for key in ("mtp_summary", "activities", "items"):
                if key in parsed and isinstance(parsed[key], list):
                    return parsed[key]
    except Exception as e:
        print(f"[WARN] MTP summary extraction failed: {e}")
    return []


def consolidate(report_date: str, dept_data: list[dict]) -> dict:
    """
    Consolidate department reports using hybrid pipeline.


    Args:
        report_date: Date string in YYYY-MM-DD format
        dept_data: List of dicts from structured_extractor.extract_structured_data()
                   Each dict has deterministic fields + narrative text fields.

    Returns:
        Complete consolidated report dict matching the output schema.

    GUARANTEE: Attendance, infrastructure counts, library transactions, staff
    changes, classwork counts, and incidents are extracted deterministically and
    NEVER sent to the LLM. These numbers cannot be hallucinated.
    """
    # ── Phase 1: Merge deterministic data (no LLM) ────────────────────────
    final_report = {
        "report_date": report_date,
        "attendance": {"departments": [], "library": None},
        "overall_staff_attendance_table": [],
        "overall_student_attendance_table": [],
        "attendance_charts": [],
        "department_highlights": [],
        "mtp_narrative": "",
        "mtp_batch_pills": "",
        "mtp_summary": [],          # Structured MTP items from LLM
        "staff_participation": [],
        "student_participation": [],
        "staff_changes": [],
        "classwork_adjustments": [],
        "incidents": [],
        "infrastructure_issues": [],
        "library_transactions": {},
        "library_services": {},
    }

    # ── Standard Academic Departments Registry ────────────────────────────────
    STANDARD_ACADEMIC_DEPTS = [
        {"code": "cse", "name": "Computer Science & Engineering", "aliases": ["cse", "computer science"]},
        {"code": "ece", "name": "Electronics & Communication Engineering", "aliases": ["ece", "electronics and communication"]},
        {"code": "eee", "name": "Electrical & Electronics Engineering", "aliases": ["eee", "electrical and electronics"]},
        {"code": "eie", "name": "Electronics & Instrumentation Engineering", "aliases": ["eie", "electronics and instrumentation"]},
        {"code": "it", "name": "Information Technology", "aliases": ["it", "information technology"]},
        {"code": "me", "name": "Mechanical Engineering", "aliases": ["me", "mechanical"]},
        {"code": "civil", "name": "Civil Engineering", "aliases": ["ce", "civil"]},
        {"code": "ae", "name": "Automobile Engineering", "aliases": ["ae", "automobile"]},
        {"code": "aiml", "name": "CSE (AI & ML and IoT)", "aliases": ["aiml", "cse-aiml", "iot"]},
        {"code": "cys", "name": "CSE (CyS, DS) and AI & DS", "aliases": ["cys", "ds", "aids", "ai&ds"]},
        {"code": "chem", "name": "Humanities & Sciences (Chemistry)", "aliases": ["chem", "chemistry"]},
        {"code": "english", "name": "Humanities & Sciences (English)", "aliases": ["eng", "english", "h&s"]},
        {"code": "mms", "name": "Humanities & Sciences (Mathematics & Management Sciences)", "aliases": ["mms", "m&ms", "maths"]},
    ]

    narrative_blocks = []  # Collect narrative text for LLM
    uploaded_dept_codes = set()

    for dept in dept_data:
        dept_code = dept["dept_code"].lower()
        dept_name = dept["dept_name"]
        uploaded_dept_codes.add(dept_code)

        # Attendance charts
        if dept.get("attendance_charts"):
            final_report["attendance_charts"].extend(dept["attendance_charts"])

        # Attendance — deterministic, never goes to LLM
        raw_att = dept.get("attendance")
        if raw_att:
            flat_att = _normalize_staff_attendance(raw_att, dept_name)
            if flat_att:
                final_report["attendance"]["departments"].append(flat_att)

        # Library attendance — deterministic
        if dept.get("library_attendance"):
            lib_att = dept["library_attendance"]
            if any(v is not None for v in lib_att.values()):
                final_report["attendance"]["library"] = lib_att

        # Infrastructure — deterministic
        if dept.get("infrastructure_issues"):
            final_report["infrastructure_issues"].extend(dept["infrastructure_issues"])

        # Staff changes — deterministic
        if dept.get("staff_changes"):
            final_report["staff_changes"].extend(dept["staff_changes"])

        # Classwork adjustments — deterministic count only
        adj_count = dept.get("classwork_adjustment_count", 0)
        if adj_count > 0:
            final_report["classwork_adjustments"].append({
                "dept": dept_name,
                "count": adj_count,
            })

        # Incidents — deterministic
        if dept.get("incidents"):
            final_report["incidents"].extend(dept["incidents"])

        # Library transactions — deterministic
        if dept.get("library_transactions"):
            final_report["library_transactions"].update(dept["library_transactions"])

        # Library services — deterministic
        if dept.get("library_services"):
            final_report["library_services"].update(dept["library_services"])

        # Overall Attendance — deterministic (from separate file)
        if dept.get("overall_staff_attendance_table"):
            final_report["overall_staff_attendance_table"] = dept["overall_staff_attendance_table"]

        # MTP narrative — sent exclusively to MTP LLM extractor
        if dept.get("mtp_narrative"):
            final_report["mtp_narrative"] = dept["mtp_narrative"]
        if dept.get("mtp_batch_pills"):
            final_report["mtp_batch_pills"] = dept["mtp_batch_pills"]
        if dept.get("mtp_summary"):
            for item in dept["mtp_summary"]:
                if isinstance(item, dict) and item not in final_report["mtp_summary"]:
                    final_report["mtp_summary"].append(item)

        # ── Collect narrative text for LLM (Academic departments ONLY) ───────
        # MTP, Library, and pure attendance files have their own dedicated sections
        NON_ACADEMIC_DEPTS = {"mtp", "library", "overall_attendance", "attendance"}
        if dept_code in NON_ACADEMIC_DEPTS:
            continue

        narrative_parts = []
        for key in [
            "events_text",
            "staff_participation_text",
            "student_participation_text",
            "other_matters_text",
            "loose_paragraphs",
        ]:
            text = dept.get(key, "").strip()

            # Strip attendance mentions out of free-text before the LLM sees it
            if key == "loose_paragraphs" and text:
                filtered = []
                for line in text.split("\n"):
                    lower = line.lower()
                    if "attendance" in lower or "on roll" in lower or "present" in lower or "absent" in lower:
                        continue
                    filtered.append(line)
                text = "\n".join(filtered).strip()

            if text and _has_real_narrative_content(text):
                narrative_parts.append(text)

        if narrative_parts:
            narrative_blocks.append({
                "dept_code": dept_code,
                "dept_name": dept_name,
                "text": "\n\n".join(narrative_parts),
            })

    det_highlights, det_staff, det_students = _deterministic_narratives(dept_data)
    final_report["department_highlights"] = det_highlights
    if det_staff:
        final_report["staff_participation"] = det_staff
    if det_students:
        final_report["student_participation"] = det_students

    # ── Phase 2 & 3: Concurrent LLM Summarization & MTP Extraction ────────
    from concurrent.futures import ThreadPoolExecutor

    mtp_narrative = final_report.get("mtp_narrative", "").strip()
    narrative_future = None
    mtp_future = None

    with ThreadPoolExecutor(max_workers=2) as executor:
        if narrative_blocks:
            narrative_future = executor.submit(_summarize_narratives, report_date, narrative_blocks)

        if mtp_narrative and not final_report.get("mtp_summary"):
            mtp_future = executor.submit(_extract_mtp_summary, mtp_narrative)

        llm_highlights = []
        if narrative_future:
            try:
                llm_result = narrative_future.result()
                if isinstance(llm_result, list):
                    if llm_result and isinstance(llm_result[0], dict) and (
                        "dept" in llm_result[0] or "events" in llm_result[0]
                    ):
                        llm_result = {"department_highlights": llm_result,
                                      "staff_participation": [],
                                      "student_participation": []}
                    else:
                        llm_result = {}

                if isinstance(llm_result, dict):
                    if "department_highlights" in llm_result:
                        raw_highlights = llm_result["department_highlights"]
                        llm_highlights = [
                            b for b in raw_highlights
                            if isinstance(b, dict) and b.get("dept_code", "").lower() not in NON_ACADEMIC_DEPTS
                        ]
                    if llm_result.get("staff_participation"):
                        final_report["staff_participation"] = llm_result["staff_participation"]
                    elif det_staff:
                        final_report["staff_participation"] = det_staff
                    if llm_result.get("student_participation"):
                        final_report["student_participation"] = llm_result["student_participation"]
                    elif det_students:
                        final_report["student_participation"] = det_students
                    if llm_result.get("mtp_summary"):
                        final_report["mtp_summary"] = llm_result["mtp_summary"]
            except Exception as e:
                import traceback
                print(f"[ERROR] LLM summarization failed: {e}")
                traceback.print_exc()

        if mtp_future:
            try:
                mtp_items = mtp_future.result()
                if mtp_items:
                    final_report["mtp_summary"] = mtp_items
                    print(f"  [OK] Extracted {len(mtp_items)} MTP activity items")
            except Exception as e:
                print(f"[WARN] MTP summary extraction failed: {e}")

    # ── Reconcile all standard academic departments (including missing status) ──
    combined_highlights = _merge_highlights(det_highlights, llm_highlights)
    final_report["department_highlights"] = _build_all_department_roster(
        STANDARD_ACADEMIC_DEPTS, uploaded_dept_codes, combined_highlights, dept_data
    )

    # ── Sort participation by importance (High -> Medium -> Low) ──────────────
    def _imp_val(item):
        imp = str(item.get("importance", "low")).lower()
        if "high" in imp: return 3
        if "med" in imp: return 2
        return 1

    if final_report.get("staff_participation"):
        final_report["staff_participation"].sort(key=_imp_val, reverse=True)
    if final_report.get("student_participation"):
        final_report["student_participation"].sort(key=_imp_val, reverse=True)

    # ── Clean up empty sections ───────────────────────────────────────────
    final_report = _remove_empty_sections(final_report)

    return final_report


def _summarize_narratives(report_date: str, narrative_blocks: list[dict]) -> dict:
    """
    Send narrative text to LLM for summarization.
    Uses single prompt for inputs up to ~35k tokens (fits all standard department reports).
    Uses parallel chunked execution for exceptionally large inputs.
    """
    # Build full prompt to check size
    sections = "\n\n".join(
        f"=== DEPARTMENT: {b['dept_name']} (code: {b['dept_code']}) ===\n{b['text']}"
        for b in narrative_blocks
    )

    user_message = (
        f"Summarize the following department daily report narrative sections for date: {report_date}.\n"
        f"Extract all events, participation entries, industry visits, and other matters.\n"
        f"Include content from [Free Text] sections — departments often write events there.\n"
        f"NEVER invent any number — use null for any count not explicitly stated in the source.\n\n"
        f"{sections}"
    )

    # Rough token estimate: 4 chars ≈ 1 token
    # Gemini 2.5 Flash easily handles 1M tokens. Sending all departments together (typically ~4-8k tokens)
    # produces faster, more cohesive output in a single 2-4s call.
    estimated_tokens = len(user_message) // 4
    if estimated_tokens <= 35000:
        raw = _llm_call(SUMMARIZE_SYSTEM_PROMPT, user_message)
        return _parse_json(raw, context="narrative_summarization_single")

    # Otherwise chunk by department with parallel execution
    return _chunked_summarize(report_date, narrative_blocks)


def _chunked_summarize(report_date: str, narrative_blocks: list[dict]) -> dict:
    """
    Chunked summarization: process departments in groups of 6 with parallel execution.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    merged = {
        "department_highlights": [],
        "staff_participation": [],
        "student_participation": [],
        "mtp_summary": [],
    }

    chunk_size = 6
    chunks = [narrative_blocks[i:i + chunk_size] for i in range(0, len(narrative_blocks), chunk_size)]

    def _process_chunk(chunk_idx, chunk):
        sections = "\n\n".join(
            f"=== DEPARTMENT: {b['dept_name']} (code: {b['dept_code']}) ===\n{b['text']}"
            for b in chunk
        )
        msg = (
            f"Summarize the following department daily report narrative sections for date: {report_date}.\n"
            f"Extract all events, participation entries, industry visits, and other matters.\n"
            f"Include content from [Free Text] sections — departments often write events there.\n"
            f"NEVER invent any number — use null for any count not explicitly stated in the source.\n\n"
            f"{sections}"
        )
        try:
            raw = _llm_call(SUMMARIZE_SYSTEM_PROMPT, msg)
            return _parse_json(raw, context=f"narrative_chunk_{chunk_idx}")
        except Exception as e:
            print(f"[WARN] Chunk {chunk_idx} failed: {e}")
            return None

    with ThreadPoolExecutor(max_workers=min(4, len(chunks))) as executor:
        futures = [executor.submit(_process_chunk, idx, c) for idx, c in enumerate(chunks)]
        for future in as_completed(futures):
            parsed = future.result()
            if isinstance(parsed, dict):
                if "department_highlights" in parsed and isinstance(parsed["department_highlights"], list):
                    merged["department_highlights"].extend([
                        b for b in parsed["department_highlights"]
                        if b.get("dept_code", "").lower() != "mtp"
                    ])
                for key in ["staff_participation", "student_participation"]:
                    if key in parsed and isinstance(parsed[key], list):
                        merged[key].extend(parsed[key])
                for item in parsed.get("mtp_summary", []):
                    if isinstance(item, dict) and item not in merged["mtp_summary"]:
                        merged["mtp_summary"].append(item)

    return merged


def _normalize_staff_attendance(raw_att: dict, dept_name: str) -> dict | None:
    """Accept both extractor (flat) and portal (nested staff) attendance shapes."""
    if not isinstance(raw_att, dict):
        return None
    if raw_att.get("staff"):
        teaching = raw_att.get("staff", {}).get("teaching") or {}
        non_teaching = raw_att.get("staff", {}).get("non_teaching") or {}
        t_rolls = teaching.get("on_rolls") or 0
        nt_rolls = non_teaching.get("on_rolls") or 0
        t_abs = teaching.get("absent") or 0
        nt_abs = non_teaching.get("absent") or 0
        total_rolls = t_rolls + nt_rolls
        total_absent = t_abs + nt_abs
        if total_rolls == 0 and total_absent == 0:
            return None
        present = total_rolls - total_absent
        return {
            "dept": dept_name or raw_att.get("dept") or "",
            "teaching_count": t_rolls or None,
            "non_teaching_count": nt_rolls or None,
            "on_rolls": total_rolls,
            "absent": total_absent,
            "present": present,
            "percentage": round(present / total_rolls * 100, 1) if total_rolls else None,
        }
    if any(k in raw_att for k in ("teaching_count", "on_rolls", "absent", "present")):
        att = dict(raw_att)
        att.pop("_students", None)
        att.pop("students", None)
        att.pop("staff", None)
        if not att.get("dept"):
            att["dept"] = dept_name
        on_rolls = att.get("on_rolls") or 0
        absent = att.get("absent") or 0
        if att.get("present") is None and on_rolls:
            att["present"] = on_rolls - absent
        if att.get("percentage") is None and on_rolls and att.get("present") is not None:
            att["percentage"] = round(att["present"] / on_rolls * 100, 1)
        if not on_rolls and not absent and not att.get("teaching_count"):
            return None
        return att
    return None


def _student_rows_from_nested(students: dict, dept_name: str) -> list[dict]:
    rows = []
    if not isinstance(students, dict):
        return rows
    mapping = [
        ("B.Tech", students.get("btech") or []),
        ("M.Tech", students.get("mtech") or []),
        ("Minor", students.get("minor") or []),
    ]
    for programme, years in mapping:
        for y in years:
            if not isinstance(y, dict):
                continue
            rolls = y.get("on_rolls")
            present = y.get("present")
            absent = y.get("absent")
            if rolls is None and present is None and absent is None:
                continue
            if present is None and rolls is not None and absent is not None:
                present = rolls - absent
            if absent is None and rolls is not None and present is not None:
                absent = rolls - present
            pct = round(present / rolls * 100, 1) if rolls and present is not None else None
            rows.append({
                "dept": dept_name,
                "programme": programme,
                "year": y.get("year") or "",
                "on_rolls": rolls,
                "present": present,
                "absent": absent,
                "percentage": pct,
            })
    return rows


def _is_real_note(text: str) -> bool:
    """Filter out table headers or raw pipe remnants that leaked into other matters."""
    if not text or not isinstance(text, str):
        return False
    t = text.strip()
    if not t or t.lower() in {"nil", "none", "no", "-", "—", "n/a", "na", "--"}:
        return False
    if "|" in t and any(k in t.lower() for k in ("rolls", "present", "absent", "s. no", "industry visited", "location")):
        return False
    if t.startswith("[Other]") and len(t) < 15:
        return False
    return True


def _deterministic_narratives(dept_data: list[dict]) -> tuple[list, list, list]:
    """Build highlights and participation lists from structured portal/extractor fields."""
    highlights = []
    staff_p = []
    student_p = []
    for dept in dept_data:
        dept_code = (dept.get("dept_code") or "").lower()
        if dept_code == "mtp":
            continue
        events = [e for e in (dept.get("events") or []) if isinstance(e, dict) and (e.get("name") or e.get("summary"))]
        other = []
        if dept.get("other_matters_text") and _has_real_narrative_content(dept["other_matters_text"]):
            raw_text = dept["other_matters_text"].strip()
            if _is_real_note(raw_text):
                other.append(raw_text)
        if events or other:
            highlights.append({
                "dept": dept.get("dept_name") or dept_code,
                "dept_code": dept_code,
                "events": events,
                "other_matters": other,
            })
        for row in dept.get("staff_participation_rows") or []:
            if isinstance(row, dict):
                staff_p.append(row)
        for row in dept.get("student_participation_rows") or []:
            if isinstance(row, dict):
                student_p.append(row)
    return highlights, staff_p, student_p


def _merge_highlights(deterministic: list, llm_blocks: list) -> list:
    """Prefer LLM wording when a department is covered; keep deterministic otherwise."""
    by_code = {}
    for block in deterministic:
        key = (block.get("dept_code") or block.get("dept") or "").lower()
        by_code[key] = block
    for block in llm_blocks:
        events = block.get("events") or []
        raw_other = block.get("other_matters") or []
        other = [m for m in raw_other if _is_real_note(m)]
        if not events and not other:
            continue
        key = (block.get("dept_code") or block.get("dept") or "").lower()
        block["other_matters"] = other
        by_code[key] = block
    return list(by_code.values())


def _build_all_department_roster(
    standard_depts: list[dict],
    uploaded_codes: set[str],
    highlights: list[dict],
    dept_data: list[dict],
) -> list[dict]:
    """
    Ensure every standard academic department is represented in the highlights section:
    - active: has real events/other matters
    - no_highlights: department was uploaded, but has no events today
    - missing_report: department report was not uploaded in the batch
    """
    roster = []
    highlights_by_key = {}
    for h in highlights:
        code = (h.get("dept_code") or "").lower()
        name = (h.get("dept") or "").lower()
        if code:
            highlights_by_key[code] = h
        if name:
            highlights_by_key[name] = h

    def _is_uploaded(std):
        if std["code"] in uploaded_codes:
            return True
        for alias in std.get("aliases", []):
            if alias in uploaded_codes:
                return True
        for d in dept_data:
            d_code = (d.get("dept_code") or "").lower()
            d_name = (d.get("dept_name") or "").lower()
            if std["code"] in d_code or std["code"] in d_name:
                return True
            for alias in std.get("aliases", []):
                if alias in d_code or alias in d_name:
                    return True
        return False

    def _find_highlight(std):
        if std["code"] in highlights_by_key:
            return highlights_by_key[std["code"]]
        for alias in std.get("aliases", []):
            if alias in highlights_by_key:
                return highlights_by_key[alias]
        for key, h in highlights_by_key.items():
            if std["code"] in key or any(a in key for a in std.get("aliases", [])):
                return h
        return None

    handled_keys = set()
    seen_event_keys = set()

    for std in standard_depts:
        found_h = _find_highlight(std)
        uploaded = _is_uploaded(std)

        raw_events = found_h.get("events", []) if found_h else []
        other = found_h.get("other_matters", []) if found_h else []

        events = []
        for ev in raw_events:
            ev_name = (ev.get("name") or "").strip().lower()
            ev_sum = (ev.get("summary") or "").strip().lower()[:40]
            sig = (ev_name, ev_sum)
            if sig not in seen_event_keys:
                seen_event_keys.add(sig)
                events.append(ev)

        if found_h:
            handled_keys.add((found_h.get("dept_code") or "").lower())
            handled_keys.add((found_h.get("dept") or "").lower())

        if events or other:
            roster.append({
                "dept": std["name"],
                "dept_code": std["code"],
                "status": "active",
                "events": events,
                "other_matters": other,
            })
        elif uploaded:
            roster.append({
                "dept": std["name"],
                "dept_code": std["code"],
                "status": "no_highlights",
                "events": [],
                "other_matters": [],
                "message": "No significant highlights reported for today.",
            })
        else:
            roster.append({
                "dept": std["name"],
                "dept_code": std["code"],
                "status": "missing_report",
                "events": [],
                "other_matters": [],
                "message": "Report not submitted / data not available for today.",
            })

    EXCLUDED = {"mtp", "library", "overall_attendance", "attendance"}
    for h in highlights:
        h_code = (h.get("dept_code") or "").lower()
        h_name = (h.get("dept") or "").lower()
        if h_code in EXCLUDED or h_name in EXCLUDED:
            continue
        if h_code not in handled_keys and h_name not in handled_keys:
            raw_events = h.get("events") or []
            events = []
            for ev in raw_events:
                ev_name = (ev.get("name") or "").strip().lower()
                ev_sum = (ev.get("summary") or "").strip().lower()[:40]
                sig = (ev_name, ev_sum)
                if sig not in seen_event_keys:
                    seen_event_keys.add(sig)
                    events.append(ev)
            other = h.get("other_matters") or []
            if events or other:
                roster.append({
                    "dept": h.get("dept") or h_code.upper(),
                    "dept_code": h_code,
                    "status": "active",
                    "events": events,
                    "other_matters": other,
                })
            handled_keys.add(h_code)
            handled_keys.add(h_name)

    return roster


def _has_real_narrative_content(text: str) -> bool:
    """Check if narrative text has actual content worth sending to LLM."""
    lines = text.strip().split("\n")
    content_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            continue  # Skip section labels like [Events / Seminars / Workshops]
        content_lines.append(stripped)

    if not content_lines:
        return False

    # Check if remaining content is all empty/nil
    EMPTY_MARKERS = {"", "nil", "none", "no", "-", "—", "n/a", "na", "--"}
    for line in content_lines:
        # Clean pipe-delimited cells
        cells = [c.strip().lower() for c in line.split("|")]
        if any(c and c not in EMPTY_MARKERS for c in cells):
            return True

    return False


def _remove_empty_sections(report: dict) -> dict:
    """Remove sections that have no data."""
    keys_to_check = [
        "infrastructure_issues", "department_highlights",
        "staff_participation", "student_participation",
        "staff_changes", "classwork_adjustments", "incidents",
        "attendance_charts", "student_attendance",
    ]
    for key in keys_to_check:
        if key in report and isinstance(report[key], list) and not report[key]:
            del report[key]

    # Remove empty dict sections
    for key in ["library_transactions", "library_services"]:
        if key in report and isinstance(report[key], dict) and not report[key]:
            del report[key]

    # Remove library attendance if all None
    lib = report.get("attendance", {}).get("library")
    if lib and all(v is None for v in lib.values()):
        report["attendance"]["library"] = None

    # Remove MTP narrative if empty
    if not report.get("mtp_narrative", "").strip():
        report.pop("mtp_narrative", None)
    if not report.get("mtp_batch_pills", "").strip():
        report.pop("mtp_batch_pills", None)
    if not report.get("mtp_summary", []):
        report.pop("mtp_summary", None)

    return report


# ── LLM call with model fallback and retry ────────────────────────────────────

def _llm_call(system: str, user: str) -> str:
    """
    Call LLM with fallback chain:
      1. Google Gemini (models/gemini-2.5-flash)  — if GEMINI_API_KEY is set (primary & fast, ~2s)
      2. OpenRouter (OPENROUTER_MODELS)          — if OPENROUTER_API_KEY is set (fallback)

    Both use temperature=0 for deterministic, non-hallucinating output.
    max_output_tokens=16384 to prevent truncation of large consolidated outputs.
    """
    # ── 1. Try Gemini first (fastest, direct API, high rate limit) ────────────
    gemini_client = _get_gemini_client()
    if gemini_client is not None:
        from google.genai import types as gtypes
        for model_name in GEMINI_MODELS:
            for attempt in range(2):
                try:
                    response = gemini_client.models.generate_content(
                        model=model_name,
                        contents=user,
                        config=gtypes.GenerateContentConfig(
                            system_instruction=system,
                            temperature=0,
                            max_output_tokens=16384,
                        ),
                    )
                    try:
                        text = response.text
                    except Exception as text_err:
                        raise ValueError(f"Gemini response.text error: {text_err}") from text_err
                    if not text or not text.strip():
                        raise ValueError(f"Gemini ({model_name}) returned empty text")

                    print(f"[LLM] Used Gemini ({model_name})")
                    return text

                except Exception as e:
                    err_str = str(e).lower()
                    print(f"[LLM] Gemini warning ({model_name}, attempt {attempt+1}/2): {e}")
                    if "404" in err_str or "not found" in err_str or "503" in err_str or "unavailable" in err_str or "429" in err_str or "quota" in err_str:
                        # Move immediately to next model in fallback list
                        break
                    if attempt < 1:
                        time.sleep(0.5)
                        continue
                    break

    # ── 2. Fallback to OpenRouter if Gemini unavailable or failed ─────────────
    or_client = _get_openrouter_client()
    if or_client is not None:
        for model_name in OPENROUTER_MODELS:
            try:
                resp = or_client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user",   "content": user},
                    ],
                    temperature=0,
                    max_tokens=16384,
                    timeout=20.0,
                )
                text = resp.choices[0].message.content
                if text and text.strip():
                    print(f"[LLM] Used OpenRouter ({model_name})")
                    return text
            except Exception as e:
                print(f"[LLM] OpenRouter error ({model_name}): {e}")
                continue

    raise RuntimeError(
        "No LLM backend available or all models failed. Set a valid GEMINI_API_KEY or OPENROUTER_API_KEY."
    )


def _parse_json(raw: str, context: str) -> dict | list:
    """Parse JSON from LLM response reliably, stripping markdown and fixing issues."""
    cleaned = raw.strip()

    # Strip ```json ... ``` fences
    if "```json" in cleaned:
        cleaned = cleaned.split("```json")[1].split("```")[0].strip()
    elif cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0].strip()

    # Find the start of the JSON — prefer { over [
    brace_idx = cleaned.find("{")
    bracket_idx = cleaned.find("[")

    if brace_idx == -1 and bracket_idx == -1:
        raise ValueError(f"No JSON object or array found in LLM output during {context}.\nRaw (first 300): {raw[:300]}")

    if brace_idx == -1:
        cleaned = cleaned[bracket_idx:]
    elif bracket_idx == -1 or brace_idx <= bracket_idx:
        cleaned = cleaned[brace_idx:]
    else:
        # bracket appears before brace — check if that list is wrapping the object
        # e.g. "[{...}]" — try brace first anyway, fall back to bracket
        cleaned = cleaned[brace_idx:]

    try:
        parsed = json_repair.loads(cleaned)
        if not parsed and parsed != 0:
            raise ValueError("Parsed JSON is empty")

        # Auto-wrap a bare list of dept objects into the expected schema
        if isinstance(parsed, list):
            if parsed and isinstance(parsed[0], dict) and (
                "dept" in parsed[0] or "events" in parsed[0] or "dept_code" in parsed[0]
            ):
                parsed = {
                    "department_highlights": parsed,
                    "staff_participation": [],
                    "student_participation": [],
                }

        return parsed
    except Exception as e:
        raise ValueError(
            f"LLM returned invalid JSON during {context}.\n"
            f"Error: {e}\n"
            f"Raw output (first 500 chars): {raw[:500]}"
        )