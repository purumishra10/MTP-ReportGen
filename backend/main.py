import os
from typing import List, Optional, Dict
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, File, Form, UploadFile, HTTPException, Depends, Request, Response
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Initialize DB and Users
from backend.database import (
    init_db, save_mtp_record, get_records_by_date, get_records_by_dept, 
    update_status, get_all_dates, delete_records_by_date, 
    save_executive_summary, get_executive_summary, get_record
)
from backend.auth import (
    seed_default_users, verify_password, create_session, 
    get_session_user, delete_session, get_user
)

# Services
from backend.services.ai_service import consolidate
from backend.services.report_generator import generate_docx
from backend.services import supabase_client
from backend.services.portal_report_service import generate_from_portal

# Setup application
app = FastAPI(title="MTP Daily Report API & Portal")

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Startup ---
@app.on_event("startup")
def startup_event():
    print("[INFO] Initializing SQLite database...")
    init_db()
    seed_default_users()
    os.makedirs("generated_reports", exist_ok=True)
    
# --- Dependencies ---
def get_current_user(request: Request):
    token = request.cookies.get("session_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = get_session_user(token)
    if not user:
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    return user

def require_role(allowed_roles: List[str]):
    def role_checker(user: dict = Depends(get_current_user)):
        if user["role"] not in allowed_roles:
            raise HTTPException(status_code=403, detail="Forbidden")
        return user
    return role_checker

# --- API Models ---
class LoginRequest(BaseModel):
    username: str
    password: str

class DeptSubmitRequest(BaseModel):
    date: str
    content: str
    status: str

class ReviewRequest(BaseModel):
    date: str
    department: str
    status: str

class SummaryRequest(BaseModel):
    date: str
    content: str
    status: str

# --- Authentication Endpoints ---

@app.post("/api/login")
def login(req: LoginRequest, response: Response):
    user = get_user(req.username)
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")
        
    token = create_session(req.username)
    
    # Set cookie (HttpOnly for security)
    response.set_cookie(
        key="session_token", 
        value=token, 
        httponly=False,  # Set to False so client JS can see if logged in easily, though HttpOnly is better for prod. We will use frontend JS to redirect based on 'role'.
        max_age=7*24*3600
    )
    
    return {"message": "Logged in successfully", "role": user["role"], "department": user["department"]}

@app.post("/api/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get("session_token")
    if token:
        delete_session(token)
    response.delete_cookie("session_token")
    return {"message": "Logged out"}

@app.get("/api/me")
def me(user: dict = Depends(get_current_user)):
    return {"username": user["username"], "role": user["role"], "department": user["department"]}


# --- Department Endpoints ---

@app.get("/api/department/submissions")
def get_dept_submissions(user: dict = Depends(require_role(["department"]))):
    records = get_records_by_dept(user["department"])
    return {"records": records}
    
@app.get("/api/department/submission/{date}")
def get_dept_submission_by_date(date: str, user: dict = Depends(require_role(["department"]))):
    record = get_record(date, user["department"])
    if not record:
        return {"content": "", "status": "draft"}
    return record

@app.post("/api/department/submit")
def submit_dept_report(req: DeptSubmitRequest, user: dict = Depends(require_role(["department"]))):
    if req.status not in ["draft", "pending_review"]:
        raise HTTPException(status_code=400, detail="Invalid status")
    
    save_mtp_record(req.date, user["department"], req.content, req.status)
    return {"message": "Saved successfully"}


# --- PA Office Endpoints ---

@app.get("/api/tracker/{date}")
def get_tracker(date: str, user: dict = Depends(require_role(["pa", "principal"]))):
    records = get_records_by_date(date)
    return {"records": records}

@app.post("/api/tracker/review")
def review_submission(req: ReviewRequest, user: dict = Depends(require_role(["pa"]))):
    if req.status not in ["approved", "rejected", "pending_review"]:
        raise HTTPException(status_code=400, detail="Invalid status")
        
    success = update_status(req.date, req.department, req.status)
    if not success:
        raise HTTPException(status_code=404, detail="Record not found")
    return {"message": f"Status updated to {req.status}"}

@app.get("/api/history")
def get_history(user: dict = Depends(require_role(["pa", "principal", "head_office"]))):
    dates = get_all_dates()
    
    # Enrich with Supabase reports if enabled?
    # For now just return local dates.
    return {"dates": dates}

@app.delete("/api/history/{date}")
def clear_date(date: str, user: dict = Depends(require_role(["pa"]))):
    delete_records_by_date(date)
    return {"message": f"Deleted records for {date}"}

@app.post("/api/generate")
def api_generate_portal_report(req: dict, user: dict = Depends(require_role(["pa"]))):
    date_str = req.get("date")
    if not date_str:
        raise HTTPException(status_code=400, detail="Date required")
        
    try:
        docx_bytes = generate_from_portal(date_str)
        if not docx_bytes:
            raise HTTPException(status_code=500, detail="Failed to generate report")
            
        output_dir = "generated_reports"
        output_path = os.path.join(output_dir, f"daily_report_{date_str}.docx")
        with open(output_path, "wb") as f:
            f.write(docx_bytes)
            
        return {"message": "Generated successfully", "download_url": f"/reports/download/daily_report_{date_str}.docx"}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/monthly")
def generate_monthly(req: dict, user: dict = Depends(require_role(["pa"]))):
    return JSONResponse(status_code=501, content={"message": "Monthly generation via AI from portal is not yet implemented."})


# --- Principal Endpoints ---

@app.get("/api/principal/summary/{date}")
def get_summary(date: str, user: dict = Depends(require_role(["principal", "pa"]))):
    record = get_executive_summary(date)
    return {"record": record}

@app.post("/api/principal/summary")
def save_summary(req: SummaryRequest, user: dict = Depends(require_role(["principal"]))):
    if req.status not in ["draft", "finalized"]:
        raise HTTPException(status_code=400, detail="Invalid status")
        
    save_executive_summary(req.date, req.content, req.status)
    return {"message": "Saved successfully"}


# --- Original Main Branch Endpoints (Supabase/File Upload) ---

@app.post("/consolidate")
async def api_consolidate_files(
    report_date: str = Form(...),
    files: List[UploadFile] = File(...),
):
    """File upload endpoint — uses hybrid pipeline (deterministic + LLM)."""
    if not report_date:
        raise HTTPException(status_code=400, detail="report_date is required")

    print(f"\n[INFO] Starting consolidation for date: {report_date}")
    print(f"[INFO] Received {len(files)} files")
    print(f"[INFO] Pipeline: Deterministic extraction + LLM narrative summarization")

    from backend.services.structured_extractor import extract_structured_data
    from backend.batch_processor import get_dept_code, LIBRARY_DEPT_CODES, _dept_name_from_code

    dept_data = []

    # Parse each file using structured extractor
    for file in files:
        file_bytes = await file.read()
        filename = file.filename
        print(f"  -> Processing file: {filename}")

        dept_code = get_dept_code(filename)
        if dept_code == "unknown":
            dept_code = os.path.splitext(filename)[0].lower()[:10]

        is_library = dept_code in LIBRARY_DEPT_CODES
        dept_name = _dept_name_from_code(dept_code)

        try:
            data = extract_structured_data(file_bytes, dept_code, dept_name, is_library=is_library)
            
            # If it's the attendance report, extract its charts using win32com
            if "attendance" in filename.lower():
                temp_path = os.path.join("scratch", f"temp_{filename}")
                os.makedirs("scratch", exist_ok=True)
                with open(temp_path, "wb") as f:
                    f.write(file_bytes)
                from backend.services.chart_extractor import extract_charts_from_docx
                print("     [INFO] Extracting charts from attendance report...")
                charts = extract_charts_from_docx(temp_path, "scratch")
                data["attendance_charts"] = charts
                print(f"     [OK] Extracted {len(charts)} charts")

            dept_data.append(data)
            
            att = data.get("attendance") or data.get("library_attendance")
            att_str = f"on_rolls={att['on_rolls']}" if att else "no-attendance"
            print(f"     [OK] Extracted: {att_str}")
        except Exception as e:
            print(f"     [ERROR] Failed to process {filename}: {e}")

    # Hybrid consolidation (deterministic merge + LLM narrative)
    try:
        print("[INFO] Running hybrid consolidation...")
        consolidated = consolidate(report_date, dept_data)

        output_dir = "generated_reports"
        os.makedirs(output_dir, exist_ok=True)
        filename_out = f"daily_report_{report_date}.docx"
        output_path = os.path.join(output_dir, filename_out)

        print("[INFO] Generating final DOCX report...")
        docx_bytes = generate_docx(consolidated, output_path=output_path, all_images=[])
        print(f"[SUCCESS] Report saved to: {output_path}")

        # Supabase upload
        if supabase_client.is_enabled():
            try:
                dept_codes = [d["dept_code"] for d in dept_data]
                saved_record = supabase_client.save_report(
                    report_date=report_date,
                    departments=dept_codes,
                    docx_bytes=docx_bytes,
                    filename=filename_out
                )
                print("[INFO] Successfully uploaded to Supabase.")
            except Exception as e:
                print(f"[WARNING] Supabase upload failed: {e}")

        # Provide a URL relative path
        filename_encoded = filename_out.replace(" ", "%20")
        download_url = f"/reports/download/{filename_encoded}"
        
        return {
            "status": "success",
            "message": "Report consolidated and generated successfully.",
            "report_date": report_date,
            "download_url": download_url
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Consolidation failed: {str(e)}")



@app.get("/reports")
def list_reports():
    """List all reports from Supabase if enabled, else return empty."""
    if not supabase_client.is_enabled():
        return {"status": "success", "reports": [], "message": "Supabase not enabled."}
    
    reports = supabase_client.list_reports(limit=50)
    return {"status": "success", "reports": reports}


@app.get("/reports/{report_id}")
def get_report(report_id: str):
    """Get report details from Supabase."""
    if not supabase_client.is_enabled():
        raise HTTPException(status_code=501, detail="Supabase not enabled")
        
    report = supabase_client.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
        
    return {"status": "success", "report": report}

@app.get("/reports/download/{filename}")
def download_local_report(filename: str):
    """Download a generated report from local folder generated_reports."""
    filepath = os.path.join("generated_reports", filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")
        
    return FileResponse(
        path=filepath, 
        filename=filename, 
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

@app.get("/reports/supabase/download")
def download_supabase_report(file_path: str):
    """Download a report directly from Supabase storage."""
    if not supabase_client.is_enabled():
        raise HTTPException(status_code=501, detail="Supabase not enabled")
        
    data = supabase_client.get_report_file(file_path)
    if not data:
        raise HTTPException(status_code=404, detail="File not found or download failed")
        
    filename = os.path.basename(file_path)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

# --- Format Schema Endpoint ---

@app.get("/api/formats/{dept_code}")
def get_format_schema(dept_code: str):
    """Return the JSON format schema for a department so the frontend can build table forms."""
    import json as json_module
    formats_dir = os.path.join(os.path.dirname(__file__), "formats", "json")
    
    # Try exact match first, then partial match
    matched_file = None
    for fname in os.listdir(formats_dir):
        if not fname.endswith(".json"):
            continue
        name_lower = fname.lower().replace(".json", "")
        code_lower = dept_code.lower().replace(" ", "_").replace("-", "_").replace("&", "_")
        if code_lower in name_lower or name_lower.startswith(code_lower):
            matched_file = os.path.join(formats_dir, fname)
            break
    
    if not matched_file:
        # Fallback: return CSE format as default
        fallback = os.path.join(formats_dir, "Civil_CSE_CSE__CyS__DS__and_AI_DS_ECE_IT_DEPT__format_for_CSE____CyS__DS__and_AI_DS.json")
        if os.path.exists(fallback):
            matched_file = fallback
        else:
            raise HTTPException(status_code=404, detail=f"Format not found for department: {dept_code}")
    
    with open(matched_file, "r", encoding="utf-8") as f:
        schema = json_module.load(f)
    
    return schema


# --- Static Frontend Serving ---

# Mount the static frontend directory. Order is important, this should be last.
if os.path.exists("frontend"):
    app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
else:
    print("[WARNING] 'frontend' directory not found. Static files will not be served.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
