import os
from docx import Document

def extract_library_stats(doc_path):
    stats = {"books_issued": 0, "books_returned": 0, "visits": 0}
    try:
        doc = Document(doc_path)
        for table in doc.tables:
            for row in table.rows:
                cells = [c.text.strip().lower() for c in row.cells]
                if len(cells) >= 3:
                    text = cells[1].lower()
                    val = row.cells[2].text.strip()
                    
                    if "issued" in text and "books" in text:
                        stats["books_issued"] = val
                    elif "returned" in text and "books" in text:
                        stats["books_returned"] = val
                    elif "today" in text and "visitors" in text:
                        stats["visits"] = val
    except Exception as e:
        pass
    return stats
