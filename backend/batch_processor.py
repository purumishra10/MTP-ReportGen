import os
import re
import asyncio
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from backend.services.normalizer import normalize, truncate, extract_images
from backend.services.ai_service import consolidate
from backend.services.report_generator import generate_docx
from backend.services import supabase_client

# Department mapping from main.py
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
    "chem":      "Chemical Engineering",
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
    return DEPT_MAPPING.get(code, code.upper())

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
    
    # Check others
    for code in DEPT_MAPPING.keys():
        if code in filename:
            return code
    return "unknown"

async def process_day(day_folder_path):
    folder_name = os.path.basename(day_folder_path)
    report_date = parse_date(folder_name)
    
    if not report_date:
        print(f"[SKIP] Could not parse date from folder: {folder_name}")
        return

    print(f"\n[INFO] Processing Day: {report_date} ({folder_name})")
    
    files = [f for f in os.listdir(day_folder_path) if f.endswith(('.docx', '.pdf'))]
    if not files:
        print(f"[SKIP] No .docx or .pdf files in {folder_name}")
        return

    dept_reports = []
    all_images = []
    
    for filename in files:
        file_path = os.path.join(day_folder_path, filename)
        dept_code = get_dept_code(filename)
        
        if dept_code == "unknown":
            print(f"[WARN] Could not identify department for: {filename}")
            # Fallback to filename stem
            dept_code = os.path.splitext(filename)[0].lower()[:10]

        is_library = dept_code in LIBRARY_DEPT_CODES
        dept_name = _dept_name_from_code(dept_code)

        try:
            with open(file_path, "rb") as f:
                file_bytes = f.read()
            
            text = normalize(file_bytes, filename, is_library=is_library)
            text = truncate(text, max_chars=15000)
            
            if text == "[No content extracted]":
                print(f"[WARN] No text extracted from {filename}")
                continue

            images = extract_images(file_bytes, filename, dept_code)
            all_images.extend(images)

            dept_reports.append({
                "dept_code": dept_code,
                "dept_name": dept_name,
                "text": text,
            })
            print(f"  [V] Processed: {dept_name} ({filename})")
            
        except Exception as e:
            print(f"  [X] Failed to process {filename}: {e}")

    if not dept_reports:
        print(f"[ERROR] No reports processed for {report_date}")
        return

    # Deduplicate template images
    if all_images:
        import hashlib
        from collections import Counter
        hash_counts = Counter()
        for img in all_images:
            img["_hash"] = hashlib.md5(img["image_bytes"]).hexdigest()
            hash_counts[img["_hash"]] += 1
        template_hashes = {h for h, c in hash_counts.items() if c >= 3}
        all_images = [img for img in all_images if img["_hash"] not in template_hashes]

    # AI Consolidation
    print(f"[INFO] Running AI consolidation for {report_date}...")
    try:
        consolidated = consolidate(report_date, dept_reports)
        
        # Output setup
        output_dir = "generated_reports"
        os.makedirs(output_dir, exist_ok=True)
        filename = f"daily_report_{report_date}.docx"
        output_path = os.path.join(output_dir, filename)
        
        # DOCX Generation
        docx_bytes = generate_docx(consolidated, output_path=output_path, all_images=all_images)
        print(f"[SUCCESS] Generated: {output_path}")
        
        # Optional: Supabase upload
        if supabase_client.is_enabled():
            try:
                dept_codes = [r["dept_code"] for r in dept_reports]
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

    for day_folder in day_folders:
        await process_day(day_folder)

if __name__ == "__main__":
    asyncio.run(main())
