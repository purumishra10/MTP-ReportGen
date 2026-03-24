import re

def parse_remarks(remarks_text, dept_name):
    lines = remarks_text.split('\n')
    current_leave_type = "Absent"
    absent_list = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # If it looks like a leave type heading (e.g., "Faculty - Casual / Earn Leave", "Full Day")
        # We can try to capture keywords
        lower_line = line.lower()
        if any(keyword in lower_line for keyword in ['leave', 'duty', 'vacation', 'full day', 'half day', 'lwp', 'ml/pl', 'maternity', 'paternity']):
            if not line.startswith(('1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.', '0 ')): # not a name entry
                current_leave_type = line.replace('', '-').strip()
                continue
                
        # If it starts with a number, or just looks like a name
        # E.g. "1.B.Raswitha"
        match = re.match(r'^(\d+\.)?\s*(.*)', line)
        if match:
            name = match.group(2).strip()
            # filter out placeholders
            if name.lower() in ['name of the staff', 'name of the staff (ml/pl)', '0']:
                continue
            if name:
                absent_list.append(f"{name} ({dept_name}) — {current_leave_type}")
                
    return absent_list

remarks = """
Faculty  On Duty
Faculty  Casual / Earn Leave 
Full Day
1.B.Raswitha
2.Dr. D.Dakshyani
       Himabindu(LWP)
.Half Day

                       Faculty  Half Pay Leave
Faculty - Study Leave
Faculty Maternity/Paternity Leave
"""

print(parse_remarks(remarks, "IT"))
