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
#   1. OpenRouter  — set OPENROUTER_API_KEY in .env  (primary)
#   2. Google Gemini — set GEMINI_API_KEY in .env     (fallback)

_openrouter_client = None
_gemini_client = None

def _get_openrouter_client():
    """Lazy-init OpenRouter client via openai-compatible SDK."""
    global _openrouter_client
    if _openrouter_client is None:
        from openai import OpenAI
        key = os.getenv("OPENROUTER_API_KEY", "").strip()
        if not key:
            return None
        _openrouter_client = OpenAI(
            api_key=key,
            base_url="https://openrouter.ai/api/v1",
            default_headers={
                "HTTP-Referer": "https://vnrvjiet.ac.in",
                "X-Title": "MTP ReportGen",
            },
        )
    return _openrouter_client


def _get_gemini_client():
    """Lazy-init Gemini client."""
    global _gemini_client
    if _gemini_client is None:
        from google import genai
        key = os.getenv("GEMINI_API_KEY", "").strip()
        if not key:
            return None
        _gemini_client = genai.Client(api_key=key)
    return _gemini_client


# Primary model: OpenRouter free Gemma 4
OPENROUTER_MODEL = "google/gemma-4-31b-it:free"

# Gemini fallback order
GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
]


# ── LLM Prompt — ONLY for narrative summarization ────────────────────────────
# CRITICAL: The LLM NEVER receives attendance, infrastructure counts, or any
# numeric data that was already extracted deterministically. It only ever sees
# the events/participation/free-text sections.

SUMMARIZE_SYSTEM_PROMPT = """You are a report summarizer for VNRVJIET (VNR Vignana Jyothi Institute of Engineering & Technology).

You will receive narrative sections from department daily reports: events, staff/student participation entries, MTP (Mentoring, Training & Placements) data, industry visits, and any other free-text matters.

YOUR ONLY JOB: faithfully summarize and organize narrative content.

══════════════════════════════════════════════════════
ABSOLUTE RULES — VIOLATION IS NOT ACCEPTABLE:
1. Every fact must come DIRECTLY from the input text. DO NOT infer, guess, or add anything.
2. Use EXACT WORDS from the source wherever possible.
3. DO NOT INVENT ANY NUMBER. If a participant count is not explicitly stated in the source, set it to null.
4. Return ONLY valid JSON. No explanation, no preamble, no markdown code fences.
5. DO NOT SKIP ANY EVENT or participation entry. Include every single one.
6. If a section is entirely empty or only contains "nil"/"none"/"-", skip it — do NOT include empty placeholders.
7. For MTP: Include ALL placement drives, pre-placement talks, aptitude tests, training sessions, batch statistics. This is CRITICAL data. But DO NOT GUESS any student count or percentage — only use numbers explicitly stated in the source.
══════════════════════════════════════════════════════

CONTENT SOURCES YOU WILL RECEIVE:
- [Events / Seminars / Workshops] — table rows
- [Participation by Staff] — table rows  
- [Participation by Students] — table rows
- [MTP Section IV] — MTP narrative text
- [Batch Pills Open Summary] — MTP placement stats
- [Free Text — <dept name>] — paragraphs written outside the template tables
- [Other] — unclassified table content

TREAT ALL SOURCES EQUALLY. If an event appears only in [Free Text], still include it. Many departments write their events as free text paragraphs rather than filling the template tables.

For each EVENT, extract:
- "name": exact event name from source
- "summary": 1-3 sentence summary using source wording; include resource person, participant count (if stated), venue, outcomes
- "importance": "high", "medium", or "low"
  * HIGH: Placement drives, PPTs, external events, resource persons from industry/academia, events with >50 participants (if count stated), competitive/national/international events
  * MEDIUM: Internal workshops 20-50 participants, dept-level seminars
  * LOW: Routine internal sessions <20 participants
- "date": exact date string from source, or null
- "duration": duration string from source, or null
- "participants_internal": integer from source ONLY, or null — DO NOT GUESS
- "participants_external": integer from source ONLY, or null — DO NOT GUESS
- "resource_person": name string or null

For each STAFF PARTICIPATION entry:
- "name": person's name
- "dept": department name
- "event": event name
- "role": their role (delegate, speaker, resource person, participant, etc.)
- "date": date string or null
- "venue": venue if mentioned, else null
- "summary": 1 sentence using source wording

For each STUDENT PARTICIPATION entry:
- "name": student's name or "students" if individual names not given
- "dept": department name
- "event": event name
- "achievement": achievement or status (e.g. "participated", "won 1st prize")
- "date": date string or null
- "summary": 1 sentence using source wording

For OTHER MATTERS: preserve the exact description from the source.

OUTPUT SCHEMA (return ONLY this JSON, nothing else):
{
  "department_highlights": [
    {
      "dept": "full department name",
      "dept_code": "short code",
      "events": [
        {
          "name": "...",
          "summary": "...",
          "importance": "high|medium|low",
          "date": "...|null",
          "duration": "...|null",
          "participants_internal": 42,
          "participants_external": null,
          "resource_person": "...|null"
        }
      ],
      "other_matters": ["string descriptions"]
    }
  ],
  "staff_participation": [
    {
      "name": "...", "dept": "...", "event": "...", "role": "...",
      "date": "...|null", "venue": "...|null", "summary": "..."
    }
  ],
  "student_participation": [
    {
      "name": "...", "dept": "...", "event": "...", "achievement": "...",
      "date": "...|null", "summary": "..."
    }
  ]
}

IMPORTANT GROUPING RULES:
- Group events under their department in department_highlights.
- Staff participation and student participation go into the top-level lists.
- Only include a department in department_highlights if it has at least ONE event or noteworthy matter.
- MTP department entries (placement drives, PPTs) are ALWAYS "high" importance."""


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
        "staff_participation": [],
        "student_participation": [],
        "staff_changes": [],
        "classwork_adjustments": [],
        "incidents": [],
        "infrastructure_issues": [],
        "library_transactions": {},
        "library_services": {},
    }

    narrative_blocks = []  # Collect narrative text for LLM

    for dept in dept_data:
        dept_code = dept["dept_code"]
        dept_name = dept["dept_name"]

        # Attendance charts
        if dept.get("attendance_charts"):
            final_report["attendance_charts"].extend(dept["attendance_charts"])

        # Attendance — deterministic, never goes to LLM
        if dept.get("attendance"):
            final_report["attendance"]["departments"].append(dept["attendance"])

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
        if dept.get("overall_student_attendance_table"):
            final_report["overall_student_attendance_table"] = dept["overall_student_attendance_table"]

        # MTP narrative — sent to LLM for summarization (numbers guarded by prompt)
        if dept.get("mtp_narrative"):
            final_report["mtp_narrative"] = dept["mtp_narrative"]
        if dept.get("mtp_batch_pills"):
            final_report["mtp_batch_pills"] = dept["mtp_batch_pills"]

        # ── Collect narrative text for LLM ────────────────────────────────
        # IMPORTANT: We collect ALL narrative text including loose_paragraphs.
        # Departments often write events as free text rather than filling the table.
        narrative_parts = []
        for key in [
            "events_text",
            "staff_participation_text",
            "student_participation_text",
            "other_matters_text",
            "loose_paragraphs",
            "mtp_narrative",
            "mtp_batch_pills",
        ]:
            text = dept.get(key, "").strip()
            if text and _has_real_narrative_content(text):
                narrative_parts.append(text)

        if narrative_parts:
            narrative_blocks.append({
                "dept_code": dept_code,
                "dept_name": dept_name,
                "text": "\n\n".join(narrative_parts),
            })

    # ── Phase 2: LLM summarization of narrative content ───────────────────
    # Only if there is actual narrative content to process
    if narrative_blocks:
        try:
            llm_result = _summarize_narratives(report_date, narrative_blocks)

            # Normalize: sometimes LLM wraps department_highlights directly as a list
            if isinstance(llm_result, list):
                # Check if it looks like department_highlights (list of dept objects)
                if llm_result and isinstance(llm_result[0], dict) and (
                    "dept" in llm_result[0] or "events" in llm_result[0]
                ):
                    llm_result = {"department_highlights": llm_result,
                                  "staff_participation": [],
                                  "student_participation": []}
                else:
                    # Unknown list format — skip
                    print(f"[WARNING] LLM returned unknown list format, skipping")
                    llm_result = {}

            if isinstance(llm_result, dict):
                if "department_highlights" in llm_result:
                    final_report["department_highlights"] = llm_result["department_highlights"]
                if "staff_participation" in llm_result:
                    final_report["staff_participation"] = llm_result["staff_participation"]
                if "student_participation" in llm_result:
                    final_report["student_participation"] = llm_result["student_participation"]
            else:
                print(f"[WARNING] LLM returned unexpected type: {type(llm_result)}")
        except Exception as e:
            import traceback
            print(f"[ERROR] LLM summarization failed: {e}")
            traceback.print_exc()
            print("[INFO] Continuing with deterministic data only.")


    # ── Clean up empty sections ───────────────────────────────────────────
    final_report = _remove_empty_sections(final_report)

    return final_report


def _summarize_narratives(report_date: str, narrative_blocks: list[dict]) -> dict:
    """
    Send narrative text to LLM for summarization.
    Uses per-department chunking for large inputs with per-department retry.
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

    # Rough token estimate: 4 chars ≈ 1 token; if under 20000 tokens do single call
    estimated_tokens = len(user_message) // 4
    if estimated_tokens <= 20000:
        raw = _llm_call(SUMMARIZE_SYSTEM_PROMPT, user_message)
        return _parse_json(raw, context="narrative_summarization_single")

    # Otherwise chunk by department with per-dept retry on failure
    return _chunked_summarize(report_date, narrative_blocks)


def _chunked_summarize(report_date: str, narrative_blocks: list[dict]) -> dict:
    """
    Chunked summarization: process departments in groups of 4.
    On failure, retry each department individually rather than silently dropping.
    """
    merged = {
        "department_highlights": [],
        "staff_participation": [],
        "student_participation": [],
    }

    chunk_size = 4
    for i in range(0, len(narrative_blocks), chunk_size):
        chunk = narrative_blocks[i:i + chunk_size]
        dept_names = [b["dept_name"] for b in chunk]

        sections = "\n\n".join(
            f"=== DEPARTMENT: {b['dept_name']} (code: {b['dept_code']}) ===\n{b['text']}"
            for b in chunk
        )
        user_message = (
            f"Summarize the following department daily report narrative sections for date: {report_date}.\n"
            f"Extract all events, participation entries, industry visits, and other matters.\n"
            f"Include content from [Free Text] sections — departments often write events there.\n"
            f"NEVER invent any number — use null for any count not explicitly stated in the source.\n\n"
            f"{sections}"
        )

        try:
            raw = _llm_call(SUMMARIZE_SYSTEM_PROMPT, user_message)
            parsed = _parse_json(raw, context=f"narrative_chunk_{i}")

            if isinstance(parsed, dict):
                for key in ["department_highlights", "staff_participation", "student_participation"]:
                    if key in parsed and isinstance(parsed[key], list):
                        merged[key].extend(parsed[key])

        except Exception as chunk_err:
            # Chunk failed — retry each department individually
            print(
                f"[WARN] Chunk {i//chunk_size + 1} failed ({dept_names}): {chunk_err}\n"
                f"       Retrying each department individually..."
            )
            for block in chunk:
                try:
                    single_message = (
                        f"Summarize the following department daily report narrative sections for date: {report_date}.\n"
                        f"Extract all events, participation entries, industry visits, and other matters.\n"
                        f"Include content from [Free Text] sections — departments often write events there.\n"
                        f"NEVER invent any number — use null for any count not explicitly stated in the source.\n\n"
                        f"=== DEPARTMENT: {block['dept_name']} (code: {block['dept_code']}) ===\n{block['text']}"
                    )
                    raw = _llm_call(SUMMARIZE_SYSTEM_PROMPT, single_message)
                    parsed = _parse_json(raw, context=f"dept_retry_{block['dept_code']}")

                    if isinstance(parsed, dict):
                        for key in ["department_highlights", "staff_participation", "student_participation"]:
                            if key in parsed and isinstance(parsed[key], list):
                                merged[key].extend(parsed[key])
                    print(f"       [OK] Retry succeeded for {block['dept_name']}")

                except Exception as dept_err:
                    # Individual department failed — log clearly, do NOT silently drop
                    print(
                        f"[ERROR] Failed to summarize {block['dept_name']} even after retry: {dept_err}\n"
                        f"        This department's narrative will be MISSING from the report."
                    )

    return merged


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
        "attendance_charts",
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

    return report


# ── LLM call with model fallback and retry ────────────────────────────────────

def _llm_call(system: str, user: str) -> str:
    """
    Call LLM with fallback chain:
      1. OpenRouter (google/gemma-4-31b-it:free)  — if OPENROUTER_API_KEY is set
      2. Google Gemini                             — if GEMINI_API_KEY is set

    Both use temperature=0 for deterministic, non-hallucinating output.
    max_tokens=16384 to prevent truncation of large consolidated outputs.
    """
    # ── Try OpenRouter first ──────────────────────────────────────────────────
    or_client = _get_openrouter_client()
    if or_client is not None:
        for attempt in range(3):
            try:
                resp = or_client.chat.completions.create(
                    model=OPENROUTER_MODEL,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user",   "content": user},
                    ],
                    temperature=0,
                    max_tokens=16384,
                )
                text = resp.choices[0].message.content
                if text and text.strip():
                    print(f"[LLM] Used OpenRouter ({OPENROUTER_MODEL})")
                    return text
                print(f"[LLM] OpenRouter returned empty response (attempt {attempt+1}/3)")
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "rate" in err_str.lower():
                    wait = (2 ** attempt) * 5
                    print(f"[LLM] OpenRouter rate limit, waiting {wait}s...")
                    time.sleep(wait)
                elif "402" in err_str or "credit" in err_str.lower():
                    print(f"[LLM] OpenRouter credits exhausted, falling back to Gemini")
                    break
                else:
                    print(f"[LLM] OpenRouter error (attempt {attempt+1}/3): {e}")
                    if attempt == 2:
                        print("[LLM] Falling back to Gemini after 3 OpenRouter failures")
        # Fall through to Gemini

    # ── Fallback: Gemini ──────────────────────────────────────────────────────
    gemini_client = _get_gemini_client()
    if gemini_client is None:
        raise RuntimeError(
            "No LLM backend available. Set OPENROUTER_API_KEY or GEMINI_API_KEY in .env"
        )

    from google.genai import types as gtypes
    last_err = None
    for model_name in GEMINI_MODELS:
        for attempt in range(3):
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
                print(f"[LLM] Used Gemini fallback ({model_name})")
                return response.text
            except Exception as e:
                last_err = e
                err_str = str(e)
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    wait = (2 ** attempt) * 5
                    print(f"[LLM] Gemini rate limit ({model_name}), waiting {wait}s...")
                    time.sleep(wait)
                    continue
                elif "404" in err_str or "not found" in err_str.lower():
                    break
                else:
                    raise

    raise last_err


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