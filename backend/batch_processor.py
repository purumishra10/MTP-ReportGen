"""
Batch Processor â€” Process all daily report folders
====================================================
Uses the hybrid pipeline:
1. structured_extractor.py for deterministic data extraction
2. ai_service.py for narrative summarization only
3. report_generator.py for DOCX output
"""

import os
import re
import json
import asyncio
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from backend.services.structured_extractor import extract_structured_data
from backend.services.ai_service import consolidate
from backend.services.report_generator import generate_docx
from backend.services import supabase_client

# Department mapping
DEPT_MAPPING = {
    "cse":       "Computer Science & Engineering",
    "cys":       "Cyber Security, Data Science & AIDS",
    "aiml":      "Artificial Intelligence & Machine Learning, and IoT",
    "it":        "Information Technology",
    "ece":       "Electronics & Communication Engineering",
    "eee":       "Electrical & Electronics Engineering",
    "eie":       "Electronics & Instrumentation Engineering",
    "me":        "Mechanical Engineering",
    "mech":      "Mechanical Engineering",
    "civil":     "Civil Engineering",
    "chem":      "Chemistry Department",
    "chemistry": "Chemistry Department",
    "ae":        "Automobile Engineering",
    "mtp":       "Mentorship, Training & Placements",
    "english":   "English Department",
    "eng":       "English Department",
    "m&ms":      "Management & Mathematical Sciences",
    "ms":        "Management & Mathematical Sciences",
    "library":   "Library & Information Resource Centre",
    "lib":       "Library & Information Resource Centre",
    "lirc":      "Library & Information Resource Centre",
}

LIBRARY_DEPT_CODES = {"library", "lib", "lirc"}

def _dept_name_from_code(code: str) -> str:
    return DEPT_MAPPING.get((code or "").lower(), (code or "").upper())

def parse_date(date_str):
    """Parse dates like '24th March 2026' into 'YYYY-MM-DD'."""
    # Remove ordinal suffixes (st, nd, rd, th)
    clean_date = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', date_str, flags=re.IGNORECASE).strip()
    
    formats = [
        "%d %B %Y",  # 24 March 2026
        "%d-%m-%Y",  # 24-03-2026
        "%d-%b-%Y",  # 24-Mar-2026
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(clean_date, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None

def get_dept_code(filename):
    """Extract department code from filename based on keywords."""
    filename = filename.lower()
    # Priority for specific departments
    if "cys" in filename or "ds" in filename: return "cys"
    if "aiml" in filename or "iot" in filename: return "aiml"
    if "mtp" in filename: return "mtp"
    if "m&ms" in filename or "management" in filename: return "m&ms"
    if "library" in filename: return "library"
    
    if "attendance" in filename: return "attendance_report"
    
    # Check others
    for code in DEPT_MAPPING.keys():
        if code in filename:
            return code
    return "unknown"

async def process_day(day_folder_path, dump_json=False):
    """Process all department reports for a single day.
    
    Args:
        day_folder_path: Path to the day folder (e.g., 'March_2026/24th March 2026')
        dump_json: If True, save the intermediate consolidated JSON for inspection
    """
    folder_name = os.path.basename(day_folder_path)
    report_date = parse_date(folder_name)
    
    if not report_date:
        print(f"[SKIP] Could not parse date from folder: {folder_name}")
        return

    print(f"\n[INFO] Processing Day: {report_date} ({folder_name})")
    
    files = [f for f in os.listdir(day_folder_path) if f.endswith(('.docx', '.pdf')) and not f.startswith('~')]
    if not files:
        print(f"[SKIP] No .docx or .pdf files in {folder_name}")
        return

    # â”€â”€ Phase 1: Deterministic extraction â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    dept_data = []
    seen_dept_codes = set()  # Deduplicate
    
    for filename in sorted(files):
        file_path = os.path.join(day_folder_path, filename)
        dept_code = get_dept_code(filename)
        
        if dept_code == "unknown":
            print(f"[WARN] Could not identify department for: {filename}")
            continue

        # Skip duplicate department files (e.g., AE has 4 copies)
        if dept_code in seen_dept_codes:
            print(f"  [SKIP] Duplicate {dept_code}: {filename}")
            continue
        seen_dept_codes.add(dept_code)

        is_library = dept_code in LIBRARY_DEPT_CODES
        dept_name = _dept_name_from_code(dept_code)

        try:
            with open(file_path, "rb") as f:
                file_bytes = f.read()
            
            data = extract_structured_data(file_bytes, dept_code, dept_name, is_library=is_library)
            
            if dept_code == "attendance_report":
                from backend.services.chart_extractor import extract_charts_from_docx
                print(f"  [INFO] Extracting charts from {filename}...")
                charts = extract_charts_from_docx(file_path, "scratch")
                data["attendance_charts"] = charts
                print(f"  [OK] Extracted {len(charts)} charts")

            dept_data.append(data)
            
            # Print extraction summary
            att = data.get("attendance") or data.get("library_attendance")
            att_str = f"on_rolls={att['on_rolls']}" if att else "no-attendance"
            print(f"  [OK] {dept_name} ({filename}) -- {att_str}")
            
        except Exception as e:
            print(f"  [ERR] Failed to process {filename}: {e}")


    if not dept_data:
        print(f"[ERROR] No reports processed for {report_date}")
        return

    # â”€â”€ Phase 2: AI Consolidation (hybrid) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    print(f"[INFO] Running hybrid consolidation for {report_date}...")
    print(f"  Deterministic: {len(dept_data)} departments extracted")
    
    narrative_count = sum(1 for d in dept_data 
                         if any(d.get(k, "").strip() 
                               for k in ["events_text", "staff_participation_text", 
                                         "student_participation_text", "other_matters_text"]))
    print(f"  Narrative (â†’ LLM): {narrative_count} departments have narrative content")
    
    try:
        consolidated = consolidate(report_date, dept_data)
        
        # Dump intermediate JSON for inspection
        if dump_json:
            json_dir = "generated_reports"
            os.makedirs(json_dir, exist_ok=True)
            json_path = os.path.join(json_dir, f"consolidated_{report_date}.json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(consolidated, f, indent=2, ensure_ascii=False)
            print(f"[INFO] JSON dump: {json_path}")
        
        # Output setup
        output_dir = "generated_reports"
        os.makedirs(output_dir, exist_ok=True)
        filename = f"daily_report_{report_date}.docx"
        output_path = os.path.join(output_dir, filename)
        
        # DOCX Generation (no images for now)
        docx_bytes = generate_docx(consolidated, output_path=output_path, all_images=[])
        print(f"[SUCCESS] Generated: {output_path}")
        
        # Print summary stats
        att_depts = consolidated.get("attendance", {}).get("departments", [])
        events = consolidated.get("department_highlights", [])
        total_events = sum(len(d.get("events", [])) for d in events) if events else 0
        print(f"  Stats: {len(att_depts)} departments, {total_events} events, "
              f"{len(consolidated.get('infrastructure_issues', []))} infra issues")
        
        # Optional: Supabase upload
        if supabase_client.is_enabled():
            try:
                dept_codes = [d["dept_code"] for d in dept_data]
                supabase_client.save_report(
                    report_date=report_date,
                    departments=dept_codes,
                    docx_bytes=docx_bytes,
                    filename=filename,
                    metadata={"batch": True}
                )
                print(f"[INFO] Uploaded to Supabase: {report_date}")
            except Exception as e:
                print(f"[WARN] Supabase upload failed: {e}")
                
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[ERROR] Consolidation failed for {report_date}: {e}")

async def main():
    base_data_dir = "March_2026"
    if not os.path.exists(base_data_dir):
        print(f"[ERROR] Base data directory not found: {base_data_dir}")
        return

    # Sort folders to process in order
    day_folders = sorted([
        os.path.join(base_data_dir, d) 
        for d in os.listdir(base_data_dir) 
        if os.path.isdir(os.path.join(base_data_dir, d))
    ])

    print(f"[INFO] Found {len(day_folders)} day folders to process")
    print(f"[INFO] Pipeline: Deterministic extraction + LLM narrative summarization")
    print(f"[INFO] Images: DISABLED for testing")
    print()
    
    for day_folder in day_folders:
        await process_day(day_folder, dump_json=True)

if __name__ == "__main__":
    asyncio.run(main())

