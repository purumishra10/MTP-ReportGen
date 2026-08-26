import os
import json as _json
from typing import Optional

from backend.database import get_records_by_date, get_executive_summary
from backend.services.ai_service import consolidate
from backend.services.report_generator import generate_docx
from backend.batch_processor import DEPT_MAPPING


def _dept_name_from_code(code: str) -> str:
    return DEPT_MAPPING.get((code or "").lower(), (code or "").upper())


def _cell(val) -> str:
    if val is None:
        return ""
    return str(val).strip()


def _safe_int(val):
    if val is None:
        return None
    try:
        s = str(val).strip().replace(",", "")
        if not s:
            return None
        return int(float(s))
    except (ValueError, TypeError):
        return None


def _row_has_data(row: dict) -> bool:
    for k, v in (row or {}).items():
        kl = k.lower()
        if "s.no" in kl or "s. no" in kl or kl == "s.no.":
            continue
        if _cell(v):
            return True
    return False


def _row_as_text(row: dict) -> str:
    parts = []
    for k, v in (row or {}).items():
        kl = k.lower()
        if "s.no" in kl or "s. no" in kl:
            continue
        text = _cell(v)
        if text:
            parts.append(f"{k}: {text}")
    return " | ".join(parts)


def _parse_student_attendance_row(row: dict):
    entry = {}
    for k, v in row.items():
        kl = k.lower()
        if "year" in kl:
            entry["year"] = _cell(v)
        elif "present" in kl:
            entry["present"] = _safe_int(v)
        elif "absent" in kl:
            entry["absent"] = _safe_int(v)
        elif "roll" in kl:
            entry["on_rolls"] = _safe_int(v)
    if not entry.get("year"):
        return None
    rolls = entry.get("on_rolls")
    present = entry.get("present")
    absent = entry.get("absent")
    if present is None and rolls is not None and absent is not None:
        entry["present"] = rolls - absent
    elif absent is None and rolls is not None and present is not None:
        entry["absent"] = rolls - present
    return entry


def _flatten_staff_attendance(attendance_data: dict, dept_name: str) -> Optional[dict]:
    teaching = attendance_data.get("staff", {}).get("teaching") or {}
    non_teaching = attendance_data.get("staff", {}).get("non_teaching") or {}

    t_rolls = teaching.get("on_rolls") or 0
    nt_rolls = non_teaching.get("on_rolls") or 0
    t_abs = teaching.get("absent") or 0
    nt_abs = non_teaching.get("absent") or 0
    total_rolls = t_rolls + nt_rolls
    total_absent = t_abs + nt_abs

    if total_rolls == 0 and total_absent == 0:
        return None

    present = total_rolls - total_absent
    percentage = round(present / total_rolls * 100, 1) if total_rolls else None
    return {
        "dept": dept_name,
        "dept_code": attendance_data.get("dept_code"),
        "teaching_count": t_rolls or None,
        "non_teaching_count": nt_rolls or None,
        "on_rolls": total_rolls,
        "absent": total_absent,
        "present": present,
        "percentage": percentage,
    }


def _infer_staff_change_type(row: dict) -> str:
    combined = " ".join(_cell(v) for v in row.values()).lower()
    if any(w in combined for w in ("left", "leaving", "resign", "relieved", "retired")):
        return "left"
    return "joined"


def _infer_mtp_activity_type(raw: str) -> str:
    t = (raw or "").lower()
    if "ppt" in t or "pre-placement" in t or "pre placement" in t:
        return "ppt"
    if "aptitude" in t or "test" in t:
        return "aptitude_test"
    if "mock" in t:
        return "mock_interview"
    if "intern" in t:
        return "internship"
    if "train" in t:
        return "training"
    if "drive" in t or "placement" in t:
        return "placement_drive"
    return "other" if not t else "other"


def _parse_library_particulars(rows: list) -> tuple:
    transactions = {}
    services = {}
    TXN_RULES = [
        (lambda l: "books issued" in l or "check out" in l, "books_issued"),
        (lambda l: "books returned" in l or "check in" in l, "books_returned"),
        (lambda l: "evening" in l or "5 pm" in l or "5pm" in l, "visitors_evening_5_to_8"),
        (lambda l: "digital" in l, "visitors_digital"),
        (lambda l: "show" in l and "tell" in l and "visitor" in l, "show_and_tell_visitors"),
        (lambda l: "cvpc" in l, "cvpc_visitors"),
        (lambda l: "visitor" in l or "lirc" in l, "visitors_lirc"),
    ]
    SVC_RULES = [
        (lambda l: "plagiarism" in l or "turnitin" in l, "plagiarism_checks"),
        (lambda l: "show" in l and "tell" in l, "show_and_tell"),
        (lambda l: "patent" in l, "patent_searches"),
        (lambda l: "scopus" in l, "scopus_searches"),
        (lambda l: "grammarly" in l, "grammarly_usage"),
        (lambda l: "duplicate" in l or "id card" in l, "duplicate_id_cards"),
    ]
    for row in rows:
        label = ""
        value = None
        for k, v in row.items():
            kl = k.lower()
            if "s.no" in kl or "s. no" in kl:
                continue
            if "particular" in kl or "description" in kl:
                label = _cell(v).lower()
            elif "no" in kl or "count" in kl:
                value = _safe_int(v)
            elif not label:
                label = _cell(v).lower()
            elif value is None:
                value = _safe_int(v)
        if not label or value is None:
            continue
        matched = False
        for pred, key in SVC_RULES:
            if pred(label):
                services[key] = value
                matched = True
                break
        if matched:
            continue
        for pred, key in TXN_RULES:
            if pred(label):
                transactions[key] = value
                break
    return transactions, services


def _parse_sections_to_structured(sections: list, dept_code: str, dept_name: str) -> dict:
    """
    Map portal structured sections JSON into the dict format that
    consolidate() / structured_extractor expects.
    """
    result = {
        "dept_code": dept_code,
        "dept_name": dept_name,
        "attendance": None,
        "infrastructure_issues": [],
        "staff_changes": [],
        "incidents": [],
        "classwork_adjustment_count": 0,
        "events": [],
        "events_text": "",
        "staff_participation_text": "",
        "student_participation_text": "",
        "staff_participation_rows": [],
        "student_participation_rows": [],
        "loose_paragraphs": "",
        "mtp_narrative": "",
        "mtp_batch_pills": "",
        "mtp_summary": [],
        "library_attendance": None,
        "library_transactions": {},
        "library_services": {},
        "student_attendance": {"btech": [], "mtech": [], "minor": []},
    }

    attendance_data = {
        "dept": dept_name,
        "dept_code": dept_code,
        "staff": {"teaching": {}, "non_teaching": {}},
        "students": {"btech": [], "mtech": [], "minor": []},
    }
    has_staff_attendance = False
    event_lines = []
    staff_part_lines = []
    student_part_lines = []
    mtp_lines = []

    for sec in sections:
        title = _cell(sec.get("title"))
        is_nil = bool(sec.get("nil"))
        rows = [r for r in (sec.get("rows") or []) if isinstance(r, dict) and _row_has_data(r)]
        title_lower = title.lower()

        if is_nil or not rows:
            continue

        # ── Library-style staff attendance (no Category column) ──
        if "staff attendance" in title_lower:
            sample_keys = " ".join(rows[0].keys()).lower()
            if ("absent with" in sample_keys) or ("on roll" in sample_keys and "category" not in sample_keys):
                lib = {"on_rolls": None, "absent_with_leave": None, "absent_without_leave": None, "present": None}
                row = rows[0]
                for k, v in row.items():
                    kl = k.lower()
                    if "without" in kl:
                        lib["absent_without_leave"] = _safe_int(v)
                    elif "with" in kl and "leave" in kl:
                        lib["absent_with_leave"] = _safe_int(v)
                    elif "present" in kl:
                        lib["present"] = _safe_int(v)
                    elif "roll" in kl:
                        lib["on_rolls"] = _safe_int(v)
                if any(v is not None for v in lib.values()):
                    result["library_attendance"] = lib
                continue

            has_staff_attendance = True
            for row in rows:
                cat = ""
                on_rolls = None
                absent = None
                remarks = ""
                for k, v in row.items():
                    kl = k.lower()
                    if "category" in kl:
                        cat = _cell(v).lower()
                    elif "absent" in kl:
                        absent = _safe_int(v)
                    elif "roll" in kl:
                        on_rolls = _safe_int(v)
                    elif "remark" in kl or "detail" in kl:
                        remarks = _cell(v)

                entry = {"on_rolls": on_rolls, "absent": absent, "remarks": remarks}
                if "non" in cat:
                    attendance_data["staff"]["non_teaching"] = entry
                else:
                    attendance_data["staff"]["teaching"] = entry

        elif "b.tech" in title_lower and "attendance" in title_lower:
            for row in rows:
                year_entry = _parse_student_attendance_row(row)
                if year_entry:
                    attendance_data["students"]["btech"].append(year_entry)
                    result["student_attendance"]["btech"].append(year_entry)

        elif "m.tech" in title_lower and "attendance" in title_lower:
            for row in rows:
                year_entry = _parse_student_attendance_row(row)
                if year_entry:
                    attendance_data["students"]["mtech"].append(year_entry)
                    result["student_attendance"]["mtech"].append(year_entry)

        elif "minor" in title_lower and "attendance" in title_lower:
            for row in rows:
                year_entry = _parse_student_attendance_row(row)
                if year_entry:
                    attendance_data["students"]["minor"].append(year_entry)
                    result["student_attendance"]["minor"].append(year_entry)

        elif "infrastructure" in title_lower or "maintenance" in title_lower:
            for row in rows:
                issue = {"dept": dept_name}
                for k, v in row.items():
                    kl = k.lower()
                    if "description" in kl or "problem" in kl:
                        issue["description"] = _cell(v)
                    elif "reported" in kl:
                        issue["reported_on"] = _cell(v)
                    elif "attended" in kl:
                        issue["attended_on"] = _cell(v)
                    elif "completed" in kl:
                        issue["completed_on"] = _cell(v)
                    elif "remark" in kl:
                        issue["remarks"] = _cell(v)
                if not issue.get("description"):
                    continue
                completed = issue.get("completed_on") or ""
                if completed and completed.lower() not in {"", "-", "—", "nil", "na", "n/a"}:
                    issue["status"] = "resolved"
                    continue
                issue["status"] = "pending"
                result["infrastructure_issues"].append(issue)

        elif "batch pill" in title_lower:
            headers = list(rows[0].keys())
            values = [_cell(rows[0].get(h)) for h in headers]
            # Prefer a header row of branch codes if the first row is values-only
            result["mtp_batch_pills"] = (
                "[Batch Pills Open Summary]\n"
                + " | ".join(headers) + "\n"
                + " | ".join(values)
            )

        elif "mtp" in title_lower and "attendance" not in title_lower:
            for row in rows:
                item = {
                    "company": None,
                    "activity_type": "other",
                    "summary": "",
                    "student_count": None,
                    "batch": None,
                    "status": None,
                }
                details = []
                for k, v in row.items():
                    kl = k.lower()
                    text = _cell(v)
                    if not text:
                        continue
                    if "company" in kl or "organization" in kl:
                        item["company"] = text
                    elif "activity" in kl or "type" in kl:
                        item["activity_type"] = _infer_mtp_activity_type(text)
                        details.append(text)
                    elif "batch" in kl or "target" in kl or "dept" in kl:
                        item["batch"] = text
                    elif "student" in kl or "no." in kl or "no of" in kl:
                        item["student_count"] = _safe_int(v)
                    elif "status" in kl or "outcome" in kl:
                        item["status"] = text
                    elif "remark" in kl or "detail" in kl:
                        details.append(text)
                    else:
                        details.append(f"{k}: {text}")
                item["summary"] = " — ".join(d for d in details if d) or _row_as_text(row)
                if item["company"] or item["summary"]:
                    result["mtp_summary"].append(item)
                    mtp_lines.append(_row_as_text(row))
            if mtp_lines:
                result["mtp_narrative"] = "\n".join(mtp_lines)

        elif "event" in title_lower or "workshop" in title_lower or "seminar" in title_lower:
            for row in rows:
                event = {
                    "name": "",
                    "duration": "",
                    "for_whom": "",
                    "participants_internal": None,
                    "resource_person": "",
                    "remarks": "",
                    "summary": "",
                    "importance": "medium",
                    "date": None,
                }
                for k, v in row.items():
                    kl = k.lower()
                    text = _cell(v)
                    if "s.no" in kl:
                        continue
                    if "event" in kl or "name" in kl:
                        event["name"] = text or event["name"]
                    elif "duration" in kl:
                        event["duration"] = text
                    elif "whom" in kl:
                        event["for_whom"] = text
                    elif "participant" in kl:
                        event["participants_internal"] = _safe_int(v)
                    elif "resource" in kl or "faculty" in kl:
                        event["resource_person"] = text
                    elif "remark" in kl:
                        event["remarks"] = text
                    elif "date" in kl:
                        event["date"] = text
                if not event["name"]:
                    event["name"] = _row_as_text(row) or "Untitled Event"
                summary_bits = [event["name"]]
                if event["for_whom"]:
                    summary_bits.append(f"For: {event['for_whom']}")
                if event["remarks"]:
                    summary_bits.append(event["remarks"])
                event["summary"] = ". ".join(summary_bits)
                result["events"].append(event)
                event_lines.append(_row_as_text(row))
            if event_lines:
                result["events_text"] = "\n".join(event_lines)

        elif "participation" in title_lower:
            combined = "staff" in title_lower and "student" in title_lower
            for row in rows:
                parsed = {
                    "name": "",
                    "dept": dept_name,
                    "event": "",
                    "role": "",
                    "date": None,
                    "summary": "",
                    "achievement": "",
                }
                bucket = None
                for k, v in row.items():
                    kl = k.lower()
                    text = _cell(v)
                    if "s.no" in kl:
                        continue
                    if kl == "name" or (kl.startswith("name") and "event" not in kl):
                        parsed["name"] = text
                    elif "event" in kl:
                        parsed["event"] = text
                    elif "status" in kl or "achievement" in kl:
                        parsed["role"] = text
                        parsed["achievement"] = text
                    elif "role" in kl or "category" in kl:
                        parsed["role"] = text
                        if "student" in text.lower():
                            bucket = "student"
                        elif "staff" in text.lower() or "faculty" in text.lower():
                            bucket = "staff"
                    elif "date" in kl or "duration" in kl:
                        parsed["date"] = text
                parsed["summary"] = _row_as_text(row)
                if not parsed["name"] and not parsed["event"]:
                    continue

                if combined:
                    target = bucket or "staff"
                elif "student" in title_lower:
                    target = "student"
                else:
                    target = "staff"

                if target == "student":
                    result["student_participation_rows"].append(parsed)
                    student_part_lines.append(_row_as_text(row))
                else:
                    result["staff_participation_rows"].append(parsed)
                    staff_part_lines.append(_row_as_text(row))

            if staff_part_lines:
                result["staff_participation_text"] = "\n".join(staff_part_lines)
            if student_part_lines:
                result["student_participation_text"] = "\n".join(student_part_lines)

        elif "staff" in title_lower and ("join" in title_lower or "left" in title_lower):
            for row in rows:
                change = {"dept": dept_name, "type": _infer_staff_change_type(row)}
                for k, v in row.items():
                    kl = k.lower()
                    if "name" in kl:
                        change["name"] = _cell(v)
                    elif "designation" in kl:
                        change["designation"] = _cell(v)
                    elif "date" in kl or "joining" in kl or "leaving" in kl:
                        change["date"] = _cell(v)
                    elif "remark" in kl:
                        change["remarks"] = _cell(v)
                if change.get("name"):
                    result["staff_changes"].append(change)

        elif "classwork" in title_lower or "adjustment" in title_lower:
            result["classwork_adjustment_count"] = len(rows)

        elif "incident" in title_lower:
            for row in rows:
                incident = {"dept": dept_name, "type": "student"}
                for k, v in row.items():
                    kl = k.lower()
                    if kl == "name" or ( "name" in kl and "event" not in kl):
                        incident["name"] = _cell(v)
                    elif "r. no" in kl or "id no" in kl or "roll" in kl:
                        incident["id"] = _cell(v)
                    elif "statement" in kl or "brief" in kl:
                        incident["brief"] = _cell(v)
                        incident["description"] = _cell(v)
                    elif "remark" in kl:
                        incident["remarks"] = _cell(v)
                if incident.get("brief") or incident.get("name"):
                    result["incidents"].append(incident)

        elif "library" in title_lower and ("service" in title_lower or "transaction" in title_lower or "particular" in title_lower):
            txn, svc = _parse_library_particulars(rows)
            result["library_transactions"].update(txn)
            result["library_services"].update(svc)

        elif "student attendance" in title_lower or "b.tech student" in title_lower or "m.tech student" in title_lower:
            # Explicitly drop student attendance so it NEVER leaks into loose_paragraphs
            continue

        else:
            # Unclassified tables only go to LLM if they have real content
            extra = "\n".join(_row_as_text(r) for r in rows if _row_has_data(r))
            if extra:
                labeled = f"[Other — {title}]\n{extra}"
                result["loose_paragraphs"] = (
                    (result["loose_paragraphs"] + "\n\n" + labeled).strip()
                    if result["loose_paragraphs"] else labeled
                )

    if has_staff_attendance:
        flat = _flatten_staff_attendance(attendance_data, dept_name)
        result["attendance"] = flat
        # Keep nested students on the same object for consolidate()
        if flat is not None:
            result["attendance"]["_students"] = attendance_data["students"]
        else:
            result["attendance"] = {"dept": dept_name, "_students": attendance_data["students"]}

    # Students may exist without staff attendance
    if not result["attendance"] and any(result["student_attendance"].values()):
        result["attendance"] = {"dept": dept_name, "dept_code": dept_code, "_students": result["student_attendance"]}

    return result


def generate_from_portal(date_str: str) -> Optional[bytes]:
    """
    Generates a consolidated report from the portal SQLite database.
    """
    records = get_records_by_date(date_str)
    approved_records = [r for r in records if r["status"] == "approved"]

    if not approved_records:
        raise ValueError(f"No approved department submissions found for {date_str}.")

    dept_reports = []
    for record in approved_records:
        dept_code = (record["department"] or "").lower()
        dept_name = _dept_name_from_code(dept_code)
        raw_content = record["content"] or ""

        structured_data = None
        parsed_obj = None
        if raw_content.strip().startswith("{"):
            try:
                parsed_obj = _json.loads(raw_content)
                if isinstance(parsed_obj, dict) and "sections" in parsed_obj:
                    structured_data = _parse_sections_to_structured(
                        parsed_obj["sections"], dept_code, dept_name
                    )
            except Exception as e:
                print(f"[WARN] Failed to parse structured JSON for {dept_code}: {e}")

        if structured_data:
            if isinstance(parsed_obj, dict) and parsed_obj.get("text"):
                if not structured_data.get("events_text") and not structured_data.get("mtp_narrative"):
                    structured_data["loose_paragraphs"] = (
                        (structured_data.get("loose_paragraphs") or "")
                        + "\n"
                        + parsed_obj["text"]
                    ).strip()
            dept_reports.append(structured_data)
        else:
            text = raw_content
            if parsed_obj is None and raw_content.strip().startswith("{"):
                try:
                    parsed_obj = _json.loads(raw_content)
                except Exception:
                    parsed_obj = None
            if isinstance(parsed_obj, dict) and "text" in parsed_obj:
                text = parsed_obj["text"]
            dept_reports.append({
                "dept_code": dept_code,
                "dept_name": dept_name,
                "text": text,
                "loose_paragraphs": text,
            })

    print(f"[INFO] Running AI consolidation for {date_str} from portal database ({len(dept_reports)} depts)...")
    final_json = consolidate(date_str, dept_reports)

    exec_summary_record = get_executive_summary(date_str)
    if exec_summary_record and exec_summary_record.get("content"):
        final_json["executive_summary"] = exec_summary_record["content"]

    output_dir = "generated_reports"
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"daily_report_{date_str}.docx")
    return generate_docx(final_json, output_path=output_path)
