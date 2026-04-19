import bcrypt
import uuid
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, Dict

from backend.database import get_connection

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except Exception:
        return False

def get_user(username: str) -> Optional[Dict]:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username = ?", (username,))
    row = c.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def seed_default_users():
    conn = get_connection()
    c = conn.cursor()
    
    # Check if users exist to avoid re-hashing
    c.execute("SELECT COUNT(*) as count FROM users")
    row = c.fetchone()
    if row and row['count'] > 0:
        conn.close()
        return

    users_to_seed = [
        # Departments
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
        
        # Staff Roles
        ("pa", "pa@vnr2026", "pa", None),
        ("principal", "principal@vnr2026", "principal", None),
        ("headoffice", "head@vnr2026", "head_office", None)
    ]
    
    print("[INFO] Seeding default users...")
    
    for username, password, role, dept in users_to_seed:
        hashed = hash_password(password)
        try:
            c.execute('''
                INSERT INTO users (username, password_hash, role, department)
                VALUES (?, ?, ?, ?)
            ''', (username, hashed, role, dept))
        except sqlite3.IntegrityError:
            pass # Ignore if already exists

    conn.commit()
    conn.close()
    print("[INFO] Done seeding default users.")

def create_session(username: str) -> str:
    """Create a new session token and store it."""
    token = str(uuid.uuid4())
    expires_at = datetime.now() + timedelta(days=7) # 7 days valid
    
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        INSERT INTO sessions (token, username, expires_at)
        VALUES (?, ?, ?)
    ''', (token, username, expires_at.strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()
    
    return token

def get_session_user(token: str) -> Optional[Dict]:
    """Retrieve user dictionary given a session token."""
    if not token:
        return None
        
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
    
    if not row:
        return None
        
    # Check expiration
    expires_at = datetime.strptime(row['expires_at'], '%Y-%m-%d %H:%M:%S')
    if datetime.now() > expires_at:
        delete_session(token)
        return None
        
    return dict(row)

def delete_session(token: str):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM sessions WHERE token = ?", (token,))
    conn.commit()
    conn.close()
    
def clean_expired_sessions():
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM sessions WHERE expires_at < CURRENT_TIMESTAMP")
    conn.commit()
    conn.close()
