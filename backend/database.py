import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'daily_data.db')

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mtp_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_date TEXT,
            department TEXT,
            placement_and_training TEXT,
            status TEXT DEFAULT 'draft',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS executive_summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_date TEXT UNIQUE,
            summary_text TEXT,
            status TEXT DEFAULT 'draft',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def save_mtp_record(report_date, department, placement_text, status='draft'):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('SELECT id FROM mtp_records WHERE report_date = ? AND department = ?', (report_date, department))
    exists = cursor.fetchone()
    
    if exists:
        cursor.execute('UPDATE mtp_records SET placement_and_training = ?, status = ? WHERE id = ?', (placement_text, status, exists[0]))
    else:
        cursor.execute('''
            INSERT INTO mtp_records (report_date, department, placement_and_training, status)
            VALUES (?, ?, ?, ?)
        ''', (report_date, department, placement_text, status))
        
    conn.commit()
    conn.close()

def get_daily_reports():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Also include reports that have an executive summary
    cursor.execute('''
        SELECT DISTINCT report_date FROM mtp_records 
        UNION 
        SELECT DISTINCT report_date FROM executive_summaries
        ORDER BY report_date DESC
    ''')
    results = [r[0] for r in cursor.fetchall()]
    conn.close()
    return results

def get_monthly_records():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT report_date, department, placement_and_training FROM mtp_records WHERE status = "approved" ORDER BY report_date ASC, department ASC')
    results = cursor.fetchall()
    conn.close()
    return results

def delete_record(report_date):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM mtp_records WHERE report_date = ?', (report_date,))
    cursor.execute('DELETE FROM executive_summaries WHERE report_date = ?', (report_date,))
    conn.commit()
    conn.close()

def get_records_by_date(report_date, require_approved=False):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if require_approved:
        cursor.execute('SELECT department, placement_and_training FROM mtp_records WHERE report_date = ? AND status = "approved"', (report_date,))
    else:
        cursor.execute('SELECT department, placement_and_training, status, id FROM mtp_records WHERE report_date = ?', (report_date,))
    results = cursor.fetchall()
    conn.close()
    return results

def update_status(record_id, status):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('UPDATE mtp_records SET status = ? WHERE id = ?', (status, record_id))
    conn.commit()
    conn.close()

# Executive Summary (Principal Actions)
def save_executive_summary(report_date, summary_text, status='draft'):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO executive_summaries (report_date, summary_text, status, updated_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(report_date) DO UPDATE SET 
            summary_text = excluded.summary_text,
            status = excluded.status,
            updated_at = excluded.updated_at
    ''', (report_date, summary_text, status))
    conn.commit()
    conn.close()

def get_executive_summary(report_date):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT summary_text, status FROM executive_summaries WHERE report_date = ?', (report_date,))
    result = cursor.fetchone()
    conn.close()
    return result

if __name__ == '__main__':
    init_db()
