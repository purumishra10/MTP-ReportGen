"""
Portal data access.

Uses Supabase Postgres when SUPABASE_URL + a key are set.
Falls back to local SQLite for offline development.
"""

import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from backend.services.supabase_client import get_admin_client, is_enabled as supabase_is_enabled

DATABASE_FILE = "backend/data/daily_data.db"
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "supabase_schema.sql")


def _use_supabase() -> bool:
    return supabase_is_enabled() and get_admin_client() is not None


def _sb():
    client = get_admin_client()
    if client is None:
        raise RuntimeError("Supabase client is not configured")
    return client


def _parse_dt(value) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(text[:19], fmt)
            except ValueError:
                continue
    return None


def _as_date_str(value) -> str:
    if value is None:
        return ""
    text = str(value)
    return text[:10]


# ── SQLite (local fallback) ──────────────────────────────────────────────────

def get_connection():
    os.makedirs(os.path.dirname(DATABASE_FILE), exist_ok=True)
    conn = sqlite3.connect(DATABASE_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _init_sqlite():
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            department TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            FOREIGN KEY(username) REFERENCES users(username)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS mtp_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_date DATE NOT NULL,
            department TEXT NOT NULL,
            content TEXT,
            status TEXT DEFAULT 'draft',
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(report_date, department)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS executive_summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_date DATE NOT NULL UNIQUE,
            content TEXT NOT NULL,
            status TEXT DEFAULT 'draft',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()


def _supabase_tables_ready() -> bool:
    try:
        _sb().table("users").select("username").limit(1).execute()
        _sb().table("mtp_records").select("id").limit(1).execute()
        return True
    except Exception as e:
        print(
            "[ERROR] Supabase portal tables are missing or unreachable.\n"
            f"        {e}\n"
            f"        Run the SQL in {SCHEMA_PATH} in the Supabase SQL Editor.\n"
            "        Set SUPABASE_SERVICE_ROLE_KEY (Settings > API Keys > secret or service_role)."
        )
        return False


def _maybe_migrate_sqlite():
    """Copy local SQLite rows into empty Supabase tables (one-time)."""
    if not os.path.exists(DATABASE_FILE):
        return
    try:
        existing = _sb().table("mtp_records").select("id").limit(1).execute()
        if existing.data:
            return
        users = _sb().table("users").select("username").limit(1).execute()
        conn = get_connection()
        c = conn.cursor()
        if not (users.data):
            c.execute("SELECT username, password_hash, role, department FROM users")
            rows = [dict(r) for r in c.fetchall()]
            if rows:
                _sb().table("users").upsert(rows, on_conflict="username").execute()
                print(f"[INFO] Migrated {len(rows)} users from SQLite to Supabase")
        c.execute("SELECT report_date, department, content, status, submitted_at FROM mtp_records")
        recs = []
        for r in c.fetchall():
            recs.append({
                "report_date": _as_date_str(r["report_date"]),
                "department": r["department"],
                "content": r["content"],
                "status": r["status"],
                "submitted_at": r["submitted_at"] or datetime.utcnow().isoformat(),
            })
        if recs:
            _sb().table("mtp_records").upsert(recs, on_conflict="report_date,department").execute()
            print(f"[INFO] Migrated {len(recs)} submissions from SQLite to Supabase")
        c.execute("SELECT report_date, content, status, updated_at FROM executive_summaries")
        sums = []
        for r in c.fetchall():
            sums.append({
                "report_date": _as_date_str(r["report_date"]),
                "content": r["content"],
                "status": r["status"],
                "updated_at": r["updated_at"] or datetime.utcnow().isoformat(),
            })
        if sums:
            _sb().table("executive_summaries").upsert(sums, on_conflict="report_date").execute()
            print(f"[INFO] Migrated {len(sums)} executive summaries from SQLite to Supabase")
        conn.close()
    except Exception as e:
        print(f"[WARNING] SQLite to Supabase migration skipped: {e}")


def init_db():
    if _use_supabase():
        print("[INFO] Using Supabase Postgres for portal data")
        if _supabase_tables_ready():
            init_db._pg_ok = True
            _maybe_migrate_sqlite()
            return
        print("[WARNING] Falling back to SQLite until Supabase tables are created")
    else:
        print("[INFO] Supabase not configured - using local SQLite")
    init_db._pg_ok = False
    _init_sqlite()


init_db._pg_ok = False


def _pg() -> bool:
    return bool(getattr(init_db, "_pg_ok", False))


# ── Users ────────────────────────────────────────────────────────────────────

def get_user(username: str):
    if _pg():
        result = _sb().table("users").select("*").eq("username", username).limit(1).execute()
        return result.data[0] if result.data else None
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username = ?", (username,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def count_users() -> int:
    if _pg():
        result = _sb().table("users").select("username", count="exact").limit(1).execute()
        return result.count if result.count is not None else len(result.data or [])
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as count FROM users")
    row = c.fetchone()
    conn.close()
    return int(row["count"]) if row else 0


def insert_user(username: str, password_hash: str, role: str, department: Optional[str]) -> bool:
    row = {
        "username": username,
        "password_hash": password_hash,
        "role": role,
        "department": department,
    }
    if _pg():
        try:
            _sb().table("users").insert(row).execute()
            return True
        except Exception:
            return False
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute(
            "INSERT INTO users (username, password_hash, role, department) VALUES (?, ?, ?, ?)",
            (username, password_hash, role, department),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def create_session_row(token: str, username: str, expires_at: datetime) -> None:
    iso = expires_at.strftime("%Y-%m-%d %H:%M:%S")
    if _pg():
        _sb().table("sessions").insert({
            "token": token,
            "username": username,
            "expires_at": expires_at.astimezone(timezone.utc).isoformat() if expires_at.tzinfo else expires_at.replace(tzinfo=timezone.utc).isoformat(),
        }).execute()
        return
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO sessions (token, username, expires_at) VALUES (?, ?, ?)",
        (token, username, iso),
    )
    conn.commit()
    conn.close()


def get_session_with_user(token: str) -> Optional[dict]:
    if _pg():
        sess = _sb().table("sessions").select("*").eq("token", token).limit(1).execute()
        if not sess.data:
            return None
        row = sess.data[0]
        user = get_user(row["username"])
        if not user:
            return None
        return {
            "username": user["username"],
            "role": user["role"],
            "department": user.get("department"),
            "expires_at": row["expires_at"],
        }
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        SELECT u.username, u.role, u.department, s.expires_at
        FROM sessions s
        JOIN users u ON s.username = u.username
        WHERE s.token = ?
    ''', (token,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def delete_session_row(token: str) -> None:
    if _pg():
        _sb().table("sessions").delete().eq("token", token).execute()
        return
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM sessions WHERE token = ?", (token,))
    conn.commit()
    conn.close()


def delete_expired_sessions() -> None:
    if _pg():
        now = datetime.now(timezone.utc).isoformat()
        _sb().table("sessions").delete().lt("expires_at", now).execute()
        return
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM sessions WHERE expires_at < CURRENT_TIMESTAMP")
    conn.commit()
    conn.close()


# ── MTP records ──────────────────────────────────────────────────────────────

def save_mtp_record(report_date: str, department: str, content: str, status: str = "draft"):
    if _pg():
        _sb().table("mtp_records").upsert(
            {
                "report_date": report_date,
                "department": department,
                "content": content,
                "status": status,
                "submitted_at": datetime.now(timezone.utc).isoformat(),
            },
            on_conflict="report_date,department",
        ).execute()
        return True
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        INSERT INTO mtp_records (report_date, department, content, status, submitted_at)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(report_date, department)
        DO UPDATE SET content=excluded.content, status=excluded.status, submitted_at=CURRENT_TIMESTAMP
    ''', (report_date, department, content, status))
    conn.commit()
    conn.close()
    return True


def get_record(report_date: str, department: str):
    if _pg():
        result = (
            _sb().table("mtp_records")
            .select("*")
            .eq("report_date", report_date)
            .eq("department", department)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM mtp_records WHERE report_date = ? AND department = ?", (report_date, department))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def get_records_by_date(report_date: str):
    if _pg():
        result = _sb().table("mtp_records").select("*").eq("report_date", report_date).execute()
        return result.data or []
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM mtp_records WHERE report_date = ?", (report_date,))
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_records_by_dept(department: str):
    if _pg():
        result = (
            _sb().table("mtp_records")
            .select("*")
            .eq("department", department)
            .order("report_date", desc=True)
            .execute()
        )
        return result.data or []
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM mtp_records WHERE department = ? ORDER BY report_date DESC", (department,))
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def update_status(report_date: str, department: str, status: str):
    if _pg():
        result = (
            _sb().table("mtp_records")
            .update({"status": status})
            .eq("report_date", report_date)
            .eq("department", department)
            .execute()
        )
        return bool(result.data)
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "UPDATE mtp_records SET status = ? WHERE report_date = ? AND department = ?",
        (status, report_date, department),
    )
    conn.commit()
    affected = c.rowcount
    conn.close()
    return affected > 0


def get_record_by_id(record_id: int):
    if _pg():
        result = _sb().table("mtp_records").select("*").eq("id", record_id).limit(1).execute()
        return result.data[0] if result.data else None
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM mtp_records WHERE id = ?", (record_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def update_status_by_id(record_id: int, status: str):
    if _pg():
        result = (
            _sb().table("mtp_records")
            .update({"status": status})
            .eq("id", record_id)
            .execute()
        )
        return bool(result.data)
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE mtp_records SET status = ? WHERE id = ?", (status, record_id))
    conn.commit()
    affected = c.rowcount
    conn.close()
    return affected > 0


def get_all_dates():
    if _pg():
        result = (
            _sb().table("mtp_records")
            .select("report_date")
            .order("report_date", desc=True)
            .execute()
        )
        seen = []
        for row in result.data or []:
            d = _as_date_str(row.get("report_date"))
            if d and d not in seen:
                seen.append(d)
        return seen
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT DISTINCT report_date FROM mtp_records ORDER BY report_date DESC")
    rows = c.fetchall()
    conn.close()
    return [_as_date_str(row["report_date"]) for row in rows]


def delete_records_by_date(report_date: str):
    if _pg():
        _sb().table("mtp_records").delete().eq("report_date", report_date).execute()
        _sb().table("executive_summaries").delete().eq("report_date", report_date).execute()
        return True
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM mtp_records WHERE report_date = ?", (report_date,))
    c.execute("DELETE FROM executive_summaries WHERE report_date = ?", (report_date,))
    conn.commit()
    conn.close()
    return True


def save_executive_summary(report_date: str, content: str, status: str = "draft"):
    if _pg():
        _sb().table("executive_summaries").upsert(
            {
                "report_date": report_date,
                "content": content,
                "status": status,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            on_conflict="report_date",
        ).execute()
        return True
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        INSERT INTO executive_summaries (report_date, content, status, updated_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(report_date) DO UPDATE SET
            content=excluded.content,
            status=excluded.status,
            updated_at=CURRENT_TIMESTAMP
    ''', (report_date, content, status))
    conn.commit()
    conn.close()
    return True


def get_executive_summary(report_date: str):
    if _pg():
        result = (
            _sb().table("executive_summaries")
            .select("*")
            .eq("report_date", report_date)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM executive_summaries WHERE report_date = ?", (report_date,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None
