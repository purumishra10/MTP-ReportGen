import io
import os

DEPT_TABLE_LABELS = [
    "Staff Attendance",
    "Infrastructure Issues or Maintenance",
    "Events / Seminars / Workshops",
    "Participation by Staff",
    "Particiption by Students",
    "Staff Joined or Left",
    "Classword Adjustments / Lecture Interchange",
    "Incidents (Discipline)",
    "Any Other Matter",
]

LIBRARY_TABLE_NAMES = [
    "Staff Attendance",
    "Infrastructure Issues or Maintenance",
    "Staff Joined or LEft",
    "Library Services and Transactions",
    "Plagiarism / Show and Tell / Patent / Scopus / Grammarly / Duplicate IDs"
]

def normalize(file_bytes: bytes, filename: str, is_library: bool = False) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".docx":
        return _extract_docx(file_bytes, is_library)
    elif ext == ".pdf":
        return _extract_pdf(file_bytes)
    else:
        raise ValueError(f"Unsupported file type: {ext}. Only .docx and .pdf are accepted.")
    
def _extract_docx(file_bytes: bytes, is_library: bool) -> str:
    from docx import Document

    doc = Document(io.BytesIO(file_bytes))
    labels = LIBRARY_TABLE_NAMES if is_library else DEPT_TABLE_LABELS
    output = []

    for i, table in enumerate(doc.tables):
        label = labels[i] if i < len(labels) else f"Section {i+1}"
        rows = []

        for row in table.rows:
            cells = []
            for cell in row.cells:
                text = cell.text.strip().replace("\n", " ").replace("\r", "")
                cells.append(text)

            if not any(c.strip() for c in cells):
                continue
            if len(set(cells)) == 1 and not cells[0].strip():
                continue
            
            rows.append(" | ".join(cells))
        
        if rows:
            output.append(f"[{label}]")
            output.extend(rows)
            output.append("")

    loose_paras = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if text and len(text) > 5:
            loose_paras.append(text)
    
    if loose_paras:
        output.append("[Free Text / Other Notes]")
        output.extend(loose_paras)
    
    return "\n".join(output) if output else "[No content extracted]"

def _extract_pdf(file_bytes: bytes) -> str:
    import fitz

    doc = fitz.open(stream=file_bytes, filetype="pdf")
    pages = []
    for page_num, page in enumerate(doc):
        text = page.get_text("text").strip()
        if text:
            pages.append(f"[Page {page_num + 1}]\n{text}")
    doc.close()

    return "\n\n".join(pages) if pages else "[No content extracted]"

def truncate(text: str, max_chars: int = 5000) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n[...truncated for length]"
