"""
AI Service — Hybrid Consolidation Pipeline (v2)
=================================================
Phase 1: Deterministic extraction of structured data (attendance, infra, etc.)
Phase 2: LLM summarization of narrative sections only (events, participation)

Uses the modern `google-genai` SDK (replaces deprecated `google-generativeai`).
The LLM NEVER sees numbers for attendance, library, or infrastructure.
This eliminates number hallucination entirely.
"""

import os
import json
import re
import time
from google import genai
from google.genai import types
import json_repair

# ── Initialize Gemini client ─────────────────────────────────────────────────
_api_key = os.getenv("GEMINI_API_KEY")
_client = None

def _get_client():
    """Lazy-init the Gemini client."""
    global _client
    if _client is None:
        key = os.getenv("GEMINI_API_KEY") or _api_key
        if not key:
            raise RuntimeError("GEMINI_API_KEY not set. Add it to your .env file.")
        _client = genai.Client(api_key=key)
    return _client


# Model preference order — try faster/cheaper first, fall back if unavailable
MODEL_CANDIDATES = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
]


# ── LLM Prompt — ONLY for narrative summarization ────────────────────────────

SUMMARIZE_SYSTEM_PROMPT = """You are a report summarizer for VNRVJIET (VNR Vignana Jyothi Institute of Engineering & Technology).

You will receive event descriptions, staff/student participation entries, MTP (Mentoring, Training & Placements) data, and other matters from department daily reports.

YOUR ONLY JOB: summarize and organize this narrative content faithfully.

STRICT RULES:
- Every fact must come DIRECTLY from the input. Do NOT infer, guess, or add anything.
- Use EXACT WORDS from the source wherever possible.
- Return ONLY valid JSON. No explanation, no preamble, no markdown fences.
- DO NOT SKIP ANY EVENT or participation entry. Every single one must be included.
- For MTP data: ALWAYS include ALL placement drives, pre-placement talks, aptitude tests,
  batch pill summaries, and any training/placement statistics. This is CRITICAL data.

For each EVENT, extract:
- "name": exact event name from the source
- "summary": 1-3 sentence summary using source wording. Include key details like 
  resource person name, number of participants, venue, outcomes.
- "importance": "high", "medium", or "low"
  * HIGH: Placement drives, PPTs, external events, events with resource persons from 
    industry/academia, events with >50 participants, competitive events, national/international
  * MEDIUM: Internal workshops with 20-50 participants, department-level seminars
  * LOW: Routine internal sessions with <20 participants
- "date": date string from source
- "duration": duration string from source
- "participants_internal": integer or null
- "participants_external": integer or null
- "resource_person": name string or null

For each STAFF PARTICIPATION entry, extract:
- "name": person's name
- "dept": department name
- "event": event name
- "role": their role (delegate, speaker, resource person, etc.)
- "date": date string
- "venue": venue if mentioned, else null
- "summary": 1 sentence using source wording

For each STUDENT PARTICIPATION entry, extract:
- "name": student's name
- "dept": department name
- "event": event name
- "achievement": achievement or status
- "date": date string
- "summary": 1 sentence using source wording

For OTHER MATTERS, preserve the exact description from the source.

OUTPUT SCHEMA:
{
  "department_highlights": [
    {
      "dept": "full department name",
      "dept_code": "short code",
      "events": [... event objects as above ...],
      "other_matters": ["string descriptions"]
    }
  ],
  "staff_participation": [... staff participation objects ...],
  "student_participation": [... student participation objects ...]
}

IMPORTANT:
- Group events by department.
- ONLY include a department if it has at least ONE event or noteworthy matter.
- Skip sections that are completely empty (only "nil"/"none"/"-").
- For any numeric field where the value is unclear, use null. Never guess a number.
- MTP department events (placement drives, PPTs) are ALWAYS "high" importance."""


def consolidate(report_date: str, dept_data: list[dict]) -> dict:
    """
    Consolidate department reports using hybrid pipeline.
    
    Args:
        report_date: Date string in YYYY-MM-DD format
        dept_data: List of dicts from structured_extractor.extract_structured_data()
                   Each dict has deterministic fields + narrative text fields.
    
    Returns:
        Complete consolidated report dict matching the output schema.
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

        # Attendance — deterministic
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

        # Classwork adjustments — deterministic
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

        # MTP specific deterministic parts
        if dept.get("mtp_narrative"):
            final_report["mtp_narrative"] = dept["mtp_narrative"]
        if dept.get("mtp_batch_pills"):
            final_report["mtp_batch_pills"] = dept["mtp_batch_pills"]

        # ── Collect narrative text for LLM ────────────────────────────────
        narrative_parts = []
        for key in ["events_text", "staff_participation_text",
                     "student_participation_text", "other_matters_text",
                     "loose_paragraphs"]:
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
    if narrative_blocks:
        try:
            llm_result = _summarize_narratives(report_date, narrative_blocks)
            if isinstance(llm_result, dict):
                # Merge LLM results
                if "department_highlights" in llm_result:
                    final_report["department_highlights"] = llm_result["department_highlights"]
                if "staff_participation" in llm_result:
                    final_report["staff_participation"] = llm_result["staff_participation"]
                if "student_participation" in llm_result:
                    final_report["student_participation"] = llm_result["student_participation"]
        except Exception as e:
            print(f"[WARNING] LLM summarization failed, continuing with deterministic data: {e}")

    # ── Clean up empty sections ───────────────────────────────────────────
    final_report = _remove_empty_sections(final_report)

    return final_report


def _summarize_narratives(report_date: str, narrative_blocks: list[dict]) -> dict:
    """
    Send narrative text to LLM for summarization.
    Uses chunking for large inputs.
    """
    # Build the user message
    sections = "\n\n".join(
        f"=== DEPARTMENT: {b['dept_name']} (code: {b['dept_code']}) ===\n{b['text']}"
        for b in narrative_blocks
    )

    user_message = (
        f"Summarize the following department report narrative sections for {report_date}.\n"
        f"Extract events, participation entries, and other matters.\n"
        f"Skip any section that is entirely empty or contains only 'nil'/'none'/'-'.\n"
        f"PAY SPECIAL ATTENTION to MTP/placement related events — they are ALWAYS high importance.\n\n"
        f"{sections}"
    )

    # Check if we need chunking (rough token estimate: 4 chars ≈ 1 token)
    estimated_tokens = len(user_message) // 4
    if estimated_tokens > 6000:
        return _chunked_summarize(report_date, narrative_blocks)

    raw = _llm_call(SUMMARIZE_SYSTEM_PROMPT, user_message)
    return _parse_json(raw, context="narrative_summarization")


def _chunked_summarize(report_date: str, narrative_blocks: list[dict]) -> dict:
    """Chunked summarization for large inputs."""
    merged = {
        "department_highlights": [],
        "staff_participation": [],
        "student_participation": [],
    }

    chunk_size = 5
    for i in range(0, len(narrative_blocks), chunk_size):
        chunk = narrative_blocks[i:i + chunk_size]
        sections = "\n\n".join(
            f"=== DEPARTMENT: {b['dept_name']} (code: {b['dept_code']}) ===\n{b['text']}"
            for b in chunk
        )
        user_message = (
            f"Summarize the following department report narrative sections for {report_date}.\n"
            f"Extract events, participation entries, and other matters.\n"
            f"Skip any section that is entirely empty or contains only 'nil'/'none'/'-'.\n"
            f"PAY SPECIAL ATTENTION to MTP/placement related events.\n\n"
            f"{sections}"
        )

        try:
            raw = _llm_call(SUMMARIZE_SYSTEM_PROMPT, user_message)
            parsed = _parse_json(raw, context=f"narrative_chunk_{i}")

            if isinstance(parsed, dict):
                for key in ["department_highlights", "staff_participation", "student_participation"]:
                    if key in parsed and isinstance(parsed[key], list):
                        merged[key].extend(parsed[key])
        except Exception as e:
            print(f"[WARNING] Skipping failed narrative chunk {i}: {e}")

    return merged


def _has_real_narrative_content(text: str) -> bool:
    """Check if narrative text has actual content worth sending to LLM."""
    lines = text.strip().split("\n")
    # Filter out header lines and empty lines
    content_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            continue  # Skip section labels like [Events / Seminars / Workshops]
        # Skip lines that are just column headers
        if all(w in stripped.lower() for w in ["s.", "no"]):
            if "|" in stripped:
                continue
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

    return report


# ── Helpers ───────────────────────────────────────────────────────────────────

def _llm_call(system: str, user: str) -> str:
    """Call Gemini API using the new google-genai SDK with retry and model fallback."""
    client = _get_client()
    last_err = None

    for model_name in MODEL_CANDIDATES:
        for attempt in range(3):  # Retry up to 3 times per model
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=user,
                    config=types.GenerateContentConfig(
                        system_instruction=system,
                        temperature=0,
                        max_output_tokens=8192,
                    ),
                )
                return response.text
            except Exception as e:
                last_err = e
                err_str = str(e)
                # Rate limit — wait and retry
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    wait_time = (2 ** attempt) * 5  # 5, 10, 20 seconds
                    print(f"[RATE_LIMIT] {model_name} attempt {attempt+1}/3 — waiting {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                # Model not found — try next model
                elif "404" in err_str or "not found" in err_str.lower():
                    print(f"[MODEL] {model_name} not available, trying next...")
                    break
                # Other error — raise immediately
                else:
                    raise

    raise last_err


def _parse_json(raw: str, context: str) -> dict | list:
    """Parse JSON from LLM response reliably, stripping markdown and fixing trailing commas."""
    cleaned = raw.strip()

    # Strip markdown code fences
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]

    # Strip any potential prefix/suffix text that isn't JSON
    if "```json" in cleaned:
        cleaned = cleaned.split("```json")[1].split("```")[0].strip()

    try:
        parsed = json_repair.loads(cleaned)
        if not parsed:
            raise ValueError("Parsed JSON is empty")
        return parsed
    except Exception as e:
        raise ValueError(
            f"LLM returned invalid JSON during {context}.\n"
            f"Error: {e}\n"
            f"Raw output (first 500 chars): {raw[:500]}"
        )