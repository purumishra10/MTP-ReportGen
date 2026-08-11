import sqlite3
import os
import json
from datetime import datetime

DATABASE_FILE = "backend/data/daily_data.db"

def get_connection():
    os.makedirs(os.path.dirname(DATABASE_FILE), exist_ok=True)
    conn = sqlite3.connect(DATABASE_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    c = conn.cursor()
    
    # Users table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            department TEXT
        )
    ''')
    
    # Sessions table
    c.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            FOREIGN KEY(username) REFERENCES users(username)
        )
    ''')
    
    # MTP Records (Department Submissions)
    c.execute('''
        CREATE TABLE IF NOT EXISTS mtp_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_date DATE NOT NULL,
            department TEXT NOT NULL,
            content TEXT,
            status TEXT DEFAULT 'draft', -- draft, pending_review, approved, rejected
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(report_date, department)
        )
    ''')
    
    # Executive Summaries (Principal)
    c.execute('''
        CREATE TABLE IF NOT EXISTS executive_summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_date DATE NOT NULL UNIQUE,
            content TEXT NOT NULL,
            status TEXT DEFAULT 'draft', -- draft, finalized
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

# --- Users & Sessions ---

def get_user(username: str):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username = ?", (username,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

# --- MTP Records (Department) ---

def save_mtp_record(report_date: str, department: str, content: str, status: str = 'draft'):
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
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM mtp_records WHERE report_date = ? AND department = ?", (report_date, department))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def get_records_by_date(report_date: str):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM mtp_records WHERE report_date = ?", (report_date,))
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]
    
def get_records_by_dept(department: str):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM mtp_records WHERE department = ? ORDER BY report_date DESC", (department,))
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def update_status(report_date: str, department: str, status: str):
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        UPDATE mtp_records 
        SET status = ? 
        WHERE report_date = ? AND department = ?
    ''', (status, report_date, department))
    conn.commit()
    affected = c.rowcount
    conn.close()
    return affected > 0

def get_record_by_id(record_id: int):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM mtp_records WHERE id = ?", (record_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def update_status_by_id(record_id: int, status: str):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE mtp_records SET status = ? WHERE id = ?", (status, record_id))
    conn.commit()
    affected = c.rowcount
    conn.close()
    return affected > 0

def get_all_dates():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT DISTINCT report_date FROM mtp_records ORDER BY report_date DESC")
    rows = c.fetchall()
    conn.close()
    return [row['report_date'] for row in rows]

def delete_records_by_date(report_date: str):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM mtp_records WHERE report_date = ?", (report_date,))
    c.execute("DELETE FROM executive_summaries WHERE report_date = ?", (report_date,))
    conn.commit()
    conn.close()
    return True

# --- Executive Summaries ---

def save_executive_summary(report_date: str, content: str, status: str = 'draft'):
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
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM executive_summaries WHERE report_date = ?", (report_date,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None
