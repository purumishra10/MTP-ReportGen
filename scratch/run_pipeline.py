"""Quick pipeline test script."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

from backend.services.structured_extractor import extract_structured_data
from backend.batch_processor import get_dept_code, LIBRARY_DEPT_CODES, _dept_name_from_code
from backend.services.ai_service import consolidate
from backend.services.report_generator import generate_docx

folder = r"c:\Users\Shiva\MTP-ReportGen\March_2026\31st March 2026"
report_date = "2026-03-31"
dept_data = []
seen = set()

for filename in sorted(os.listdir(folder)):
    if not filename.endswith(".docx") or filename.startswith("~"):
        continue
    dept_code = get_dept_code(filename)
    if dept_code in seen:
        continue
    seen.add(dept_code)
    is_library = dept_code in LIBRARY_DEPT_CODES
    dept_name = _dept_name_from_code(dept_code)
    try:
        with open(os.path.join(folder, filename), "rb") as f:
            data = extract_structured_data(f.read(), dept_code, dept_name, is_library=is_library)
        dept_data.append(data)
        print("OK", dept_code)
    except Exception as e:
        print("ERR", dept_code, str(e)[:60])

print("\nConsolidating %d departments..." % len(dept_data))
consolidated = consolidate(report_date, dept_data)

# Save JSON
os.makedirs("generated_reports", exist_ok=True)
with open("generated_reports/consolidated_2026-03-31.json", "w", encoding="utf-8") as f:
    json.dump(consolidated, f, indent=2, ensure_ascii=False)
print("JSON saved")

# Check key data
att = consolidated.get("overall_staff_attendance_table", [])
print("Staff att table rows:", len(att))
mtp_nar = consolidated.get("mtp_narrative", "")
mtp_pills = consolidated.get("mtp_batch_pills", "")
print("MTP narrative:", len(mtp_nar), "chars")
print("MTP batch pills:", len(mtp_pills), "chars")
if mtp_nar:
    print("  Preview:", mtp_nar[:200])

# Generate DOCX
output = "generated_reports/daily_report_2026-03-31.docx"
generate_docx(consolidated, output_path=output, all_images=[])
print("DOCX generated:", output)
