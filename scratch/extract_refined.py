import docx
import json

def get_tables(file_path):
    doc = docx.Document(file_path)
    tables_data = []
    for i, table in enumerate(doc.tables):
        rows = []
        for row in table.rows:
            rows.append([cell.text.strip() for cell in row.cells])
        tables_data.append({
            "table_index": i,
            "headers": rows[0] if rows else []
        })
    return tables_data

attendance_file = r"c:\Users\Shiva\MTP-ReportGen\March_2026\30th March 2026\Staff & Student attendance report-30-03-26.docx"
mtp_file = r"c:\Users\Shiva\MTP-ReportGen\March_2026\31st March 2026\Daily Report 31st March 2026-MTP.docx"

print("--- ATTENDANCE ---")
print(json.dumps(get_tables(attendance_file), indent=2))
print("--- MTP ---")
print(json.dumps(get_tables(mtp_file), indent=2))
