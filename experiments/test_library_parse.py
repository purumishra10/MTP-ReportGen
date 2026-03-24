import os
from docx import Document

doc_path = os.path.join(os.path.dirname(__file__), '../Sample_DRs/16.02.2026 Library_Daily Report.docx')
doc = Document(doc_path)

print("--- Library Dept Tables ---")
for i, table in enumerate(doc.tables):
    print(f"Table {i} rows: {len(table.rows)}")
    for j, row in enumerate(table.rows):
        print(f"  Row {j}: {[cell.text.strip() for cell in row.cells]}")
