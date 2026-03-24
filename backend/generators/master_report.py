import os
import io
from docx import Document
from docx.shared import Inches

def generate_master_report(template_path, output_path, attendance_data, mtp_data, image_data, missing_depts, library_data):
    doc = Document(template_path)

    try:
        table_2 = doc.tables[2]
        att_cell = table_2.rows[0].cells[1]
        att_cell.text = "Staff & Student Attendance Report : Attached.\n\nConsolidated Absent Faculty:\n"
        
        if not attendance_data and not missing_depts:
            att_cell.text += "Data Not Received\n"
        else:
            for entry in attendance_data:
                att_cell.text += f"- {entry}\n"
            
        if missing_depts:
            att_cell.text += "\nMissing Reports From:\n"
            for dept in missing_depts:
                att_cell.text += f"- {dept} Data Not Received\n"

        mtp_cell = table_2.rows[1].cells[1]
        mtp_cell.text = "MTP:\n\n"
        
        if not mtp_data and not missing_depts:
            mtp_cell.text += "Data Not Received\n"
        else:
            for text in mtp_data:
                if text:
                    mtp_cell.add_paragraph(text)

        for img_bytes, ext in image_data:
            try:
                p = mtp_cell.add_paragraph()
                p.alignment = 1 
                r = p.add_run()
                img_stream = io.BytesIO(img_bytes)
                r.add_picture(img_stream, width=Inches(4.5))
            except Exception as e:
                print(f"Failed to insert image - {e}")
                
        # Library data
        if library_data and len(doc.tables) > 3:
            table_3 = doc.tables[3]
            try:
                if len(table_3.rows) > 1:
                    table_3.rows[1].cells[2].text = str(library_data.get("books_issued", ""))
                if len(table_3.rows) > 2:
                    table_3.rows[2].cells[2].text = str(library_data.get("books_returned", ""))
                if len(table_3.rows) > 3:
                    table_3.rows[3].cells[2].text = str(library_data.get("visits", ""))
            except Exception as e:
                print(f"Error populating library table: {e}")
                
    except Exception as e:
        print(f"Error populating document: {e}")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    doc.save(output_path)
