"""
Supabase integration for storing and retrieving generated reports.
"""

import os
import io
from datetime import date
from typing import Optional

try:
    from supabase import create_client, Client

    SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
    SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

    if SUPABASE_URL and SUPABASE_KEY:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        SUPABASE_ENABLED = True
    else:
        supabase = None
        SUPABASE_ENABLED = False
except Exception:
    supabase = None
    SUPABASE_ENABLED = False


BUCKET_NAME = "reports"
TABLE_NAME = "reports"


def is_enabled() -> bool:
    """Check if Supabase is configured and available."""
    return SUPABASE_ENABLED


def save_report(
    report_date: str,
    departments: list[str],
    docx_bytes: bytes,
    filename: str,
    metadata: Optional[dict] = None,
) -> Optional[dict]:
    """
    Save a generated report to Supabase.

    Args:
        report_date: Date in YYYY-MM-DD format
        departments: List of department codes that were included
        docx_bytes: The generated DOCX file as bytes
        filename: Filename for storage (e.g. "daily_report_2026-03-16.docx")
        metadata: Optional additional metadata

    Returns:
        The inserted record dict, or None if Supabase is not enabled
    """
    if not SUPABASE_ENABLED:
        return None

    # Upload file to storage
    file_path = f"{report_date}/{filename}"
    try:
        supabase.storage.from_(BUCKET_NAME).upload(
            file_path,
            docx_bytes,
            file_options={"content-type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
        )
    except Exception as e:
        # If file already exists, update it
        if "Duplicate" in str(e) or "already exists" in str(e):
            supabase.storage.from_(BUCKET_NAME).update(
                file_path,
                docx_bytes,
                file_options={"content-type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
            )
        else:
            print(f"[WARNING] Storage upload failed: {e}")
            file_path = None

    # Insert record into database
    record = {
        "report_date": report_date,
        "departments": departments,
        "file_path": file_path or filename,
        "metadata": metadata or {},
    }

    try:
        result = supabase.table(TABLE_NAME).insert(record).execute()
        return result.data[0] if result.data else record
    except Exception as e:
        print(f"[WARNING] Database insert failed: {e}")
        return record


def list_reports(limit: int = 50) -> list[dict]:
    """List all reports, most recent first."""
    if not SUPABASE_ENABLED:
        return []

    try:
        result = (
            supabase.table(TABLE_NAME)
            .select("*")
            .order("report_date", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data
    except Exception as e:
        print(f"[WARNING] Failed to list reports: {e}")
        return []


def get_report(report_id: str) -> Optional[dict]:
    """Get a specific report by ID."""
    if not SUPABASE_ENABLED:
        return None

    try:
        result = (
            supabase.table(TABLE_NAME)
            .select("*")
            .eq("id", report_id)
            .single()
            .execute()
        )
        return result.data
    except Exception as e:
        print(f"[WARNING] Failed to get report: {e}")
        return None


def get_report_file(file_path: str) -> Optional[bytes]:
    """Download a report file from Supabase storage."""
    if not SUPABASE_ENABLED:
        return None

    try:
        data = supabase.storage.from_(BUCKET_NAME).download(file_path)
        return data
    except Exception as e:
        print(f"[WARNING] Failed to download report: {e}")
        return None
