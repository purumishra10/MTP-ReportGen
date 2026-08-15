import os
import io
import json as _json
import re
from typing import Optional
from datetime import datetime

from backend.database import get_records_by_date, get_executive_summary
from backend.services.ai_service import consolidate
from backend.services.report_generator import generate_docx
from backend.services import supabase_client

# Dictionary mapping from short code to full name for the final docx
from backend.batch_processor import DEPT_MAPPING

def _dept_name_from_code(code: str) -> str:
    return DEPT_MAPPING.get(code.lower(), code.upper())


def _parse_sections_to_structured(sections: list, dept_code: str, dept_name: str) -> dict:
    """
    Map the portal's structured sections JSON into the dict format that
    consolidate() / structured_extractor expects.
    
    Each section has a title, nil flag, and rows (list of dicts with column headers as keys).
    """
    result = {
        "dept_code": dept_code,
        "dept_name": dept_name,
        "attendance": None,
        "infrastructure_issues": [],
        "staff_changes": [],
        "incidents": [],
        "classwork_adjustment_count": 0,
        "events_text": "",
        "staff_participation_text": "",
        "student_participation_text": "",
        "loose_paragraphs": "",
    }

    attendance_data = {
        "dept": dept_name,
        "dept_code": dept_code,
        "staff": {"teaching": {}, "non_teaching": {}},
        "students": {"btech": [], "mtech": [], "minor": []},
    }
    has_attendance = False

    for sec in sections:
        title = (sec.get("title") or "").strip()
        is_nil = sec.get("nil", False)
        rows = sec.get("rows", [])
        title_lower = title.lower()

        if is_nil or not rows:
            continue

        # ── Staff Attendance ──
        if "staff attendance" in title_lower:
            has_attendance = True
            for row in rows:
                cat = ""
                on_rolls = None
                absent = None
                remarks = ""
                for k, v in row.items():
                    kl = k.lower()
                    if "category" in kl:
                        cat = (v or "").strip().lower()
                    elif "on rolls" in kl or "rolls" == kl:
                        on_rolls = _safe_int(v)
                    elif "absent" in kl:
                        absent = _safe_int(v)
                    elif "remark" in kl or "detail" in kl:
                        remarks = (v or "").strip()
                
                entry = {"on_rolls": on_rolls, "absent": absent, "remarks": remarks}
                if "non" in cat:
                    attendance_data["staff"]["non_teaching"] = entry
                else:
                    attendance_data["staff"]["teaching"] = entry

        # ── B.Tech Students Attendance ──
        elif "b.tech" in title_lower and "attendance" in title_lower:
            has_attendance = True
            for row in rows:
                year_entry = _parse_student_attendance_row(row)
                if year_entry:
                    attendance_data["students"]["btech"].append(year_entry)

        # ── M.Tech Students Attendance ──
        elif "m.tech" in title_lower and "attendance" in title_lower:
            has_attendance = True
            for row in rows:
                year_entry = _parse_student_attendance_row(row)
                if year_entry:
                    attendance_data["students"]["mtech"].append(year_entry)

        # ── Minor Degree Students Attendance ──
        elif "minor" in title_lower and "attendance" in title_lower:
            has_attendance = True
            for row in rows:
                year_entry = _parse_student_attendance_row(row)
                if year_entry:
                    attendance_data["students"]["minor"].append(year_entry)

        # ── Infrastructure Issues ──
        elif "infrastructure" in title_lower or "maintenance" in title_lower:
            for row in rows:
                issue = {}
                for k, v in row.items():
                    kl = k.lower()
                    if "description" in kl or "problem" in kl:
                        issue["description"] = (v or "").strip()
                    elif "reported" in kl:
                        issue["reported_on"] = (v or "").strip()
                    elif "attended" in kl:
                        issue["attended_on"] = (v or "").strip()
                    elif "completed" in kl:
                        issue["completed_on"] = (v or "").strip()
                    elif "remark" in kl:
                        issue["remarks"] = (v or "").strip()
                if issue.get("description"):
                    issue["dept"] = dept_name
                    result["infrastructure_issues"].append(issue)

        # ── Events / Workshops ──
        elif "event" in title_lower or "workshop" in title_lower or "seminar" in title_lower:
            lines = []
            for row in rows:
                parts = []
                for k, v in row.items():
                    kl = k.lower()
                    if "s.no" in kl or "s. no" in kl:
                        continue
                    if v and str(v).strip():
                        parts.append(f"{k}: {v.strip()}")
                if parts:
                    lines.append(" | ".join(parts))
            if lines:
                result["events_text"] = "\n".join(lines)

        # ── Participation by Staff ──
        elif "participation" in title_lower and "staff" in title_lower:
            lines = []
            for row in rows:
                parts = []
                for k, v in row.items():
                    kl = k.lower()
                    if "s.no" in kl or "s. no" in kl:
                        continue
                    if v and str(v).strip():
                        parts.append(f"{k}: {v.strip()}")
                if parts:
                    lines.append(" | ".join(parts))
            if lines:
                result["staff_participation_text"] = "\n".join(lines)

        # ── Participation by Students ──
        elif "participation" in title_lower and "student" in title_lower:
            lines = []
            for row in rows:
                parts = []
                for k, v in row.items():
                    kl = k.lower()
                    if "s.no" in kl or "s. no" in kl:
                        continue
                    if v and str(v).strip():
                        parts.append(f"{k}: {v.strip()}")
                if parts:
                    lines.append(" | ".join(parts))
            if lines:
                result["student_participation_text"] = "\n".join(lines)

        # ── Staff Joined or Left ──
        elif "staff" in title_lower and ("join" in title_lower or "left" in title_lower):
            for row in rows:
                change = {"dept": dept_name}
                for k, v in row.items():
                    kl = k.lower()
                    if "name" in kl and "faculty" in kl:
                        change["name"] = (v or "").strip()
                    elif "name" in kl:
                        change["name"] = (v or "").strip()
                    elif "designation" in kl:
                        change["designation"] = (v or "").strip()
                    elif "date" in kl or "joining" in kl or "leaving" in kl:
                        change["date"] = (v or "").strip()
                    elif "remark" in kl:
                        change["remarks"] = (v or "").strip()
                if change.get("name"):
                    result["staff_changes"].append(change)

        # ── Classwork Adjustment ──
        elif "classwork" in title_lower or "adjustment" in title_lower:
            # Count non-empty rows as adjustments
            count = 0
            for row in rows:
                has_data = any(
                    v and str(v).strip() 
                    for k, v in row.items() 
                    if "s.no" not in k.lower() and "s. no" not in k.lower()
                )
                if has_data:
                    count += 1
            result["classwork_adjustment_count"] = count

        # ── Incidents ──
        elif "incident" in title_lower:
            for row in rows:
                incident = {"dept": dept_name}
                for k, v in row.items():
                    kl = k.lower()
                    if "name" in kl:
                        incident["name"] = (v or "").strip()
                    elif "r. no" in kl or "id no" in kl:
                        incident["id"] = (v or "").strip()
                    elif "statement" in kl or "brief" in kl:
                        incident["description"] = (v or "").strip()
                    elif "remark" in kl:
                        incident["remarks"] = (v or "").strip()
                if incident.get("description") or incident.get("name"):
                    result["incidents"].append(incident)

    if has_attendance:
        result["attendance"] = attendance_data

    return result


def _parse_student_attendance_row(row: dict) -> dict:
    """Parse a single student attendance row (Year, Rolls, Present, Absent)."""
    entry = {}
    for k, v in row.items():
        kl = k.lower()
        if "year" in kl:
            entry["year"] = (v or "").strip()
        elif "rolls" in kl:
            entry["on_rolls"] = _safe_int(v)
        elif "present" in kl:
            entry["present"] = _safe_int(v)
        elif "absent" in kl:
            entry["absent"] = _safe_int(v)
    return entry if entry.get("year") else None


def _safe_int(val) -> int:
    """Safely convert a value to int, returning None if not possible."""
    if val is None:
        return None
    try:
        s = str(val).strip()
        if not s:
            return None
        return int(s)
    except (ValueError, TypeError):
        return None


def generate_from_portal(date_str: str) -> Optional[bytes]:
    """
    Generates a consolidated report specifically pulling from the portal's SQLite database 
    rather than from uploaded files.
    
    1. Fetch all 'approved' mtp_records for the given date
    2. Parse the structured JSON sections into the format consolidate() expects
    3. Run AI consolidation
    4. Fetch executive summary
    5. Generate the DOCX file
    """
    records = get_records_by_date(date_str)
    
    # Filter for only approved reports
    approved_records = [r for r in records if r["status"] == "approved"]
    
    if not approved_records:
        raise ValueError(f"No approved department submissions found for {date_str}.")

    # Format for AI service — parse structured sections into consolidate-compatible dicts
    dept_reports = []
    for record in approved_records:
        dept_code = record["department"]
        dept_name = _dept_name_from_code(dept_code)
        
        raw_content = record["content"] or ""
        
        # Try to parse structured JSON first
        structured_data = None
        if raw_content.strip().startswith("{"):
            try:
                parsed_obj = _json.loads(raw_content)
                if isinstance(parsed_obj, dict) and "sections" in parsed_obj:
                    # Map structured sections to the format consolidate() expects
                    structured_data = _parse_sections_to_structured(
                        parsed_obj["sections"], dept_code, dept_name
                    )
            except Exception as e:
                print(f"[WARN] Failed to parse structured JSON for {dept_code}: {e}")
        
        if structured_data:
            # If we also have a text field, add it as loose_paragraphs for LLM context
            if raw_content.strip().startswith("{"):
                try:
                    parsed_obj = _json.loads(raw_content)
                    if isinstance(parsed_obj, dict) and "text" in parsed_obj:
                        text_content = parsed_obj["text"]
                        # Only use text for narrative sections the parser might have missed
                        if not structured_data.get("events_text") and not structured_data.get("staff_participation_text"):
                            structured_data["loose_paragraphs"] = text_content
                except Exception:
                    pass
            dept_reports.append(structured_data)
        else:
            # Fallback: plain text submission
            text = raw_content
            if raw_content.strip().startswith("{"):
                try:
                    parsed_obj = _json.loads(raw_content)
                    if isinstance(parsed_obj, dict) and "text" in parsed_obj:
                        text = parsed_obj["text"]
                except Exception:
                    text = raw_content
            
            dept_reports.append({
                "dept_code": dept_code,
                "dept_name": dept_name,
                "text": text,
                "loose_paragraphs": text,
            })
        
    print(f"[INFO] Running AI consolidation for {date_str} from portal database ({len(dept_reports)} depts)...")
    
    # Run the same AI logic as main branch
    final_json = consolidate(date_str, dept_reports)
    
    # Add executive summary if present
    exec_summary_record = get_executive_summary(date_str)
    if exec_summary_record and exec_summary_record.get("content"):
        final_json["executive_summary"] = exec_summary_record["content"]

    # Generate the DOCX bytes
    docx_bytes = generate_docx(final_json)
    
    # Supabase optional upload
    if supabase_client.is_enabled():
        try:
            dept_codes = [r["dept_code"] for r in dept_reports]
            filename = f"daily_report_{date_str}.docx"
            supabase_client.save_report(
                report_date=date_str,
                departments=dept_codes,
                docx_bytes=docx_bytes,
                filename=filename,
                metadata={"source": "portal"}
            )
            print(f"[INFO] Uploaded portal report to Supabase: {date_str}")
        except Exception as e:
            print(f"[WARN] Supabase upload failed: {e}")
            
    return docx_bytes

