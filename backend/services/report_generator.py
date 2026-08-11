"""
DOCX Report Generator
Generates a consolidated daily report in .docx format matching the VNRVJIET template.
Events and other matters are grouped by department with inline images.
"""

import io
import os
from datetime import datetime
from docx import Document
from docx.shared import Inches, Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn, nsdecls
from docx.oxml import parse_xml


# ── Colour constants ──────────────────────────────────────────────────────────
DARK_BLUE = RGBColor(0x1A, 0x2F, 0x5A)
MID_BLUE = RGBColor(0x2E, 0x50, 0x90)
ACCENT_GREEN = RGBColor(0x27, 0x7D, 0x4E)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
BODY_GRAY = RGBColor(0x33, 0x33, 0x33)
LIGHT_GRAY_HEX = "F2F2F2"
DARK_BLUE_HEX = "1A2F5A"
MID_BLUE_HEX = "2E5090"


# ── Helper functions ──────────────────────────────────────────────────────────

def _set_cell_shading(cell, color_hex: str):
    """Set background shading on a table cell."""
    shading = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{color_hex}"/>')
    cell._tc.get_or_add_tcPr().append(shading)


def _set_cell_text(cell, text: str, bold: bool = False, font_size: int = 9,
                   color: RGBColor = None, alignment=WD_ALIGN_PARAGRAPH.LEFT):
    """Set text in a table cell with formatting."""
    cell.text = ""
    paragraph = cell.paragraphs[0]
    paragraph.alignment = alignment
    paragraph.paragraph_format.space_before = Pt(2)
    paragraph.paragraph_format.space_after = Pt(2)
    run = paragraph.add_run(str(text))
    run.bold = bold
    run.font.size = Pt(font_size)
    if color:
        run.font.color.rgb = color
    run.font.name = "Calibri"


def _add_header_row(table, headers: list[str]):
    """Style the first row of a table as a header."""
    row = table.rows[0]
    for i, header in enumerate(headers):
        cell = row.cells[i]
        _set_cell_shading(cell, DARK_BLUE_HEX)
        _set_cell_text(cell, header, bold=True, font_size=9,
                       color=WHITE, alignment=WD_ALIGN_PARAGRAPH.CENTER)


def _add_data_row(table, values: list[str], row_idx: int):
    """Add a data row with alternating gray/white background."""
    row = table.rows[row_idx]
    bg = LIGHT_GRAY_HEX if row_idx % 2 == 0 else "FFFFFF"
    for i, val in enumerate(values):
        cell = row.cells[i]
        _set_cell_shading(cell, bg)
        _set_cell_text(cell, str(val), font_size=9,
                       alignment=WD_ALIGN_PARAGRAPH.CENTER)


def _add_section_heading(doc, number: int, title: str):
    """Add a numbered section heading with blue bottom border."""
    heading = doc.add_paragraph()
    heading.paragraph_format.space_before = Pt(12)
    heading.paragraph_format.space_after = Pt(4)
    run = heading.add_run(f"  {number}.  {title}")
    run.bold = True
    run.font.size = Pt(11)
    run.font.color.rgb = DARK_BLUE
    run.font.name = "Calibri"
    # Bottom border
    pPr = heading._p.get_or_add_pPr()
    pBdr = parse_xml(
        f'<w:pBdr {nsdecls("w")}>'
        f'<w:bottom w:val="single" w:sz="6" w:space="1" w:color="{DARK_BLUE_HEX}"/>'
        f'</w:pBdr>'
    )
    pPr.append(pBdr)


def _add_sub_heading(doc, title: str):
    """Add a sub-section heading."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(2)
    run = p.add_run(title)
    run.bold = True
    run.font.size = Pt(10)
    run.font.color.rgb = MID_BLUE
    run.font.name = "Calibri"


def _add_dept_heading(doc, dept_name: str):
    """Add a department name heading (bold, slightly larger, with accent bar)."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.left_indent = Cm(0.2)

    # Accent bar
    run = p.add_run("▎ ")
    run.font.size = Pt(10)
    run.font.color.rgb = ACCENT_GREEN
    run.font.name = "Calibri"

    # Department name
    run = p.add_run(dept_name.upper())
    run.bold = True
    run.font.size = Pt(10)
    run.font.color.rgb = DARK_BLUE
    run.font.name = "Calibri"


def _add_body_text(doc, text: str, bold_prefix: str = None):
    """Add a body paragraph with optional bold prefix."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.left_indent = Cm(0.5)

    if bold_prefix:
        run = p.add_run(bold_prefix)
        run.bold = True
        run.font.size = Pt(9)
        run.font.color.rgb = DARK_BLUE
        run.font.name = "Calibri"

    run = p.add_run(text)
    run.font.size = Pt(9)
    run.font.color.rgb = BODY_GRAY
    run.font.name = "Calibri"
    return p


def _add_importance_badge(paragraph, importance: str):
    """Add a colored importance badge to a paragraph."""
    color_map = {
        "high": RGBColor(0xC0, 0x39, 0x2B),    # Red
        "medium": RGBColor(0xE6, 0x8A, 0x00),   # Orange
        "low": RGBColor(0x7F, 0x8C, 0x8D),      # Gray
    }
    badge_color = color_map.get(importance.lower(), BODY_GRAY)
    run = paragraph.add_run(f"  [{importance.upper()}]")
    run.bold = True
    run.font.size = Pt(8)
    run.font.color.rgb = badge_color
    run.font.name = "Calibri"


def _insert_dept_images(doc, dept_code: str, all_images: list[dict], max_images: int = 3):
    """Insert event-related images for a specific department inline."""
    dept_images = [img for img in all_images if img["dept_code"] == dept_code]
    if not dept_images:
        return 0

    inserted = 0
    for img in dept_images[:max_images]:
        try:
            img_stream = io.BytesIO(img["image_bytes"])
            doc.add_picture(img_stream, width=Inches(3.5))
            last_p = doc.paragraphs[-1]
            last_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            last_p.paragraph_format.space_before = Pt(4)
            last_p.paragraph_format.space_after = Pt(4)
            inserted += 1
        except Exception as e:
            print(f"[WARNING] Failed to insert image {img['filename']}: {e}")

    return inserted


def _val(v):
    """Format a value for display — use '—' for None/null."""
    if v is None:
        return "—"
    return str(v)


def _pct(val):
    """Format percentage."""
    if val is None:
        return "—"
    return f"{val:.1f}%"


def _build_attendance(doc, report, section_num: int) -> int:
    """Build the staff attendance section (table format)."""
    depts = report.get("attendance", {}).get("departments", [])
    if not depts:
        return section_num

    _add_section_heading(doc, section_num, "Staff Attendance Report (Department-wise)")

    headers = ["S.No", "Department", "Teaching", "Non-Teaching", "On Rolls", "Absent", "Present", "Attendance %"]
    table = doc.add_table(rows=1 + len(depts) + 1, cols=8)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True
    _add_header_row(table, headers)

    total_teach = total_non_teach = total_rolls = total_absent = total_present = 0
    for i, d in enumerate(depts):
        t_count = d.get("teaching_count", 0) or 0
        nt_count = d.get("non_teaching_count", 0) or 0
        on_rolls = d.get("on_rolls", 0) or 0
        absent = d.get("absent", 0) or 0
        present = d.get("present", 0) or 0
        pct = _pct(d.get("percentage"))
        
        total_teach += t_count
        total_non_teach += nt_count
        total_rolls += on_rolls
        total_absent += absent
        total_present += present
        
        _add_data_row(table, [
            str(i + 1), d.get("dept", ""),
            _val(t_count), _val(nt_count),
            _val(on_rolls), _val(absent),
            _val(present), pct,
        ], i + 1)

    # Totals row
    total_pct = round(total_present / total_rolls * 100, 1) if total_rolls else 0
    total_row = table.rows[-1]
    totals_vals = ["", "TOTAL", str(total_teach), str(total_non_teach), 
                   str(total_rolls), str(total_absent), str(total_present), _pct(total_pct)]
    
    for i, val in enumerate(totals_vals):
        cell = total_row.cells[i]
        _set_cell_shading(cell, MID_BLUE_HEX)
        _set_cell_text(cell, val, bold=True, font_size=9,
                       color=WHITE, alignment=WD_ALIGN_PARAGRAPH.CENTER)

    # Library attendance
    lib = report.get("attendance", {}).get("library")
    if lib:
        _add_sub_heading(doc, "Library Staff Attendance")
        lib_headers = ["On Rolls", "Absent (w/ leave)", "Absent (w/o leave)", "Present"]
        lib_table = doc.add_table(rows=2, cols=4)
        lib_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        _add_header_row(lib_table, lib_headers)
        _add_data_row(lib_table, [
            _val(lib.get("on_rolls")), _val(lib.get("absent_with_leave")),
            _val(lib.get("absent_without_leave")), _val(lib.get("present")),
        ], 1)

    return section_num + 1


def _build_overall_attendance(doc, report, section_num: int) -> int:
    """
    Build the staff attendance section.
    Uses attendance.departments (deterministic) directly for a clean dept-wise table.
    Falls back to raw overall_staff_attendance_table if dept data is missing.
    """
    depts = report.get("attendance", {}).get("departments", [])
    has_overall = bool(report.get("overall_staff_attendance_table"))

    if not depts and not has_overall:
        return section_num

    _add_section_heading(doc, section_num, "Staff & Student Attendance Report")

    # ── Department-wise table (from deterministic attendance data) ────────────
    if depts:
        _add_sub_heading(doc, "Staff Attendance Summary")

        headers = ["S.No", "Department", "Teaching", "Non-Teaching",
                   "On Rolls", "Absent", "Present", "Attendance %"]
        table = doc.add_table(rows=1 + len(depts) + 1, cols=len(headers))
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.style = 'Table Grid'
        _add_header_row(table, headers)

        total_teach = total_nt = total_rolls = total_absent = total_present = 0
        for i, d in enumerate(depts):
            t  = d.get("teaching_count", 0) or 0
            nt = d.get("non_teaching_count", 0) or 0
            on = d.get("on_rolls", 0) or 0
            ab = d.get("absent", 0) or 0
            pr = d.get("present", 0) or 0
            total_teach  += t
            total_nt     += nt
            total_rolls  += on
            total_absent += ab
            total_present+= pr
            _add_data_row(table, [
                str(i + 1), d.get("dept", ""),
                _val(t) if t else "—", _val(nt) if nt else "—",
                _val(on), _val(ab), _val(pr),
                _pct(d.get("percentage")),
            ], i + 1)

        # Totals row
        total_pct = round(total_present / total_rolls * 100, 1) if total_rolls else 0
        total_row = table.rows[-1]
        totals = ["", "TOTAL",
                  str(total_teach) if total_teach else "—",
                  str(total_nt)    if total_nt    else "—",
                  str(total_rolls), str(total_absent), str(total_present), _pct(total_pct)]
        for i, val in enumerate(totals):
            cell = total_row.cells[i]
            _set_cell_shading(cell, MID_BLUE_HEX)
            _set_cell_text(cell, val, bold=True, font_size=9,
                           color=WHITE, alignment=WD_ALIGN_PARAGRAPH.CENTER)



    # ── Library staff attendance ──────────────────────────────────────────────
    lib = report.get("attendance", {}).get("library")
    if lib:
        _add_sub_heading(doc, "Library Staff Attendance")
        lib_headers = ["On Rolls", "Absent (w/ leave)", "Absent (w/o leave)", "Present"]
        lib_table = doc.add_table(rows=2, cols=4)
        lib_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        lib_table.style = 'Table Grid'
        _add_header_row(lib_table, lib_headers)
        _add_data_row(lib_table, [
            _val(lib.get("on_rolls")), _val(lib.get("absent_with_leave")),
            _val(lib.get("absent_without_leave")), _val(lib.get("present")),
        ], 1)

    return section_num + 1


def _build_student_attendance(doc, report):
    """Build the student attendance table from raw data."""
    student_table = report.get("overall_student_attendance_table", [])
    if not student_table:
        return

    _add_sub_heading(doc, "Student Attendance Report")
    
    # We render the table exactly as it is, since it has variable lengths
    # Find max columns
    max_cols = max((len(r) for r in student_table), default=0)
    if max_cols == 0:
        return
        
    table = doc.add_table(rows=len(student_table), cols=max_cols)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.style = 'Table Grid'

    for r, row_data in enumerate(student_table):
        row_obj = table.rows[r]
        for c, val in enumerate(row_data):
            if c < max_cols:
                cell = row_obj.cells[c]
                is_header = (r == 0)
                # Shading: dark blue for header, alternate for body
                if is_header:
                    _set_cell_shading(cell, DARK_BLUE_HEX)
                else:
                    _set_cell_shading(cell, LIGHT_GRAY_HEX if r % 2 == 0 else "FFFFFF")
                
                color = WHITE if is_header else BODY_GRAY
                _set_cell_text(cell, str(val), bold=is_header, font_size=8, color=color, alignment=WD_ALIGN_PARAGRAPH.CENTER)



def _parse_batch_pills_table(text: str):
    """
    Extract the header+values pipe-separated table from batch pills text.
    Returns (headers: list[str], values: list[str]) or (None, None).
    """
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    # Find the header line: contains '|' and at least 5 branch codes (CSE, AIML, IT, ECE…)
    BRANCH_KEYS = {"CSE", "AIML", "IOT", "IT", "ECE", "EEE", "EIE", "ME", "CE", "AE"}
    header_idx = None
    for i, line in enumerate(lines):
        cols = [c.strip() for c in line.split("|") if c.strip()]
        if len(cols) >= 8 and len(BRANCH_KEYS & set(cols)) >= 4:
            header_idx = i
            break
    if header_idx is None:
        return None, None
    headers = [c.strip() for c in lines[header_idx].split("|") if c.strip()]
    # Next line should be all numbers
    if header_idx + 1 < len(lines):
        val_line = lines[header_idx + 1]
        vals = [c.strip() for c in val_line.split("|") if c.strip()]
        if all(v.isdigit() for v in vals):
            return headers, vals
    return headers, None


def _build_mtp_sections(doc, report, section_num: int) -> int:
    """Build the MTP highlights and Batch Pills summary sections."""
    mtp_narrative = report.get("mtp_narrative", "").strip()
    batch_pills   = report.get("mtp_batch_pills", "").strip()
    mtp_summary   = report.get("mtp_summary", [])

    if not mtp_narrative and not batch_pills and not mtp_summary:
        return section_num

    _add_section_heading(doc, section_num, "Mentoring, Training & Placements (MTP)")

    # ── Structured MTP activity items (produced by LLM) ──────────────────────
    if mtp_summary:
        _add_sub_heading(doc, "MTP Highlights (Section IV)")

        ACTIVITY_COLORS = {
            "placement_drive": RGBColor(0xC0, 0x39, 0x2B),   # Red
            "ppt":             RGBColor(0xC0, 0x39, 0x2B),   # Red
            "aptitude_test":   RGBColor(0xE6, 0x8A, 0x00),   # Orange
            "training":        RGBColor(0x27, 0x7D, 0x4E),   # Green
            "mock_interview":  RGBColor(0x2E, 0x50, 0x90),   # Blue
            "internship":      RGBColor(0x8E, 0x44, 0xAD),   # Purple
            "other":           RGBColor(0x55, 0x55, 0x55),   # Gray
        }
        ACTIVITY_LABELS = {
            "placement_drive": "Placement Drive",
            "ppt":             "Pre-Placement Talk",
            "aptitude_test":   "Aptitude Test",
            "training":        "Training Session",
            "mock_interview":  "Mock Interview",
            "internship":      "Internship",
            "other":           "Activity",
        }

        for item in mtp_summary:
            if not isinstance(item, dict):
                continue
            company       = item.get("company") or ""
            activity_type = item.get("activity_type", "other")
            summary_text  = item.get("summary", "").strip()
            student_count = item.get("student_count")
            batch         = item.get("batch") or ""
            status        = item.get("status") or ""

            if not summary_text:
                continue

            # ── Bullet: ● Company  [Activity Type] ────────────────────────────
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(4)
            p.paragraph_format.space_after  = Pt(1)
            p.paragraph_format.left_indent  = Cm(0.5)

            label = company if company else ACTIVITY_LABELS.get(activity_type, "Activity")
            run = p.add_run(f"● {label}")
            run.bold = True
            run.font.size = Pt(9)
            run.font.color.rgb = DARK_BLUE
            run.font.name = "Calibri"

            badge_color = ACTIVITY_COLORS.get(activity_type, BODY_GRAY)
            badge_label = ACTIVITY_LABELS.get(activity_type, activity_type.replace("_", " ").title())
            run2 = p.add_run(f"  [{badge_label}]")
            run2.bold = True
            run2.font.size = Pt(8)
            run2.font.color.rgb = badge_color
            run2.font.name = "Calibri"

            # ── Meta line: batch | status | count ─────────────────────────────
            meta_parts = []
            if batch:
                meta_parts.append(batch)
            if status:
                meta_parts.append(status)
            if student_count is not None:
                meta_parts.append(f"{student_count} students")

            if meta_parts:
                meta_p = doc.add_paragraph()
                meta_p.paragraph_format.space_before = Pt(0)
                meta_p.paragraph_format.space_after  = Pt(1)
                meta_p.paragraph_format.left_indent  = Cm(1.0)
                run_m = meta_p.add_run("  " + "  |  ".join(meta_parts))
                run_m.font.size = Pt(8)
                run_m.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
                run_m.font.name = "Calibri"
                run_m.italic = True

            # ── Summary body ───────────────────────────────────────────────────
            _add_body_text(doc, summary_text)

    elif mtp_narrative:
        # Fallback: raw narrative when LLM produced no structured items
        _add_sub_heading(doc, "MTP Highlights (Section IV)")
        text = mtp_narrative.replace("[MTP Section IV]", "").strip()
        for line in text.split("\n"):
            line = line.strip()
            if line:
                _add_body_text(doc, line)

    # ── Batch Pills table ─────────────────────────────────────────────────────
    if batch_pills:
        _add_sub_heading(doc, "Batch Pills Open Summary")
        text = batch_pills.replace("[Batch Pills Open Summary]", "").strip()

        headers, values = _parse_batch_pills_table(text)
        if headers and values:
            n_cols = min(len(headers), len(values))
            tbl = doc.add_table(rows=2, cols=n_cols)
            tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
            tbl.style = 'Table Grid'
            for i, h in enumerate(headers[:n_cols]):
                cell = tbl.rows[0].cells[i]
                _set_cell_shading(cell, DARK_BLUE_HEX)
                _set_cell_text(cell, h, bold=True, font_size=8,
                               color=WHITE, alignment=WD_ALIGN_PARAGRAPH.CENTER)
            for i, v in enumerate(values[:n_cols]):
                cell = tbl.rows[1].cells[i]
                _set_cell_shading(cell, LIGHT_GRAY_HEX)
                _set_cell_text(cell, v, bold=True, font_size=9,
                               color=DARK_BLUE, alignment=WD_ALIGN_PARAGRAPH.CENTER)
        else:
            for line in text.split("\n"):
                line = line.strip()
                if line and not line.startswith("["):
                    _add_body_text(doc, line)

    return section_num + 1


def _build_infrastructure(doc, report, section_num: int) -> int:
    """Build infrastructure issues section (table, pending only)."""
    issues = [i for i in report.get("infrastructure_issues", [])
              if i.get("status", "").lower() == "pending"]
    if not issues:
        return section_num

    _add_section_heading(doc, section_num, "Infrastructure Issues / Maintenance (Pending)")

    headers = ["S.No", "Department", "Description", "Reported On", "Remarks"]
    table = doc.add_table(rows=1 + len(issues), cols=5)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    _add_header_row(table, headers)

    for i, iss in enumerate(issues):
        row = table.rows[i + 1]
        values = [
            str(i + 1), iss.get("dept", "").upper(),
            iss.get("description", "—"), _val(iss.get("reported_on")),
            _val(iss.get("remarks")),
        ]
        bg = LIGHT_GRAY_HEX if i % 2 == 0 else "FFFFFF"
        for j, val in enumerate(values):
            cell = row.cells[j]
            _set_cell_shading(cell, bg)
            align = WD_ALIGN_PARAGRAPH.LEFT if j == 2 else WD_ALIGN_PARAGRAPH.CENTER
            _set_cell_text(cell, val, font_size=9, alignment=align)

    return section_num + 1


def _build_department_highlights(doc, report, section_num: int, all_images: list[dict]) -> int:
    """
    Build events + other matters grouped by DEPARTMENT with inline images.

    Each department with noteworthy content gets:
    - A bold department heading
    - Events listed as bullet points with importance badges
    - Other matters listed below
    - Relevant images inserted inline
    """
    highlights = report.get("department_highlights", [])

    # Fallback: if AI returned old-style flat "events" list, convert it
    if not highlights and report.get("events"):
        highlights = _convert_flat_events_to_highlights(report)

    if not highlights:
        return section_num

    _add_section_heading(doc, section_num, "Department Highlights — Events & Activities")

    for dept_block in highlights:
        dept_name = dept_block.get("dept", "Unknown Department")
        dept_code = dept_block.get("dept_code", "").lower()
        events = dept_block.get("events", [])
        other_matters = dept_block.get("other_matters", [])

        # MTP has its own dedicated section — never render it in Dept Highlights
        if dept_code == "mtp":
            continue

        # Skip departments with nothing to show
        if not events and not other_matters:
            continue

        # Department heading
        _add_dept_heading(doc, dept_name)

        # Events
        for ev in events:
            name = ev.get("name", "Untitled Event")
            summary = ev.get("summary", "")
            importance = ev.get("importance", "medium")
            date_str = ev.get("date", "")
            duration = ev.get("duration", "")
            internal = ev.get("participants_internal")
            external = ev.get("participants_external")
            resource_person = ev.get("resource_person")

            # Event title with importance badge
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(4)
            p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.left_indent = Cm(0.5)

            run = p.add_run(f"● {name}")
            run.bold = True
            run.font.size = Pt(9)
            run.font.color.rgb = MID_BLUE
            run.font.name = "Calibri"

            _add_importance_badge(p, importance)

            # Meta line (date, participants, resource person)
            meta_parts: list[str] = []
            if date_str:
                meta_parts.append(f"Date: {date_str}")
            if duration:
                meta_parts.append(f"Duration: {duration}")
            if internal is not None:
                meta_parts.append(f"Internal: {internal}")
            if external is not None:
                meta_parts.append(f"External: {external}")
            if resource_person:
                meta_parts.append(f"Resource Person: {resource_person}")

            if meta_parts:
                meta_p = doc.add_paragraph()
                meta_p.paragraph_format.space_before = Pt(0)
                meta_p.paragraph_format.space_after = Pt(2)
                meta_p.paragraph_format.left_indent = Cm(1.0)
                run = meta_p.add_run("  ".join(meta_parts))
                run.font.size = Pt(8)
                run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
                run.font.name = "Calibri"
                run.italic = True

            # Summary narrative
            if summary:
                _add_body_text(doc, summary)

        # Other matters for this department
        if other_matters:
            for matter in other_matters:
                if isinstance(matter, str) and matter.strip():
                    _add_body_text(doc, matter, bold_prefix="• Other: ")
                elif isinstance(matter, dict):
                    desc = matter.get("description", "")
                    if desc.strip():
                        _add_body_text(doc, desc, bold_prefix="• Other: ")

        # Insert images inline for this department
        img_count = _insert_dept_images(doc, dept_code, all_images, max_images=3)
        if img_count > 0:
            print(f"[INFO] Inserted {img_count} image(s) for {dept_code.upper()}")

    return section_num + 1


def _convert_flat_events_to_highlights(report: dict) -> list[dict]:
    """Convert old-style flat events list to department-grouped highlights."""
    events = report.get("events", [])
    other_matters = report.get("other_matters", [])

    dept_map: dict[str, dict] = {}

    for ev in events:
        dept = ev.get("dept", "Unknown")
        if dept not in dept_map:
            dept_map[dept] = {"dept": dept, "dept_code": dept.lower(), "events": [], "other_matters": []}
        dept_map[dept]["events"].append(ev)

    for om in other_matters:
        dept = om.get("dept", "General")
        if dept not in dept_map:
            dept_map[dept] = {"dept": dept, "dept_code": dept.lower(), "events": [], "other_matters": []}
        dept_map[dept]["other_matters"].append(om.get("description", str(om)))

    return list(dept_map.values())


def _build_participation(doc, report, section_num: int) -> int:
    """Build staff & student participation in narrative format."""
    staff_p = report.get("staff_participation", [])
    student_p = report.get("student_participation", [])

    if not staff_p and not student_p:
        return section_num

    _add_section_heading(doc, section_num, "Participation by Staff & Students (External)")

    if staff_p:
        _add_sub_heading(doc, "Staff Participation")
        for s in staff_p:
            name = s.get("name", "")
            dept = s.get("dept", "")
            event = s.get("event", "")
            role = s.get("role", s.get("status", ""))
            date_str = s.get("date", "")
            summary = s.get("summary", "")

            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.left_indent = Cm(0.5)

            run = p.add_run(f"● {name}")
            run.bold = True
            run.font.size = Pt(9)
            run.font.color.rgb = DARK_BLUE
            run.font.name = "Calibri"

            detail_parts: list[str] = []
            if dept:
                detail_parts.append(dept)
            if role:
                detail_parts.append(role)
            if event:
                detail_parts.append(f'at "{event}"')
            if date_str:
                detail_parts.append(f"({date_str})")

            if detail_parts:
                run = p.add_run(f"  — {', '.join(detail_parts)}")
                run.font.size = Pt(9)
                run.font.color.rgb = BODY_GRAY
                run.font.name = "Calibri"

            if summary:
                _add_body_text(doc, summary)

    if student_p:
        _add_sub_heading(doc, "Student Participation")
        for s in student_p:
            name = s.get("name", "")
            dept = s.get("dept", "")
            event = s.get("event", "")
            achievement = s.get("achievement", s.get("status", ""))
            date_str = s.get("date", "")
            summary = s.get("summary", "")

            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.left_indent = Cm(0.5)

            run = p.add_run(f"● {name}")
            run.bold = True
            run.font.size = Pt(9)
            run.font.color.rgb = DARK_BLUE
            run.font.name = "Calibri"

            detail_parts: list[str] = []
            if dept:
                detail_parts.append(dept)
            if event:
                detail_parts.append(f'at "{event}"')
            if achievement:
                detail_parts.append(f"— {achievement}")
            if date_str:
                detail_parts.append(f"({date_str})")

            if detail_parts:
                run = p.add_run(f"  — {', '.join(detail_parts)}")
                run.font.size = Pt(9)
                run.font.color.rgb = BODY_GRAY
                run.font.name = "Calibri"

            if summary:
                _add_body_text(doc, summary)

    return section_num + 1


def _build_staff_changes(doc, report, section_num: int) -> int:
    """Build staff joined/left section (table)."""
    changes = report.get("staff_changes", [])
    if not changes:
        return section_num

    _add_section_heading(doc, section_num, "Staff Joined / Left")

    headers = ["S.No", "Name", "Department", "Designation", "Joined/Left", "Date"]
    table = doc.add_table(rows=1 + len(changes), cols=6)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    _add_header_row(table, headers)

    for i, c in enumerate(changes):
        _add_data_row(table, [
            str(i + 1), c.get("name", "—"), c.get("dept", "—").upper(),
            c.get("designation", "—"), c.get("type", "—").upper(), c.get("date", "—"),
        ], i + 1)

    return section_num + 1


def _build_classwork_adjustments(doc, report, section_num: int) -> int:
    """Build classwork adjustments summary (table)."""
    adjustments = report.get("classwork_adjustments", [])
    if not adjustments:
        return section_num

    _add_section_heading(doc, section_num, "Classwork Adjustments / Lecture Interchange")

    headers = ["S.No", "Department", "Number of Adjustments"]
    table = doc.add_table(rows=1 + len(adjustments), cols=3)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    _add_header_row(table, headers)

    for i, adj in enumerate(adjustments):
        _add_data_row(table, [
            str(i + 1), adj.get("dept", "").upper(), _val(adj.get("count")),
        ], i + 1)

    return section_num + 1


def _build_incidents(doc, report, section_num: int) -> int:
    """Build incidents (discipline) section (table)."""
    incidents = report.get("incidents", [])
    if not incidents:
        return section_num

    _add_section_heading(doc, section_num, "Incidents (Discipline)")

    headers = ["S.No", "Department", "Type", "Name", "Brief", "Remarks"]
    table = doc.add_table(rows=1 + len(incidents), cols=6)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    _add_header_row(table, headers)

    for i, inc in enumerate(incidents):
        row = table.rows[i + 1]
        values = [
            str(i + 1), inc.get("dept", "").upper(), inc.get("type", "—"),
            inc.get("name", "—"), inc.get("brief", "—"), _val(inc.get("remarks")),
        ]
        bg = LIGHT_GRAY_HEX if i % 2 == 0 else "FFFFFF"
        for j, val in enumerate(values):
            cell = row.cells[j]
            _set_cell_shading(cell, bg)
            align = WD_ALIGN_PARAGRAPH.LEFT if j in (4, 5) else WD_ALIGN_PARAGRAPH.CENTER
            _set_cell_text(cell, val, font_size=9, alignment=align)
            if j in (4, 5):
                for cell_run in cell.paragraphs[0].runs:
                    cell_run.font.color.rgb = RGBColor(0xC0, 0x39, 0x2B)

    return section_num + 1


def _build_library(doc, report, section_num: int) -> int:
    """Build library transactions & services section (table). Always last."""
    txn = report.get("library_transactions", {})
    svc = report.get("library_services", {})

    if not txn and not svc:
        return section_num

    _add_section_heading(doc, section_num, "Library Services & Transactions")

    if txn:
        _add_sub_heading(doc, "Library Transactions")
        txn_items = [
            ("Books Issued (Check Out)", txn.get("books_issued")),
            ("Books Returned (Check In)", txn.get("books_returned")),
            ("Today's Visitors to LIRC", txn.get("visitors_lirc")),
            ("Evening Users (5 PM – 8 PM)", txn.get("visitors_evening_5_to_8")),
            ("Digital Library Visitors", txn.get("visitors_digital")),
            ("Show & Tell Visitors", txn.get("show_and_tell_visitors")),
            ("CVPC Visitors", txn.get("cvpc_visitors")),
        ]
        txn_items = [(k, v) for k, v in txn_items if v is not None]
        if txn_items:
            table = doc.add_table(rows=1 + len(txn_items), cols=2)
            table.alignment = WD_TABLE_ALIGNMENT.CENTER
            _add_header_row(table, ["Particulars", "Count"])
            for i, (label, value) in enumerate(txn_items):
                _add_data_row(table, [label, _val(value)], i + 1)

    if svc:
        has_svc = any(v for v in svc.values() if v is not None)
        if has_svc:
            _add_sub_heading(doc, "Library Services")
            svc_items = [
                ("Plagiarism Checks (Turnitin)", svc.get("plagiarism_checks")),
                ("Show & Tell", svc.get("show_and_tell")),
                ("Patent Searches", svc.get("patent_searches")),
                ("Scopus Indexing Service", svc.get("scopus_searches")),
                ("Grammarly Usage", svc.get("grammarly_usage")),
                ("Duplicate ID Cards Issued", svc.get("duplicate_id_cards")),
            ]
            svc_items = [(k, v) for k, v in svc_items if v is not None]
            if svc_items:
                table = doc.add_table(rows=1 + len(svc_items), cols=2)
                table.alignment = WD_TABLE_ALIGNMENT.CENTER
                _add_header_row(table, ["Service", "Count"])
                for i, (label, value) in enumerate(svc_items):
                    _add_data_row(table, [label, _val(value)], i + 1)

    return section_num + 1


# ── Main entry point ──────────────────────────────────────────────────────────

def generate_docx(report: dict, output_path: str = None,
                  all_images: list[dict] = None) -> bytes:
    """
    Generate the formatted daily report DOCX from the consolidated JSON.

    Args:
        report:      The full consolidated report dict.
        output_path: Optional file path to write the DOCX to.
        all_images:  Optional list of image dicts from source department files.

    Returns:
        DOCX as bytes (always), and also writes to output_path if provided.
    """
    if all_images is None:
        all_images = []

    doc = Document()

    # ── Page setup ────────────────────────────────────────────────────────────
    section = doc.sections[0]
    section.page_width = Cm(21)    # A4
    section.page_height = Cm(29.7)
    section.left_margin = Cm(1.8)
    section.right_margin = Cm(1.8)
    section.top_margin = Cm(2.0)
    section.bottom_margin = Cm(2.0)

    # ── Format date ───────────────────────────────────────────────────────────
    report_date_str = report.get("report_date", "—")
    try:
        dt = datetime.strptime(report_date_str, "%Y-%m-%d")
        formatted_date = dt.strftime("%d %B %Y")
    except Exception:
        formatted_date = report_date_str

    # ── Title ─────────────────────────────────────────────────────────────────
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.space_after = Pt(2)
    run = title.add_run("VNR Vignana Jyothi Institute of Engineering & Technology")
    run.bold = True
    run.font.size = Pt(14)
    run.font.color.rgb = DARK_BLUE
    run.font.name = "Calibri"

    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.paragraph_format.space_after = Pt(8)
    run = subtitle.add_run(f"Daily Report  |  {formatted_date}")
    run.font.size = Pt(11)
    run.font.color.rgb = RGBColor(0x44, 0x44, 0x44)
    run.font.name = "Calibri"

    # Horizontal rule
    hr = doc.add_paragraph()
    hr.paragraph_format.space_before = Pt(0)
    hr.paragraph_format.space_after = Pt(8)
    pPr = hr._p.get_or_add_pPr()
    pBdr = parse_xml(
        f'<w:pBdr {nsdecls("w")}>'
        f'<w:bottom w:val="single" w:sz="12" w:space="1" w:color="{DARK_BLUE_HEX}"/>'
        f'</w:pBdr>'
    )
    pPr.append(pBdr)

    # ── Build sections ────────────────────────────────────────────────────────
    # Order: Attendance → Infrastructure → Dept Highlights → Participation →
    #        Staff Changes → Classwork → Incidents → Library (ALWAYS LAST)
    num = 1
    num = _build_overall_attendance(doc, report, num)
    num = _build_mtp_sections(doc, report, num)
    num = _build_department_highlights(doc, report, num, all_images)
    num = _build_participation(doc, report, num)
    num = _build_staff_changes(doc, report, num)
    num = _build_classwork_adjustments(doc, report, num)
    num = _build_incidents(doc, report, num)
    num = _build_library(doc, report, num)
    num = _build_infrastructure(doc, report, num) # Moved to last


    # ── Footer note ───────────────────────────────────────────────────────────
    doc.add_paragraph()  # spacing
    footer = doc.add_paragraph()
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = footer.add_run("Consolidated by AI  |  VNRVJIET Principal's Office")
    run.font.size = Pt(8)
    run.font.color.rgb = RGBColor(0x99, 0x99, 0x99)
    run.font.name = "Calibri"
    run.italic = True

    # ── Save ──────────────────────────────────────────────────────────────────
    buf = io.BytesIO()
    doc.save(buf)
    docx_bytes = buf.getvalue()

    if output_path:
        with open(output_path, "wb") as f:
            f.write(docx_bytes)

    return docx_bytes