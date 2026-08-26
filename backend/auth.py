import bcrypt
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict

from backend.database import (
    get_user as db_get_user,
    count_users,
    insert_user,
    create_session_row,
    get_session_with_user,
    delete_session_row,
    delete_expired_sessions,
)


def _parse_expiry(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except ValueError:
        try:
            return datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def get_user(username: str) -> Optional[Dict]:
    return db_get_user(username)


def seed_default_users():
    if count_users() > 0:
        return

    users_to_seed = [
        ("cse", "cse@vnr2026", "department", "cse"),
        ("ece", "ece@vnr2026", "department", "ece"),
        ("eee", "eee@vnr2026", "department", "eee"),
        ("eie", "eie@vnr2026", "department", "eie"),
        ("it", "it@vnr2026", "department", "it"),
        ("me", "me@vnr2026", "department", "me"),
        ("mech", "mech@vnr2026", "department", "mech"),
        ("civil", "civil@vnr2026", "department", "civil"),
        ("chem", "chem@vnr2026", "department", "chem"),
        ("ae", "ae@vnr2026", "department", "ae"),
        ("mtp", "mtp@vnr2026", "department", "mtp"),
        ("english", "english@vnr2026", "department", "english"),
        ("eng", "eng@vnr2026", "department", "eng"),
        ("mms", "mms@vnr2026", "department", "m&ms"),
        ("library", "library@vnr2026", "department", "library"),
        ("aiml", "aiml@vnr2026", "department", "aiml"),
        ("cys", "cys@vnr2026", "department", "cys"),
        ("pa", "pa@vnr2026", "pa", None),
        ("principal", "principal@vnr2026", "principal", None),
        ("headoffice", "head@vnr2026", "head_office", None),
    ]

    print("[INFO] Seeding default users...")
    for username, password, role, dept in users_to_seed:
        insert_user(username, hash_password(password), role, dept)
    print("[INFO] Done seeding default users.")


def create_session(username: str) -> str:
    token = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    create_session_row(token, username, expires_at)
    return token


def get_session_user(token: str) -> Optional[Dict]:
    if not token:
        return None

    row = get_session_with_user(token)
    if not row:
        return None

    try:
        expires_at = _parse_expiry(row.get("expires_at"))
        if expires_at is not None:
            now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
            now_local = datetime.now()
            # Delete only if both UTC and local clock are well past expiration
            if now_utc > (expires_at + timedelta(hours=2)) and now_local > (expires_at + timedelta(hours=2)):
                delete_session(token)
                return None
    except Exception as e:
        print(f"[AUTH] Expiry parse warning: {e}")

    return {
        "username": row["username"],
        "role": row["role"],
        "department": row.get("department"),
    }


def delete_session(token: str):
    delete_session_row(token)


def clean_expired_sessions():
    delete_expired_sessions()
