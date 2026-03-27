import io
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
 
 
# ── Colour palette ────────────────────────────────────────────────────────────
DARK_BLUE   = colors.HexColor("#1a2f5a")
MID_BLUE    = colors.HexColor("#2e5090")
LIGHT_BLUE  = colors.HexColor("#dce6f7")
LIGHT_GRAY  = colors.HexColor("#f5f5f5")
MID_GRAY    = colors.HexColor("#cccccc")
DARK_GRAY   = colors.HexColor("#444444")
WHITE       = colors.white
RED_ALERT   = colors.HexColor("#c0392b")
AMBER       = colors.HexColor("#d35400")
 
PAGE_W, PAGE_H = A4
L_MARGIN = R_MARGIN = 1.8 * cm
T_MARGIN = B_MARGIN = 2.0 * cm
CONTENT_W = PAGE_W - L_MARGIN - R_MARGIN
 
 
# ── Style helpers ─────────────────────────────────────────────────────────────
def _styles():
    base = getSampleStyleSheet()
 
    def add(name, **kw):
        if name not in base:
            base.add(ParagraphStyle(name=name, **kw))
        return base[name]
 
    add("ReportTitle",  fontSize=16, fontName="Helvetica-Bold",
        textColor=DARK_BLUE, spaceAfter=2, alignment=TA_CENTER)
    add("ReportSub",    fontSize=10, fontName="Helvetica",
        textColor=DARK_GRAY, spaceAfter=8, alignment=TA_CENTER)
    add("SectionHead",  fontSize=11, fontName="Helvetica-Bold",
        textColor=WHITE,    spaceBefore=10, spaceAfter=4,
        backColor=DARK_BLUE, leftIndent=6, leading=16)
    add("SubHead",      fontSize=10, fontName="Helvetica-Bold",
        textColor=MID_BLUE, spaceBefore=6, spaceAfter=3)
    add("Body",         fontSize=9,  fontName="Helvetica",
        textColor=DARK_GRAY, spaceAfter=3, leading=13)
    add("BodyBold",     fontSize=9,  fontName="Helvetica-Bold",
        textColor=DARK_GRAY, spaceAfter=3)
    add("Small",        fontSize=8,  fontName="Helvetica",
        textColor=DARK_GRAY, spaceAfter=2)
    add("Alert",        fontSize=9,  fontName="Helvetica-Bold",
        textColor=RED_ALERT, spaceAfter=3)
    add("FooterStyle",  fontSize=7,  fontName="Helvetica",
        textColor=MID_GRAY,  alignment=TA_CENTER)
    return base
 
 
def _section_header(text, styles):
    """Blue banner heading."""
    return Paragraph(f"&nbsp;&nbsp;{text}", styles["SectionHead"])
 
 
def _sub_header(text, styles):
    return Paragraph(text, styles["SubHead"])
 
 
def _body(text, styles, bold=False):
    key = "BodyBold" if bold else "Body"
    return Paragraph(str(text), styles[key])
 
 
def _hr():
    return HRFlowable(width="100%", thickness=0.5,
                      color=MID_GRAY, spaceAfter=4, spaceBefore=2)
 
 
def _spacer(h=0.25):
    return Spacer(1, h * cm)
 
 
def _pct(val):
    if val is None:
        return "—"
    return f"{val:.1f}%"
 
 
def _val(v):
    return "—" if v is None else str(v)
 
 
# ── Table style builders ──────────────────────────────────────────────────────
def _header_table_style(n_header_rows=1):
    return TableStyle([
        ("BACKGROUND",  (0, 0), (-1, n_header_rows - 1), DARK_BLUE),
        ("TEXTCOLOR",   (0, 0), (-1, n_header_rows - 1), WHITE),
        ("FONTNAME",    (0, 0), (-1, n_header_rows - 1), "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, -1), 8),
        ("FONTNAME",    (0, n_header_rows), (-1, -1), "Helvetica"),
        ("ROWBACKGROUNDS", (0, n_header_rows), (-1, -1), [WHITE, LIGHT_GRAY]),
        ("ALIGN",       (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("GRID",        (0, 0), (-1, -1), 0.4, MID_GRAY),
        ("TOPPADDING",  (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",(0, 0), (-1, -1), 5),
    ])
 
 
# ── Section builders ──────────────────────────────────────────────────────────
 
def _build_attendance(report, styles):
    story = []
    story.append(_section_header("1.  Staff Attendance Report (Dept-wise)", styles))
    story.append(_spacer(0.15))
 
    depts = report.get("attendance", {}).get("departments", [])
    if not depts:
        story.append(_body("No attendance data available.", styles))
        return story
 
    headers = ["Dept", "On Rolls", "Absent", "Present", "Attendance %"]
    rows = [headers]
    for d in depts:
        pct = _pct(d.get("percentage"))
        rows.append([
            d.get("dept", "").upper(),
            _val(d.get("on_rolls")),
            _val(d.get("absent")),
            _val(d.get("present")),
            pct,
        ])
 
    # Totals row
    total_rolls   = sum(d.get("on_rolls", 0) or 0 for d in depts)
    total_absent  = sum(d.get("absent",   0) or 0 for d in depts)
    total_present = sum(d.get("present",  0) or 0 for d in depts)
    total_pct     = round(total_present / total_rolls * 100, 1) if total_rolls else 0
    rows.append(["TOTAL", str(total_rolls), str(total_absent),
                 str(total_present), _pct(total_pct)])
 
    col_w = [2.5*cm, 2.5*cm, 2.5*cm, 2.5*cm, 3*cm]
    tbl = Table(rows, colWidths=col_w, repeatRows=1)
    style = _header_table_style()
    # Bold + dark bg for totals row
    style.add("BACKGROUND",  (0, -1), (-1, -1), MID_BLUE)
    style.add("TEXTCOLOR",   (0, -1), (-1, -1), WHITE)
    style.add("FONTNAME",    (0, -1), (-1, -1), "Helvetica-Bold")
    tbl.setStyle(style)
    story.append(tbl)
 
    # Library attendance
    lib = report.get("attendance", {}).get("library")
    if lib:
        story.append(_spacer(0.3))
        story.append(_sub_header("Library Staff Attendance", styles))
        lib_rows = [
            ["On Rolls", "Absent (w/ leave)", "Absent (w/o leave)", "Present"],
            [_val(lib.get("on_rolls")), _val(lib.get("absent_with_leave")),
             _val(lib.get("absent_without_leave")), _val(lib.get("present"))],
        ]
        lib_tbl = Table(lib_rows, colWidths=[3.5*cm]*4)
        lib_tbl.setStyle(_header_table_style())
        story.append(lib_tbl)
 
    return story
 
 
def _build_mtp(report, styles):
    """Section 2 — Maintenance / infrastructure issues (MTP)."""
    issues = [i for i in report.get("infrastructure_issues", []) if i.get("status") == "pending"]
    if not issues:
        return []
 
    story = [_spacer(), _section_header("2.  MTP (Maintenance & Infrastructure Issues)", styles), _spacer(0.15)]
    headers = ["S.No", "Dept", "Description", "Reported On", "Remarks"]
    rows = [headers]
    for idx, iss in enumerate(issues, 1):
        rows.append([
            str(idx),
            iss.get("dept", "").upper(),
            iss.get("description", "—"),
            _val(iss.get("reported_on")),
            _val(iss.get("remarks")),
        ])
    col_w = [1*cm, 1.8*cm, 8*cm, 2.5*cm, 3*cm]
    tbl = Table(rows, colWidths=col_w, repeatRows=1)
    tbl.setStyle(_header_table_style())
    story.append(tbl)
    return story
 
 
def _dept_has_content(dept_code, report):
    """Return True if a dept has anything reportable beyond attendance."""
    code = dept_code.lower()
    for ev in report.get("events", []):
        if ev.get("dept", "").lower() == code:
            return True
    for sp in report.get("staff_participation", []):
        if sp.get("dept", "").lower() == code:
            return True
    for sc in report.get("staff_changes", []):
        if sc.get("dept", "").lower() == code:
            return True
    for inc in report.get("incidents", []):
        if inc.get("dept", "").lower() == code:
            return True
    for om in report.get("other_matters", []):
        if om.get("dept", "").lower() == code:
            return True
    return False
 
 
def _build_hod_section(dept_code, dept_label, report, styles, section_num):
    """Build a single HOD dept block. Returns [] if nothing to report."""
    code = dept_code.lower()
 
    events   = [e for e in report.get("events", [])           if e.get("dept","").lower() == code]
    staff_p  = [s for s in report.get("staff_participation",[]) if s.get("dept","").lower() == code]
    changes  = [c for c in report.get("staff_changes", [])    if c.get("dept","").lower() == code]
    incidents= [i for i in report.get("incidents", [])        if i.get("dept","").lower() == code]
    others   = [o for o in report.get("other_matters", [])    if o.get("dept","").lower() == code]
 
    if not any([events, staff_p, changes, incidents, others]):
        return []
 
    story = [_spacer(), _section_header(f"{section_num}.  HOD — {dept_label}", styles), _spacer(0.1)]
 
    # Events
    if events:
        story.append(_sub_header("Events / Seminars / Workshops", styles))
        for ev in events:
            parts = [f"<b>{ev.get('name','—')}</b>"]
            if ev.get("duration"):      parts.append(f"Duration: {ev['duration']}")
            if ev.get("participants_internal"): parts.append(f"Internal participants: {ev['participants_internal']}")
            if ev.get("participants_external"): parts.append(f"External participants: {ev['participants_external']}")
            if ev.get("resource_person"):       parts.append(f"Resource person: {ev['resource_person']}")
            story.append(_body(" &nbsp;|&nbsp; ".join(parts), styles))
 
    # Staff changes
    if changes:
        story.append(_sub_header("Staff Joined / Left", styles))
        for c in changes:
            story.append(_body(
                f"{c.get('name','—')} ({c.get('designation','—')}) — "
                f"<b>{c.get('type','').upper()}</b> on {c.get('date','—')}",
                styles
            ))
 
    # Incidents
    if incidents:
        story.append(_sub_header("Incidents", styles))
        for inc in incidents:
            story.append(Paragraph(
                f"<b>{inc.get('name','—')}</b> (ID: {_val(inc.get('id'))}): "
                f"{inc.get('brief','—')}. Remarks: {_val(inc.get('remarks'))}",
                styles["Alert"]
            ))
 
    # Other matters
    if others:
        story.append(_sub_header("Other Matters", styles))
        for om in others:
            story.append(_body(om.get("description", "—"), styles))
 
    return story
 
 
def _build_hod_sections(report, styles, start_num=3):
    """
    Builds HOD sections.
    Fixed order: CSE group (cse, cys, ds, aiml, aids) → CE (civil) →
    then any other dept that has content.
    """
    story = []
    num = start_num
 
    CSE_GROUP = [
        ("cse",   "CSE"),
        ("cys",   "CSE (CyS)"),
        ("ds",    "CSE (DS)"),
        ("aiml",  "CSE (AI&ML)"),
        ("aids",  "CSE (AI&DS)"),
    ]
    CE_GROUP = [("civil", "CE")]
 
    KNOWN = {c for c, _ in CSE_GROUP + CE_GROUP}
 
    # Collect all dept codes that appear anywhere in the report
    all_codes = set()
    for key in ["events", "staff_participation", "staff_changes", "incidents", "other_matters"]:
        for item in report.get(key, []):
            all_codes.add(item.get("dept", "").lower())
    for d in report.get("attendance", {}).get("departments", []):
        all_codes.add(d.get("dept", "").lower())
 
    OTHER_DEPTS = sorted(all_codes - KNOWN - {"", "library", "lib", "lirc"})
 
    for code, label in CSE_GROUP:
        block = _build_hod_section(code, label, report, styles, num)
        if block:
            story.extend(block)
            num += 1
 
    for code, label in CE_GROUP:
        block = _build_hod_section(code, label, report, styles, num)
        if block:
            story.extend(block)
            num += 1
 
    for code in OTHER_DEPTS:
        if _dept_has_content(code, report):
            block = _build_hod_section(code, code.upper(), report, styles, num)
            if block:
                story.extend(block)
                num += 1
 
    return story, num
 
 
def _build_participation(report, styles, section_num):
    staff_p   = report.get("staff_participation", [])
    student_p = report.get("student_participation", [])
 
    if not staff_p and not student_p:
        return [], section_num
 
    story = [_spacer(), _section_header(f"{section_num}.  Participation by Staff / Students", styles), _spacer(0.1)]
 
    if staff_p:
        story.append(_sub_header("Staff Participation", styles))
        headers = ["S.No", "Name", "Dept", "Event", "Role", "Date"]
        rows = [headers]
        for i, s in enumerate(staff_p, 1):
            rows.append([
                str(i),
                s.get("name", "—"),
                s.get("dept", "—").upper(),
                s.get("event", "—"),
                s.get("status", "—"),
                s.get("date", "—"),
            ])
        col_w = [0.8*cm, 3.5*cm, 1.5*cm, 6*cm, 2*cm, 2.5*cm]
        tbl = Table(rows, colWidths=col_w, repeatRows=1)
        tbl.setStyle(_header_table_style())
        story.append(tbl)
 
    if student_p:
        story.append(_spacer(0.25))
        story.append(_sub_header("Student Participation", styles))
        headers = ["S.No", "Name", "Dept", "Event", "Role", "Date"]
        rows = [headers]
        for i, s in enumerate(student_p, 1):
            rows.append([
                str(i),
                s.get("name", "—"),
                s.get("dept", "—").upper(),
                s.get("event", "—"),
                s.get("status", "—"),
                s.get("date", "—"),
            ])
        col_w = [0.8*cm, 3.5*cm, 1.5*cm, 6*cm, 2*cm, 2.5*cm]
        tbl = Table(rows, colWidths=col_w, repeatRows=1)
        tbl.setStyle(_header_table_style())
        story.append(tbl)
 
    return story, section_num + 1
 
 
def _build_library(report, styles, section_num):
    txn = report.get("library_transactions", {})
    svc = report.get("library_services", {})
 
    if not txn and not svc:
        return [], section_num
 
    story = [_spacer(), _section_header(f"{section_num}.  Particulars of Library Services and Transactions", styles), _spacer(0.1)]
 
    if txn:
        story.append(_sub_header("Library Transactions", styles))
        rows = [
            ["Particulars", "Count"],
            ["Books Issued (Check Out)",          _val(txn.get("books_issued"))],
            ["Books Returned (Check In)",         _val(txn.get("books_returned"))],
            ["Today's Visitors to LIRC",          _val(txn.get("visitors_lirc"))],
            ["Evening Users (5 PM – 8 PM)",       _val(txn.get("visitors_evening_5_to_8"))],
            ["Digital Library Visitors",          _val(txn.get("visitors_digital"))],
            ["Show & Tell Visitors",              _val(txn.get("show_and_tell_visitors"))],
            ["CVPC Visitors",                     _val(txn.get("cvpc_visitors"))],
        ]
        rows = [r for r in rows if r[0] == "Particulars" or r[1] != "—"]
        tbl = Table(rows, colWidths=[10*cm, 3*cm])
        tbl.setStyle(_header_table_style())
        story.append(tbl)
 
    if svc:
        has_svc = any(v for v in svc.values() if v is not None)
        if has_svc:
            story.append(_spacer(0.25))
            story.append(_sub_header("Library Services", styles))
            rows = [
                ["Service", "Count"],
                ["Plagiarism Checks (Turnitin)",  _val(svc.get("plagiarism_checks"))],
                ["Show & Tell",                  _val(svc.get("show_and_tell"))],
                ["Patent Searches",              _val(svc.get("patent_searches"))],
                ["Scopus Indexing Service",      _val(svc.get("scopus_searches"))],
                ["Grammarly Usage",              _val(svc.get("grammarly_usage"))],
                ["Duplicate ID Cards Issued",    _val(svc.get("duplicate_id_cards"))],
            ]
            rows = [r for r in rows if r[0] == "Service" or r[1] != "—"]
            tbl = Table(rows, colWidths=[10*cm, 3*cm])
            tbl.setStyle(_header_table_style())
            story.append(tbl)
 
    return story, section_num + 1
 
 
# ── Header / footer ───────────────────────────────────────────────────────────
 
def _make_header_footer(report_date_str, styles):
    def on_page(canvas, doc):
        canvas.saveState()
        w, h = A4
 
        # Header bar
        canvas.setFillColor(DARK_BLUE)
        canvas.rect(L_MARGIN, h - T_MARGIN - 0.6*cm,
                    CONTENT_W, 0.6*cm, fill=1, stroke=0)
        canvas.setFont("Helvetica-Bold", 9)
        canvas.setFillColor(WHITE)
        canvas.drawString(L_MARGIN + 0.3*cm, h - T_MARGIN - 0.37*cm,
                          "VNRVJIET — DAILY REPORT")
        canvas.drawRightString(w - R_MARGIN - 0.3*cm, h - T_MARGIN - 0.37*cm,
                               report_date_str)
 
        # Footer
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MID_GRAY)
        canvas.drawCentredString(w / 2, B_MARGIN - 0.5*cm,
                                 f"Page {doc.page}  |  Consolidated by AI  |  VNRVJIET Principal's Office")
        canvas.restoreState()
 
    return on_page
 
 
# ── Main entry point ──────────────────────────────────────────────────────────
 
def generate_pdf(report: dict, output_path: str = None) -> bytes:
    """
    Generate the formatted daily report PDF from the consolidated JSON.
 
    Args:
        report:      The full consolidated report dict (the 'report' key from /consolidate response).
        output_path: Optional file path to write the PDF to.
                     If None, returns the PDF as bytes.
 
    Returns:
        PDF as bytes (always), and also writes to output_path if provided.
    """
    styles = _styles()
    buf = io.BytesIO()
 
    report_date_str = report.get("report_date", "—")
    try:
        dt = datetime.strptime(report_date_str, "%Y-%m-%d")
        formatted_date = dt.strftime("%d %B %Y")
    except Exception:
        formatted_date = report_date_str
 
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=L_MARGIN, rightMargin=R_MARGIN,
        topMargin=T_MARGIN + 0.8*cm,   # space for header bar
        bottomMargin=B_MARGIN + 0.5*cm,
        title=f"Daily Report — {formatted_date}",
        author="VNRVJIET Principal's Office",
    )
 
    story = []
 
    # ── Cover title ───────────────────────────────────────────────────────────
    story.append(_spacer(0.4))
    story.append(Paragraph("VNR Vignana Jyothi Institute of Engineering & Technology",
                            styles["ReportTitle"]))
    story.append(Paragraph(f"Daily Report &nbsp;|&nbsp; {formatted_date}",
                            styles["ReportSub"]))
    story.append(_hr())
    story.append(_spacer(0.2))
 
    # ── Section 1: Attendance ─────────────────────────────────────────────────
    story.extend(_build_attendance(report, styles))
 
    # ── Section 2: MTP ───────────────────────────────────────────────────────
    story.extend(_build_mtp(report, styles))
 
    # ── Sections 3+: HOD blocks ───────────────────────────────────────────────
    hod_story, next_num = _build_hod_sections(report, styles, start_num=3)
    story.extend(hod_story)
 
    # ── Participation ─────────────────────────────────────────────────────────
    part_story, next_num = _build_participation(report, styles, next_num)
    story.extend(part_story)
 
    # ── Library ───────────────────────────────────────────────────────────────
    lib_story, _ = _build_library(report, styles, next_num)
    story.extend(lib_story)
 
    story.append(_spacer(1))
 
    # ── Build ─────────────────────────────────────────────────────────────────
    on_page = _make_header_footer(formatted_date, styles)
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
 
    pdf_bytes = buf.getvalue()
 
    if output_path:
        with open(output_path, "wb") as f:
            f.write(pdf_bytes)
 
    return pdf_bytes