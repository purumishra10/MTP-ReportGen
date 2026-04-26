import os
import sys
import asyncio
from dotenv import load_dotenv

# Make sure we can import backend
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

from backend.services.structured_extractor import extract_structured_data
from backend.batch_processor import get_dept_code, LIBRARY_DEPT_CODES, _dept_name_from_code
from backend.services.ai_service import consolidate
from backend.services.report_generator import generate_docx

def main():
    folder = r"c:\Users\Shiva\MTP-ReportGen\March_2026\31st March 2026"
    report_date = "2026-03-31"

    if not os.path.isdir(folder):
        print(f"Folder not found: {folder}")
        return

    dept_data = []

    for filename in sorted(os.listdir(folder)):
        if filename.endswith(".docx") or filename.endswith(".pdf"):
            path = os.path.join(folder, filename)
            with open(path, "rb") as f:
                file_bytes = f.read()
                
            print(f"Processing: {filename}")
            dept_code = get_dept_code(filename)
            if dept_code == "unknown":
                dept_code = os.path.splitext(filename)[0].lower()[:10]

            is_library = dept_code in LIBRARY_DEPT_CODES
            dept_name = _dept_name_from_code(dept_code)

            try:
                data = extract_structured_data(file_bytes, dept_code, dept_name, is_library=is_library)
                dept_data.append(data)
                print(" -> OK")
            except Exception as e:
                print(f" -> ERROR: {e}")

    print("\nRunning consolidation...")
    consolidated = consolidate(report_date, dept_data)

    output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "generated_reports")
    os.makedirs(output_dir, exist_ok=True)
    filename_out = f"daily_report_{report_date}.docx"
    output_path = os.path.join(output_dir, filename_out)

    print("\nGenerating DOCX...")
    generate_docx(consolidated, output_path=output_path, all_images=[])
    print(f"Done! Saved to: {output_path}")

if __name__ == "__main__":
    main()
