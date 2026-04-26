"""
Deterministic Structured Extractor
===================================
Reads DOCX tables directly and extracts structured data WITHOUT any LLM.
Uses header-matching (not position-based indexing) to handle varying table orders.

This eliminates number hallucination for: attendance, infrastructure, staff changes,
classwork adjustments, incidents, and library data.

Narrative sections (events, participation, other matters) are returned as raw text
for LLM summarization.
"""

import io
import os
import re
from typing import Optional

from docx import Document


# ── Header fingerprints for table identification ──────────────────────────────
# Each fingerprint is a set of keywords that MUST appear in the header row.
# We normalize headers to lowercase before matching.

FINGERPRINTS = {
    "attendance": {"on rolls", "absent"},
    "infrastructure": {"description", "reported"},
    "events": {"event", "duration"},
    "staff_participation": {"name", "event", "status"},
    "student_participation": {"name", "event", "status"},
    "staff_changes": {"name", "designation", "joining"},
    "classwork": {"dept", "subject", "adjusted"},
    "incidents": {"name", "brief", "remarks"},
    # Library-specific
    "library_transactions": {"particulars", "no"},
    "library_attendance": {"on roll", "absent", "present"},
}

# Sections whose data should be extracted deterministically (no LLM)
DETERMINISTIC_SECTIONS = {
    "attendance", "infrastructure", "staff_changes",
    "classwork", "incidents", "library_transactions", "library_attendance",
}

# Sections whose data goes to LLM for summarization
NARRATIVE_SECTIONS = {
    "events", "staff_participation", "student_participation",
}


def extract_structured_data(file_bytes: bytes, dept_code: str,
                            dept_name: str, is_library: bool = False) -> dict:
    """
    Extract structured data from a DOCX file.

    Returns a dict with:
    - Deterministically extracted sections (attendance, infra, etc.)
    - Raw text for narrative sections (events, participation)
    - Loose paragraphs as raw text
    """
    doc = Document(io.BytesIO(file_bytes))
    tables = doc.tables

    # Classify each table by matching its header row
    classified = _classify_tables(tables, is_library)

    result = {
        "dept_code": dept_code,
        "dept_name": dept_name,
        # Deterministic extractions
        "attendance": None,
        "infrastructure_issues": [],
        "staff_changes": [],
        "classwork_adjustment_count": 0,
        "incidents": [],
        # Library-specific
        "library_attendance": None,
        "library_transactions": {},
        "library_services": {},
        # Narrative text for LLM
        "events_text": "",
        "staff_participation_text": "",
        "student_participation_text": "",
        "other_matters_text": "",
        "loose_paragraphs": "",
    }

    # Track which participation table we've seen (first = staff, second = student)
    participation_count = 0

    for section_type, table in classified:
        if section_type == "attendance" and not is_library:
            result["attendance"] = _extract_attendance(table, dept_code, dept_name)
        elif section_type == "library_attendance" and is_library:
            result["library_attendance"] = _extract_library_attendance(table)
        elif section_type == "infrastructure":
            result["infrastructure_issues"] = _extract_infrastructure(table, dept_name)
        elif section_type == "staff_changes":
            result["staff_changes"] = _extract_staff_changes(table, dept_name)
        elif section_type == "classwork":
            result["classwork_adjustment_count"] = _count_non_empty_rows(table)
        elif section_type == "incidents":
            result["incidents"] = _extract_incidents(table, dept_name)
        elif section_type == "library_transactions":
            txn, svc = _extract_library_data(table)
            result["library_transactions"] = txn
            result["library_services"] = svc
        elif section_type == "events":
            result["events_text"] = _table_to_text("Events / Seminars / Workshops", table)
        elif section_type in ("staff_participation", "student_participation"):
            # Disambiguate: first occurrence = staff, second = student
            if participation_count == 0:
                result["staff_participation_text"] = _table_to_text("Participation by Staff", table)
            else:
                result["student_participation_text"] = _table_to_text("Participation by Students", table)
            participation_count += 1
        # Unclassified tables go to "other matters"
        elif section_type == "unknown":
            text = _table_to_text("Other", table)
            if text.strip() and _has_real_content(text):
                result["other_matters_text"] += text + "\n\n"

    # Extract loose paragraphs (free text outside tables)
    loose = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if text and len(text) > 10:
            loose.append(text)
    result["loose_paragraphs"] = "\n".join(loose) if loose else ""

    return result


# ── Table classification ─────────────────────────────────────────────────────

def _classify_tables(tables, is_library: bool) -> list[tuple[str, object]]:
    """Classify each table by matching header row against fingerprints."""
    classified = []
    participation_seen = 0

    for table in tables:
        header_text = _get_header_text(table)
        section_type = _match_fingerprint(header_text, is_library)

        # Handle dual participation tables (same headers, different meaning)
        if section_type == "staff_participation":
            if participation_seen == 0:
                section_type = "staff_participation"
            else:
                section_type = "student_participation"
            participation_seen += 1

        classified.append((section_type, table))

    return classified


def _get_header_text(table) -> str:
    """Get all text from the first two rows of a table, normalized."""
    texts = []
    for row_idx, row in enumerate(table.rows[:2]):
        for cell in row.cells:
            t = cell.text.strip().lower()
            if t:
                texts.append(t)
    return " ".join(texts)


def _match_fingerprint(header_text: str, is_library: bool) -> str:
    """Match header text against known fingerprints.
    
    ORDER MATTERS: More specific patterns must be checked before generic ones.
    Participation tables have 'event' in their headers too, so they must be
    checked BEFORE the events fingerprint.
    """
    # Library attendance has different column names
    if is_library and "on roll" in header_text and "present" in header_text:
        return "library_attendance"

    # Library transactions
    if "particulars" in header_text:
        return "library_transactions"

    # Standard attendance — must have On Rolls + Absent + some dept/category indicator
    if "on rolls" in header_text and "absent" in header_text:
        if "category" in header_text or "teaching" in header_text or "dept" in header_text:
            return "attendance"

    # Infrastructure
    if "description" in header_text and ("reported" in header_text or "problem" in header_text):
        return "infrastructure"

    # Participation BEFORE Events — participation has "status" + "delegate/paper/speaker"
    # but does NOT have "duration" or "participants" or "seminar"
    if "status" in header_text and ("delegate" in header_text or "paper" in header_text or "speaker" in header_text):
        return "staff_participation"  # Will be disambiguated by counter

    # Events — has "seminar" or "workshop" or ("event" + "duration"/"participants")
    if ("seminar" in header_text or "workshop" in header_text or "short term" in header_text):
        return "events"
    if ("event" in header_text) and ("duration" in header_text or "participants" in header_text):
        return "events"

    # Staff changes
    if "designation" in header_text and ("joining" in header_text or "leaving" in header_text):
        return "staff_changes"

    # Classwork adjustments
    if "adjusted" in header_text and ("subject" in header_text or "dept" in header_text):
        return "classwork"

    # Incidents
    if "brief" in header_text and ("statement" in header_text or "remarks" in header_text):
        return "incidents"

    return "unknown"


# ── Deterministic extractors ─────────────────────────────────────────────────

def _extract_attendance(table, dept_code: str, dept_name: str) -> dict:
    """Extract attendance data deterministically."""
    rows = _read_table_rows(table)
    if len(rows) < 2:  # Need at least header + 1 data row
        return None

    header = [h.lower().strip() for h in rows[0]]

    # Find column indices
    on_rolls_idx = _find_col(header, ["on rolls", "onrolls", "on roll"])
    absent_idx = _find_col(header, ["absent"])
    category_idx = _find_col(header, ["category"])

    if on_rolls_idx is None or absent_idx is None:
        return None

    teaching_count = 0
    non_teaching_count = 0
    total_on_rolls = 0
    total_absent = 0

    for row in rows[1:]:
        if len(row) <= max(on_rolls_idx, absent_idx):
            continue

        on_rolls = _parse_int(row[on_rolls_idx])
        absent = _parse_int(row[absent_idx])

        if on_rolls is None:
            continue

        # Determine teaching vs non-teaching
        category = row[category_idx].lower().strip() if category_idx is not None and category_idx < len(row) else ""

        if "non" in category:
            non_teaching_count = on_rolls
        else:
            teaching_count = on_rolls

        total_on_rolls += on_rolls or 0
        total_absent += absent or 0

    present = total_on_rolls - total_absent
    percentage = round(present / total_on_rolls * 100, 1) if total_on_rolls > 0 else None

    return {
        "dept": dept_name,
        "teaching_count": teaching_count or None,
        "non_teaching_count": non_teaching_count or None,
        "on_rolls": total_on_rolls,
        "absent": total_absent,
        "present": present,
        "percentage": percentage,
    }


def _extract_library_attendance(table) -> dict:
    """Extract library staff attendance."""
    rows = _read_table_rows(table)
    if len(rows) < 2:
        return None

    header = [h.lower().strip() for h in rows[0]]
    data = rows[1]

    on_rolls_idx = _find_col(header, ["on roll", "on rolls"])
    absent_with_idx = _find_col(header, ["absent with leave", "absent with"])
    absent_without_idx = _find_col(header, ["absent without leave", "absent without"])
    present_idx = _find_col(header, ["present"])

    return {
        "on_rolls": _safe_get_int(data, on_rolls_idx),
        "absent_with_leave": _safe_get_int(data, absent_with_idx),
        "absent_without_leave": _safe_get_int(data, absent_without_idx),
        "present": _safe_get_int(data, present_idx),
    }


def _extract_infrastructure(table, dept_name: str) -> list[dict]:
    """Extract infrastructure issues deterministically."""
    rows = _read_table_rows(table)
    if len(rows) < 2:
        return []

    header = [h.lower().strip() for h in rows[0]]
    desc_idx = _find_col(header, ["description", "problem"])
    reported_idx = _find_col(header, ["reported"])
    completed_idx = _find_col(header, ["completed"])
    remarks_idx = _find_col(header, ["remarks"])

    issues = []
    for row in rows[1:]:
        desc = _safe_get(row, desc_idx, "").strip()
        if not desc or _is_empty(desc):
            continue

        completed = _safe_get(row, completed_idx, "").strip()
        # Skip resolved issues (completed date is filled)
        if completed and not _is_empty(completed):
            continue

        issues.append({
            "dept": dept_name,
            "description": desc,
            "reported_on": _safe_get(row, reported_idx, ""),
            "status": "pending",
            "remarks": _safe_get(row, remarks_idx, "") or None,
        })

    return issues


def _extract_staff_changes(table, dept_name: str) -> list[dict]:
    """Extract staff joined/left entries."""
    rows = _read_table_rows(table)
    if len(rows) < 2:
        return []

    header = [h.lower().strip() for h in rows[0]]
    name_idx = _find_col(header, ["name", "faculty"])
    desig_idx = _find_col(header, ["designation"])
    date_idx = _find_col(header, ["joining", "leaving", "date"])
    remarks_idx = _find_col(header, ["remarks"])

    changes = []
    for row in rows[1:]:
        name = _safe_get(row, name_idx, "").strip()
        if not name or _is_empty(name):
            continue

        date_val = _safe_get(row, date_idx, "")
        remarks = _safe_get(row, remarks_idx, "")

        # Determine joined or left
        change_type = "joined"
        combined = (date_val + " " + remarks).lower()
        if "left" in combined or "leaving" in combined or "resign" in combined:
            change_type = "left"

        changes.append({
            "name": name,
            "dept": dept_name,
            "designation": _safe_get(row, desig_idx, ""),
            "type": change_type,
            "date": date_val,
        })

    return changes


def _extract_incidents(table, dept_name: str) -> list[dict]:
    """Extract discipline incidents."""
    rows = _read_table_rows(table)
    if len(rows) < 2:
        return []

    header = [h.lower().strip() for h in rows[0]]
    name_idx = _find_col(header, ["name"])
    id_idx = _find_col(header, ["r. no", "id no", "roll"])
    brief_idx = _find_col(header, ["brief", "statement"])
    remarks_idx = _find_col(header, ["remarks"])

    incidents = []
    for row in rows[1:]:
        name = _safe_get(row, name_idx, "").strip()
        brief = _safe_get(row, brief_idx, "").strip()
        if (not name or _is_empty(name)) and (not brief or _is_empty(brief)):
            continue

        incidents.append({
            "dept": dept_name,
            "type": "student",  # Default; can be refined
            "name": name,
            "id": _safe_get(row, id_idx, "") or None,
            "brief": brief,
            "remarks": _safe_get(row, remarks_idx, "") or None,
        })

    return incidents


def _extract_library_data(table) -> tuple[dict, dict]:
    """Extract library transactions and services from the combined table."""
    rows = _read_table_rows(table)
    if len(rows) < 2:
        return {}, {}

    # Find the value column — it's always the last column (labeled "No's" or "No.s")
    # We can't search for "no" because it matches "s. no." too
    header = [h.lower().strip() for h in rows[0]]
    val_idx = len(rows[0]) - 1  # Last column is always the value column

    particulars_idx = _find_col(header, ["particulars", "description"])
    if particulars_idx is None:
        particulars_idx = 1  # Typical position

    transactions = {}
    services = {}

    # Ordered (keyword, json_key) pairs — more specific patterns first
    # Order matters: first match wins, and later rows can overwrite if less specific
    TXN_RULES = [
        # Books
        (lambda l: "books issued" in l or "check out" in l, "books_issued"),
        (lambda l: "books returned" in l or "check in" in l, "books_returned"),
        # Visitors — must match in specific order to avoid overwrites
        (lambda l: "total" in l and "visitors" in l and "lirc" in l, "visitors_lirc"),
        (lambda l: ("evening" in l or "5.00 pm" in l or "5 pm" in l or "5.00pm" in l), "visitors_evening_5_to_8"),
        (lambda l: "digital" in l, "visitors_digital"),
        (lambda l: "show" in l and "tell" in l and "visitor" in l, "show_and_tell_visitors"),
        (lambda l: "cvpc" in l or "c.v.p.c" in l, "cvpc_visitors"),
    ]

    SVC_RULES = [
        (lambda l: "plagiarism" in l or "turnitin" in l, "plagiarism_checks"),
        (lambda l: "show" in l and "tell" in l and "visitor" not in l, "show_and_tell"),
        (lambda l: "patent" in l, "patent_searches"),
        (lambda l: "scopus" in l, "scopus_searches"),
        (lambda l: "grammarly" in l, "grammarly_usage"),
        (lambda l: "duplicate" in l, "duplicate_id_cards"),
    ]

    for row in rows[1:]:
        label = _safe_get(row, particulars_idx, "").strip().lower()
        value = _safe_get_int(row, val_idx)

        if not label or value is None:
            continue

        # Match against known keys — first rule that matches wins
        matched = False
        for rule_fn, key in TXN_RULES:
            if rule_fn(label):
                transactions[key] = value
                matched = True
                break

        if not matched:
            for rule_fn, key in SVC_RULES:
                if rule_fn(label):
                    services[key] = value
                    break

    return transactions, services


# ── Table → text for LLM narrative sections ──────────────────────────────────

def _table_to_text(label: str, table) -> str:
    """Convert a table to pipe-delimited text for LLM consumption."""
    rows = _read_table_rows(table)
    if not rows:
        return ""

    # Filter out completely empty rows
    non_empty = [r for r in rows if any(c.strip() for c in r)]
    if not non_empty:
        return ""

    lines = [f"[{label}]"]
    for row in non_empty:
        lines.append(" | ".join(row))

    return "\n".join(lines)


# ── Utility functions ─────────────────────────────────────────────────────────

def _read_table_rows(table) -> list[list[str]]:
    """Read all rows from a table, handling merged cells.
    
    Deduplication is done by checking the underlying XML tc element identity,
    not by comparing text content. This prevents data loss when adjacent cells
    legitimately contain the same value (e.g., '--' in library attendance).
    """
    rows = []
    for row in table.rows:
        cells = []
        seen_tc_ids = set()
        for cell in row.cells:
            tc_id = id(cell._tc)  # Unique identity of the table cell XML element
            if tc_id in seen_tc_ids:
                continue  # Skip merged cell (same underlying XML element)
            seen_tc_ids.add(tc_id)
            text = cell.text.strip().replace("\n", " ").replace("\r", "")
            cells.append(text)
        rows.append(cells)
    return rows


def _find_col(header: list[str], keywords: list[str]) -> Optional[int]:
    """Find column index by keyword matching."""
    for i, h in enumerate(header):
        for kw in keywords:
            if kw in h:
                return i
    return None


def _parse_int(val: str) -> Optional[int]:
    """Parse an integer from a cell value, handling common formats."""
    if not val:
        return None
    stripped = val.strip()
    # Treat '--', '-', '—' as 0 (common in library reports for zero values)
    if stripped in ('--', '-', '—', 'nil', 'Nil', 'NIL'):
        return 0
    # Remove whitespace and common non-numeric chars
    cleaned = re.sub(r'[^\d]', '', stripped.split(':')[0].split('.')[0].strip())
    if not cleaned:
        return None
    try:
        return int(cleaned)
    except (ValueError, TypeError):
        return None


def _safe_get(lst: list, idx: Optional[int], default: str = "") -> str:
    """Safely get a value from a list by index."""
    if idx is None or idx >= len(lst):
        return default
    return lst[idx]


def _safe_get_int(lst: list, idx: Optional[int]) -> Optional[int]:
    """Safely get an integer value from a list by index."""
    val = _safe_get(lst, idx, "")
    return _parse_int(val)


def _is_empty(text: str) -> bool:
    """Check if a cell value is effectively empty."""
    if not text:
        return True
    normalized = text.strip().lower()
    return normalized in ("", "nil", "none", "no", "-", "—", "n/a", "na", "--")


def _has_real_content(text: str) -> bool:
    """Check if text block has meaningful content beyond just headers."""
    lines = text.strip().split("\n")
    # Must have content beyond just the section label
    content_lines = [l for l in lines if not l.startswith("[") and l.strip()]
    if not content_lines:
        return False
    # Check if all content lines are empty/nil
    return any(not _is_empty(l.replace("|", "").strip()) for l in content_lines)


def _count_non_empty_rows(table) -> int:
    """Count data rows that have actual content (for classwork adjustments)."""
    rows = _read_table_rows(table)
    count = 0
    for row in rows[1:]:  # Skip header
        # A row has content if any cell (beyond S.No) has non-empty text
        if len(row) > 1 and any(not _is_empty(c) for c in row[1:]):
            count += 1
    return count
