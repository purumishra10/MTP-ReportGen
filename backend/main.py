import os
import argparse
from datetime import datetime

from extractors.attendance import extract_attendance
from extractors.mtp_content import extract_mtp
from extractors.media import extract_images
from extractors.library import extract_library_stats
from generators.master_report import generate_master_report
from database import init_db, save_mtp_record, get_records_by_date, get_executive_summary

# Expected Departments
DEPARTMENTS = ["CSE", "IT", "M&MS", "Library", "IQAC"]

def generate_from_db(date_str):
    print(f"Generating MTP Report from DATABASE for date: {date_str}")
    
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d") # API submits YYYY-MM-DD
    except ValueError:
        dt = datetime.strptime(date_str, "%d-%m-%Y")
        
    date_formatted_display = dt.strftime("%d.%m.%Y")
    
    month_name = dt.strftime("%B_%Y")
    output_dir = os.path.join(os.path.dirname(__file__), "..", month_name)
    os.makedirs(output_dir, exist_ok=True)
    
    output_file = os.path.join(output_dir, f"Master_Daily_Report_{dt.strftime('%d-%m-%Y')}.docx")
    template_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../Sample_DRs/Empty Daily DR.docx"))
    
    records = get_records_by_date(date_str, require_approved=True)
    if not records:
        raise Exception(f"No APPROVED database records found for date {date_str}")
        
    all_mtp = {}
    found_departments = set()
    
    for dept_name, placement_text in records:
        if placement_text:
            all_mtp[dept_name] = placement_text.split('\n')
        found_departments.add(dept_name)
        
    missing_depts = [d for d in DEPARTMENTS if d not in found_departments]
    
    # Fetch executive summary
    summary_res = get_executive_summary(date_str)
    executive_summary = summary_res[0] if summary_res else None
    
    generate_master_report(template_path, output_file, [], all_mtp, [], missing_depts, None, executive_summary=executive_summary)
    return output_file
DEPARTMENTS = ["CSE", "IT", "M&MS", "Library", "IQAC"]

def main(date_str, source_dir=None):
    print(f"Starting MTP Report Generator for date: {date_str}")
    init_db()
    
    if source_dir is None:
        source_dir = os.path.join(os.path.dirname(__file__), "../Sample_DRs")
        
    try:
        dt = datetime.strptime(date_str, "%d.%m.%Y")
    except ValueError:
        dt = datetime.strptime(date_str, "%Y-%m-%d") # accept HTML5 date format
        date_str = dt.strftime("%d.%m.%Y") # normalize
        
    month_name = dt.strftime("%B_%Y")
    output_dir = os.path.join(os.path.dirname(__file__), "..", month_name)
    os.makedirs(output_dir, exist_ok=True)
    
    output_file = os.path.join(output_dir, f"Master_Daily_Report_{dt.strftime('%d-%m-%Y')}.docx")
    
    # Empty template is expected to be statically present in Sample_DRs
    template_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../Sample_DRs/Empty Daily DR.docx"))
    
    all_attendance = []
    all_mtp = {}
    all_images = []
    found_departments = set()
    library_data = None
    
    for filename in os.listdir(source_dir):
        if not filename.endswith(".docx") or "Empty" in filename:
            continue
            
        filepath = os.path.join(source_dir, filename)
        
        dept_name = "Unknown"
        for d in DEPARTMENTS + ["AE", "ECE"]:
            if d.lower() in filename.lower():
                dept_name = d
                break
                
        # Handle special cases based on file names
        if "M&MS" in filename:
            dept_name = "M&MS"
        elif "IQAC" in filename:
            dept_name = "IQAC"
        elif "Library" in filename:
            dept_name = "Library"
            library_data = extract_library_stats(filepath)
            
        elif "IT" in filename:
            dept_name = "IT"
            
        found_departments.add(dept_name)
        print(f"Processing ({dept_name}): {filename}")
        
        attendance = extract_attendance(filepath, dept_name)
        all_attendance.extend(attendance)
        
        mtp = extract_mtp(filepath)
        if mtp:
            all_mtp[dept_name] = mtp
            mtp_text_joined = "\n".join(mtp)
            save_mtp_record(date_str, dept_name, mtp_text_joined)
            
        images = extract_images(filepath)
        all_images.extend(images)

    missing_depts = []
    for d in DEPARTMENTS:
        if d not in found_departments:
            missing_depts.append(d)
        
    mtp_count = sum(len(v) for v in all_mtp.values())
    print(f"Extracted {len(all_attendance)} absent remarks, {mtp_count} paragraphs of MTP text.")
    generate_master_report(template_path, output_file, all_attendance, all_mtp, all_images, missing_depts, library_data)
    
    return output_file

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MTP Report Generator")
    parser.add_argument("--date", type=str, default="17.02.2026", help="Date in DD.MM.YYYY format")
    args = parser.parse_args()
    main(args.date)
