import json
import os
import re
from google import genai
import json_repair

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
MODEL = "gemini-2.5-flash"

SYSTEM_PROMPT = """You are a report consolidation assistant for the Principal's office of VNRVJIET (VNR Vignana Jyothi Institute of Engineering & Technology).
You receive daily reports from all departments and produce one concise consolidated JSON report.

STRICT RULES — no exceptions:
- Every fact in your output must come directly from the input. Do not infer, guess, or add anything.
- Preserve key terms, names, and numbers accurately without losing their meaning, but keep summaries concise and professional.
- Do not include individual student or staff names in attendance counts — use numbers only.
- Return ONLY valid JSON matching the output schema below. No explanation, no preamble, no markdown fences.

FIELD EXTRACTION GUIDELINES:
- Attendance data is in a table labeled "Staff Attendance". Extract: on_rolls, absent, present. Calculate percentage = round((present / on_rolls) * 100, 1).
- Infrastructure issues are in "Infrastructure Issues or Maintenance". KEEP only pending ones (where Completed On / Status is blank or "pending").
- Events are in "Events / Seminars / Workshops". Extract event name, date/duration, participant counts (internal vs external), resource person name.
- Staff participation at external events is in "Participation by Staff".
- Student participation at external events is in "Particiption by Students" (note the typo in source data).
- Staff changes (joined/left) are in "Staff Joined or Left".
- Classwork adjustments are in "Classword Adjustments / Lecture Interchange" — just count per department.
- Incidents are in "Incidents (Discipline)".
- Library data has its own sections: "Library Services and Transactions" and the plagiarism/patent services section.
- "Any Other Matter" captures miscellaneous items — these MUST be grouped under their source department.
- Check free text paragraphs at the bottom of each file for events or participation data missing from tables.

COMPRESSION RULES — apply before writing each section:

KEEP as-is:
  - Infrastructure issues where status is pending
  - Any incident (discipline of staff or student)
  - Any staff joined or left entry
  - Events that had external participants (Others > 0)
  - Staff or student participation at external events (national/international conferences, competitions, workshops, etc.)

COMPRESS to numbers / one line:
  - Attendance: one row per dept → {dept, on_rolls, absent, present, percentage}
    percentage = round((present / on_rolls) * 100, 1) — if on_rolls is 0 or missing, use null
  - Classwork adjustments: just total count per dept, not individual rows
  - Library transactions: preserve exact numbers from the source

DROP entirely (do not mention in output):
  - Any section that is completely empty or has only "nil", "none", "no", "-", "N/A" entries
  - Remarks that are "nil", "none", "no issues", "-", or equivalent
  - Resolved infrastructure issues (completed_on is filled)
  - Duplicate information that appears across multiple departments

DEPARTMENT HIGHLIGHTS — CRITICAL SECTION:
  - Group ALL events AND other matters BY DEPARTMENT.
  - Each department entry should have:
    * "dept": the full department name (use exact name from source report)
    * "dept_code": the short code (cse, ece, etc.)
    * "events": list of events from that department
    * "other_matters": list of other noteworthy items from that department
  - ONLY include a department if it has at least ONE event with importance "high" or "medium", OR a noteworthy "other matter".
  - For each event, write a concise 1-2 sentence "summary" using EXACT WORDS from the source report as much as possible.
  - Rate each event's "importance" as "high", "medium", or "low":
    * HIGH: External events, events with resource persons from industry/academia, events with >50 participants, competitive events, national/international events
    * MEDIUM: Internal workshops with 20-50 participants, department-level seminars
    * LOW: Routine internal sessions with <20 participants
  - Combine multiple small internal events from the same department into one entry if they are similar.
  - For each "other_matters" item, preserve the exact description from the source report.

PARTICIPATION SECTION — IMPORTANT:
  - For each participation entry, write a concise 1 sentence "summary" using EXACT WORDS from the source report.
  - Include any notable achievements (awards, certifications, publications).

OUTPUT SCHEMA — return exactly this structure, omitting any key whose section has no data:

{
  "report_date": "YYYY-MM-DD",
  "attendance": {
    "departments": [
      {"dept": "string", "on_rolls": int, "absent": int, "present": int, "percentage": float | null}
    ],
    "library": {
      "on_rolls": int, "absent_with_leave": int, "absent_without_leave": int, "present": int
    }
  },
  "infrastructure_issues": [
    {
      "dept": "string",
      "description": "string",
      "reported_on": "string",
      "status": "pending",
      "remarks": "string | null"
    }
  ],
  "department_highlights": [
    {
      "dept": "string (full department name from source)",
      "dept_code": "string (short code: cse, ece, etc.)",
      "events": [
        {
          "name": "string (exact name from source report)",
          "summary": "string (1-2 sentence description using source wording)",
          "importance": "high | medium | low",
          "date": "string",
          "duration": "string",
          "participants_internal": int | null,
          "participants_external": int | null,
          "resource_person": "string | null"
        }
      ],
      "other_matters": ["string (exact description from source)"]
    }
  ],
  "staff_participation": [
    {"name": "string", "dept": "string", "event": "string", "role": "string", "date": "string", "venue": "string | null", "summary": "string (1 sentence using source wording)"}
  ],
  "student_participation": [
    {"name": "string", "dept": "string", "event": "string", "achievement": "string", "date": "string", "summary": "string (1 sentence using source wording)"}
  ],
  "staff_changes": [
    {
      "name": "string",
      "dept": "string",
      "designation": "string",
      "type": "joined | left",
      "date": "string"
    }
  ],
  "classwork_adjustments": [
    {"dept": "string", "count": int}
  ],
  "incidents": [
    {
      "dept": "string",
      "type": "staff | student",
      "name": "string",
      "id": "string | null",
      "brief": "string",
      "remarks": "string | null"
    }
  ],
  "library_transactions": {
    "books_issued": int | null,
    "books_returned": int | null,
    "visitors_lirc": int | null,
    "visitors_evening_5_to_8": int | null,
    "visitors_digital": int | null,
    "show_and_tell_visitors": int | null,
    "cvpc_visitors": int | null
  },
  "library_services": {
    "plagiarism_checks": int | null,
    "show_and_tell": int | null,
    "patent_searches": int | null,
    "scopus_searches": int | null,
    "grammarly_usage": int | null,
    "duplicate_id_cards": int | null
  }
}

For any numeric field where the source value is missing, blank, or unclear — use null. Never guess a number."""


VERIFY_SYSTEM_PROMPT = """You are a fact-checker for an AI-generated report.
Compare the consolidated JSON output against the original source department data.
Find any number, name, or date in the JSON that cannot be traced to the source data.

Return ONLY a JSON array. Empty array [] if no issues found.
Each issue must be: {"field": "path.to.field", "value": "the suspicious value", "issue": "brief reason"}

Do not flag paraphrasing or style — only flag facts that contradict or are absent from the source."""


def consolidate(report_date: str, dept_reports: list[dict]) -> dict:
    """
    Consolidate department reports into a single structured JSON.
    Uses chunking to avoid LLM output truncation on large inputs.
    """
    final_report = {
        "report_date": report_date,
        "attendance": {"departments": [], "library": None},
        "department_highlights": [],
        "staff_participation": [],
        "student_participation": [],
        "staff_changes": [],
        "classwork_adjustments": [],
        "incidents": [],
        "infrastructure_issues": [],
        "library_transactions": {},
        "library_services": {},
    }

    chunk_size = 5
    for i in range(0, len(dept_reports), chunk_size):
        chunk = dept_reports[i:i + chunk_size]
        user_message = _build_user_message(report_date, chunk)
        try:
            raw = _llm_call(SYSTEM_PROMPT, user_message)
            parsed = _parse_json(raw, context=f"consolidation chunk {i}")
            
            if not isinstance(parsed, dict):
                continue
                
            # Merge lists
            list_keys = [
                "department_highlights", "staff_participation",
                "student_participation", "staff_changes",
                "classwork_adjustments", "incidents", "infrastructure_issues"
            ]
            for key in list_keys:
                if key in parsed and isinstance(parsed[key], list):
                    final_report[key].extend(parsed[key])
                    
            # Merge attendance
            if "attendance" in parsed and isinstance(parsed["attendance"], dict):
                att = parsed["attendance"]
                if "departments" in att and isinstance(att["departments"], list):
                    final_report["attendance"]["departments"].extend(att["departments"])
                if "library" in att and att["library"]:
                    if any(v is not None for v in att["library"].values()):
                        final_report["attendance"]["library"] = att["library"]
                        
            # Merge library sections
            if "library_transactions" in parsed and isinstance(parsed["library_transactions"], dict):
                if any(v is not None for v in parsed["library_transactions"].values()):
                    final_report["library_transactions"].update(parsed["library_transactions"])
                    
            if "library_services" in parsed and isinstance(parsed["library_services"], dict):
                if any(v is not None for v in parsed["library_services"].values()):
                    final_report["library_services"].update(parsed["library_services"])
                    
        except Exception as e:
            print(f"[WARNING] Skipping failed chunk processing {i}: {e}")

    return final_report


def verify_facts(consolidated: dict, dept_reports: list[dict]) -> list[dict]:
    """
    Verify consolidated report against source data.
    Returns list of issues found (empty list if clean).
    """
    source_text = "\n\n".join(
        f"=== {r['dept_name']} ===\n{r['text']}"
        for r in dept_reports
    )
    user_message = f"""SOURCE DATA:
{source_text}

CONSOLIDATED JSON:
{json.dumps(consolidated, indent=2)}
"""
    raw = _llm_call(VERIFY_SYSTEM_PROMPT, user_message)
    issues = _parse_json(raw, context="verification")

    if isinstance(issues, list) and issues:
        consolidated["_fact_issues"] = issues

    return issues


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_user_message(report_date: str, dept_reports: list[dict]) -> str:
    sections = "\n\n".join(
        f"=== DEPARTMENT: {r['dept_name']} (code: {r['dept_code']}) ===\n{r['text']}"
        for r in dept_reports
    )
    return f"Consolidate the following department reports for {report_date}.\n\n{sections}"


def _llm_call(system: str, user: str) -> str:
    """Call Gemini API and return the text response."""
    response = client.models.generate_content(
        model=MODEL,
        contents=user,
        config=genai.types.GenerateContentConfig(
            system_instruction=system,
            temperature=0,
            max_output_tokens=8192,
        ),
    )
    return response.text


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