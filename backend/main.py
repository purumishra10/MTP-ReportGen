from dotenv import load_dotenv
load_dotenv()

import os
from datetime import date
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import Annotated
 
from backend.services.normalizer import normalize, truncate
from backend.services.ai_service import consolidate, verify_facts
from backend.services.report_generator import generate_pdf

app = FastAPI(title = "VNRVJIET Report Consolidation - Prototype")

app.add_middleware(
    CORSMiddleware,
    allow_origins = ["*"],
    allow_methods = ["*"],
    allow_headers = ["*"]
)

ALLOWED_EXTENSIONS = {".pdf", ".docx"}
LIBRARY_DEPT_CODES = {"library", "lib", "lirc"}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/consolidate")
async def consolidate_reports(
    report_date: Annotated[str, Form(description="Date in YYYY-MM-DD format")],
    files: Annotated[
        list[UploadFile],
        File(description="Upload all department report files. Name each file as dept_code.docx or dept_code.pdf")
    ],
):
    """
        Example curl:
            curl -X POST http://localhost:8000/consolidate \\
            -F "report_date=2025-01-15" \\
            -F "files=@reports/cse.docx" \\
            -F "files=@reports/ece.docx" \\
            -F "files=@reports/library.docx"
    """

    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")
    
    try:
        date.fromisoformat(report_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="report_date must be in YYYY-MM-DD format.")
    
    # read validate and normalize files
    dept_reports = []
    errors = []

    for upload in files:
        filename = upload.filename or "unknown"
        stem, ext = os.path.splitext(filename)
        ext = ext.lower()

        if ext not in ALLOWED_EXTENSIONS:
            errors.append(f"{filename}: unsupported file type (only .docx and .pdf allowed)")
            continue

        try:
            file_bytes = await upload.read()
        except Exception as e:
            errors.append(f"{filename}: failed to read file - {e}")
            continue

        if not file_bytes:
            errors.append(f"{filename}: file is empty")
            continue

        dept_code = stem.lower().strip()
        is_library = dept_code in LIBRARY_DEPT_CODES

        dept_name = _dept_name_from_code(dept_code)

        try:
            text = normalize(file_bytes, filename, is_library=is_library)
            text = truncate(text, max_chars=5000)
        except Exception as e:
            errors.append(f"{filename}: failed to extract text — {e}")
            continue

        if text == "{No content extracted}":
            errors.append(f"{filename}: no readable content found in file")
            continue

        dept_reports.append({
            "dept_code": dept_code,
            "dept_name": dept_name,
            "text": text,
        })

    if not dept_reports:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "No files could be processed.",
                "file_errors": errors,
            },
        )
    

    try:
        consolidated = consolidate(report_date, dept_reports)
    except ValueError as e:
        raise HTTPException(
            status_code=502,
            detail={"message": "AI consolidation failed", "error": str(e)},
        )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail={"message": "Unexpected error during AI consolidation", "error": str(e)},
        )
    
    
    try:
        issues = verify_facts(consolidated, dept_reports)
    except Exception:
        issues = []
        consolidated["_fact_issues"]= []
    
    
    try:
        output_dir = "generated_reports"
        os.makedirs(output_dir, exist_ok=True)
        filename = f"daily_report_{report_date}.pdf"
        output_path= os.path.join(output_dir, filename)
        generate_pdf(consolidated, output_path=output_path)
        print(f"[SUCCESS] PDF generated at: {output_path}")
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"message": "PDF generation failed", "error":str(e)},
        )
    return {
        "success": True,
        "message": "PDF report generated successfully",
        "file": output_path
    }

def _dept_name_from_code(code: str) -> str:
    """
    Map short dept codes to full names.
    Add your institution's actual department codes here.
    """
    mapping = {
        "cse":     "Computer Science & Engineering",
        "cys":     "Cyber Security, Data science, and AIDS",
        "aiml":    "AIML, and IOT",
        "it":      "Information Technology",
        "ece":     "Electronics & Communication Engineering",
        "eee":     "Electrical & Electronics Engineering",
        "eie":     "Electrical & Instrumentation Engineering",
        "mech":    "Mechanical Engineering",
        "me":      "Mechanical Engineering",
        "civil":   "Civil Engineering",
        "chem":    "Chemical Engineering",
        "ae":      "Automobile Engineering",
        "chem":    "Chemistry Department",
        "chemistry":"Chemistry Department",
        "chemical":"Chemistry Department",
        "mtp":     "Mentorship, Training and Placements",
        "eng":     "English Department",
        "english": "English Department",
        "m&ms":    "Management & Mathematical Sciences",
        "ms":    "Management & Mathematical Sciences",
        "library": "Library & Information Resource Centre",
        "lib":     "Library & Information Resource Centre",
        "lirc":    "Library & Information Resource Centre",
    }
    return mapping.get(code, code.upper())
