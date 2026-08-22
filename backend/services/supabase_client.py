"""
Supabase client for generated reports (storage) and a shared Postgres API client.

Live portal tables (users, sessions, submissions) use get_admin_client() so the
server can write under the service role key. The publishable/anon key is not
enough once RLS is enabled.
"""

import os
from typing import Optional

from dotenv import load_dotenv
load_dotenv()


def _normalize_supabase_url(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    if url.endswith("/rest/v1"):
        url = url[: -len("/rest/v1")]
    return url.rstrip("/")


def _create_client():
    try:
        from supabase import create_client
    except Exception:
        return None, False

    url = _normalize_supabase_url(os.environ.get("SUPABASE_URL", ""))
    service_key = (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        or os.environ.get("SUPABASE_SECRET_KEY", "").strip()
    )
    fallback_key = os.environ.get("SUPABASE_KEY", "").strip()
    key = service_key or fallback_key

    if not url or not key:
        return None, False

    try:
        client = create_client(url, key)
        return client, bool(service_key)
    except Exception as e:
        print(f"[WARNING] Could not create Supabase client: {e}")
        return None, False


supabase, _using_service_role = _create_client()
SUPABASE_ENABLED = supabase is not None

if SUPABASE_ENABLED and not _using_service_role:
    print(
        "[WARNING] SUPABASE_SERVICE_ROLE_KEY is not set. "
        "Using SUPABASE_KEY. Portal writes may fail after RLS is enabled. "
        "Add the secret/service_role key from Supabase > Settings > API Keys."
    )

BUCKET_NAME = "reports"
TABLE_NAME = "reports"


def is_enabled() -> bool:
    return SUPABASE_ENABLED


def get_admin_client():
    """Shared Supabase client (service role when configured)."""
    return supabase


def save_report(
    report_date: str,
    departments: list[str],
    docx_bytes: bytes,
    filename: str,
    metadata: Optional[dict] = None,
) -> Optional[dict]:
    if not SUPABASE_ENABLED:
        return None

    file_path = f"{report_date}/{filename}"
    try:
        supabase.storage.from_(BUCKET_NAME).upload(
            file_path,
            docx_bytes,
            file_options={"content-type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
        )
    except Exception as e:
        if "Duplicate" in str(e) or "already exists" in str(e):
            supabase.storage.from_(BUCKET_NAME).update(
                file_path,
                docx_bytes,
                file_options={"content-type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
            )
        else:
            print(f"[WARNING] Storage upload failed: {e}")
            file_path = None

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
        return result.data or []
    except Exception as e:
        print(f"[WARNING] Failed to list reports: {e}")
        return []


def get_report(report_id: str) -> Optional[dict]:
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
    if not SUPABASE_ENABLED:
        return None

    try:
        return supabase.storage.from_(BUCKET_NAME).download(file_path)
    except Exception as e:
        print(f"[WARNING] Failed to download report: {e}")
        return None
