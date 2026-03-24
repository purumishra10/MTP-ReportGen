import re
from docx import Document

def extract_attendance(doc_path, dept_name):
    try:
        doc = Document(doc_path)
    except Exception:
        return []
        
    absent_list = []
    
    for table in doc.tables:
        if not table.rows:
            continue
            
        header = [cell.text.strip().lower() for cell in table.rows[0].cells]
        if 'absent' in header:
            # Found attendance table
            # Find index of remarks column
            remarks_idx = -1
            for i, h in enumerate(header):
                if 'remark' in h or 'detail' in h:
                    remarks_idx = i
                    break
            
            if remarks_idx == -1:
                remarks_idx = len(header) - 1 # Fallback to last column
            
            # Iterate rows
            for row in table.rows[1:]:
                if len(row.cells) > remarks_idx:
                    remarks_text = row.cells[remarks_idx].text
                    
                    # Parse remarks
                    lines = remarks_text.split('\n')
                    current_leave_type = "Absent"
                    
                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue
                            
                        # If it looks like a leave type heading
                        lower_line = line.lower()
                        if any(kw in lower_line for kw in ['leave', 'duty', 'vacation', 'full day', 'half day', 'lwp', 'ml/pl', 'maternity']):
                            if not re.match(r'^(\d+\.)', line):
                                current_leave_type = line.replace('', '').strip()
                                continue
                                
                        match = re.match(r'^(\d+\.)?\s*(.*)', line)
                        if match:
                            name = match.group(2).strip()
                            if name.lower() in ['name of the staff', 'name of the staff (ml/pl)', '0', '']:
                                continue
                            if name:
                                absent_list.append(f"{name} ({dept_name}) — {current_leave_type}")
    
    return absent_list
