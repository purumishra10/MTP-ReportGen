import os
import io
from typing import Optional
from datetime import datetime

from backend.database import get_records_by_date, get_executive_summary
from backend.services.ai_service import consolidate
from backend.services.report_generator import generate_docx
from backend.services import supabase_client

# Dictionary mapping from short code to full name for the final docx
from backend.batch_processor import DEPT_MAPPING

def _dept_name_from_code(code: str) -> str:
    return DEPT_MAPPING.get(code.lower(), code.upper())

def generate_from_portal(date_str: str) -> Optional[bytes]:
    """
    Generates a consolidated report specifically pulling from the portal's SQLite database 
    rather than from uploaded files.
    
    1. Fetch all 'approved' mtp_records for the given date
    2. Format into the ai_service input shape (List of dicts)
    3. Run AI consolidation
    4. Fetch executive summary
    5. Generate the DOCX file
    """
    records = get_records_by_date(date_str)
    
    # Filter for only approved reports
    approved_records = [r for r in records if r["status"] == "approved"]
    
    if not approved_records:
        raise ValueError(f"No approved department submissions found for {date_str}.")

    # Format for AI service
    dept_reports = []
    for record in approved_records:
        dept_code = record["department"]
        dept_name = _dept_name_from_code(dept_code)
        
        # If the content contains raw HTML from the rich text editor, it would be okay,
        # Gemini handles HTML reasonably well. But standardizing to plain text is better.
        text = record["content"] or ""
        
        # Extract images from HTML string if any?
        # For now, the portal doesn't allow image upload natively to the DB (it saves base64 in HTML)
        # We will just pass the raw text to AI.
        
        dept_reports.append({
            "dept_code": dept_code,
            "dept_name": dept_name,
            "text": text,
        })
        
    print(f"[INFO] Running AI consolidation for {date_str} from portal database...")
    
    # Run the same AI logic as main branch
    final_json = consolidate(date_str, dept_reports)
    
    # Add executive summary if present
    exec_summary_record = get_executive_summary(date_str)
    if exec_summary_record and exec_summary_record.get("content"):
        # The frontend sends HTML, but the docx generator needs text/bullet points.
        # We can either pass it raw, or the docx generator will need to handle HTML.
        # Right now the report generator doesn't have an Executive Summary section builder.
        # Let's inject it into the final_json under a new key.
        final_json["executive_summary"] = exec_summary_record["content"]

    # Generate the DOCX bytes
    docx_bytes = generate_docx(final_json)
    
    # Supabase optional upload
    if supabase_client.is_enabled():
        try:
            dept_codes = [r["dept_code"] for r in dept_reports]
            filename = f"daily_report_{date_str}.docx"
            supabase_client.save_report(
                report_date=date_str,
                departments=dept_codes,
                docx_bytes=docx_bytes,
                filename=filename,
                metadata={"source": "portal"}
            )
            print(f"[INFO] Uploaded portal report to Supabase: {date_str}")
        except Exception as e:
            print(f"[WARN] Supabase upload failed: {e}")
            
    return docx_bytes
