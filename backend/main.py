from dotenv import load_dotenv
load_dotenv()

import os
from datetime import date
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from typing import Annotated

from backend.services.normalizer import normalize, truncate, extract_images
from backend.services.ai_service import consolidate, verify_facts
from backend.services.post_processor import post_process
from backend.services.report_generator import generate_docx
from backend.services import supabase_client

app = FastAPI(
    title="VNRVJIET Daily Report Consolidation",
    description="Upload department reports and get a consolidated daily report in DOCX format.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

ALLOWED_EXTENSIONS = {".pdf", ".docx"}
LIBRARY_DEPT_CODES = {"library", "lib", "lirc"}


# ── Department code → name mapping ───────────────────────────────────────────

DEPT_MAPPING = {
    "cse":       "Computer Science & Engineering",
    "cys":       "Cyber Security, Data Science & AIDS",
    "aiml":      "Artificial Intelligence & Machine Learning, and IoT",
    "it":        "Information Technology",
    "ece":       "Electronics & Communication Engineering",
    "eee":       "Electrical & Electronics Engineering",
    "eie":       "Electronics & Instrumentation Engineering",
    "me":        "Mechanical Engineering",
    "mech":      "Mechanical Engineering",
    "civil":     "Civil Engineering",
    "chem":      "Chemical Engineering",
    "ae":        "Automobile Engineering",
    "mtp":       "Mentorship, Training & Placements",
    "english":   "English Department",
    "eng":       "English Department",
    "m&ms":      "Management & Mathematical Sciences",
    "ms":        "Management & Mathematical Sciences",
    "library":   "Library & Information Resource Centre",
    "lib":       "Library & Information Resource Centre",
    "lirc":      "Library & Information Resource Centre",
}


def _dept_name_from_code(code: str) -> str:
    return DEPT_MAPPING.get(code, code.upper())


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status": "ok",
        "supabase": supabase_client.is_enabled(),
    }


# ── Main consolidation endpoint ──────────────────────────────────────────────

@app.post("/consolidate")
async def consolidate_reports(
    report_date: Annotated[str, Form(description="Date in YYYY-MM-DD format")],
    files: Annotated[
        list[UploadFile],
        File(description="Upload all department report files (.docx or .pdf). Name each file as dept_code.docx")
    ],
):
    """
    Upload department reports and get a consolidated daily report.

    Example:
        curl -X POST http://localhost:8000/consolidate \\
          -F "report_date=2026-03-16" \\
          -F "files=@reports/cse.docx" \\
          -F "files=@reports/ece.docx"
    """
    # Validate inputs
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")

    try:
        date.fromisoformat(report_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="report_date must be in YYYY-MM-DD format.")

    # Read, validate, and normalize files
    dept_reports = []
    all_images = []
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
            text = truncate(text, max_chars=15000)
        except Exception as e:
            errors.append(f"{filename}: failed to extract text — {e}")
            continue

        if text == "[No content extracted]":
            errors.append(f"{filename}: no readable content found in file")
            continue

        # Extract images from DOCX files
        try:
            images = extract_images(file_bytes, filename, dept_code)
            all_images.extend(images)
        except Exception as e:
            print(f"[WARNING] Image extraction failed for {filename}: {e}")

        dept_reports.append({
            "dept_code": dept_code,
            "dept_name": dept_name,
            "text": text,
        })

    if not dept_reports:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "No files could be processed successfully.",
                "file_errors": errors,
            },
        )

    # Deduplicate template images: any image hash appearing in 3+ files is a logo/template
    if all_images:
        import hashlib
        from collections import Counter
        hash_counts = Counter()
        for img in all_images:
            img["_hash"] = hashlib.md5(img["image_bytes"]).hexdigest()
            hash_counts[img["_hash"]] += 1
        template_hashes = {h for h, c in hash_counts.items() if c >= 3}
        before = len(all_images)
        all_images = [img for img in all_images if img["_hash"] not in template_hashes]
        filtered = before - len(all_images)
        if filtered:
            print(f"[INFO] Filtered {filtered} template/logo images (hash dedup)")


    # AI consolidation
    try:
        consolidated = consolidate(report_date, dept_reports)
    except ValueError as e:
        raise HTTPException(
            status_code=502,
            detail={"message": "AI consolidation failed (invalid JSON response)", "error": str(e)},
        )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail={"message": "Unexpected error during AI consolidation", "error": str(e)},
        )

    # Fact verification (non-blocking — failures don't stop report generation)
    try:
        issues = verify_facts(consolidated, dept_reports)
    except Exception:
        issues = []
        consolidated["_fact_issues"] = []

    # Post-process: deduplicate, normalize, clean
    consolidated = post_process(consolidated)

    # Generate DOCX
    try:
        output_dir = "generated_reports"
        os.makedirs(output_dir, exist_ok=True)
        from datetime import datetime as _dt
        _ts = _dt.now().strftime("%H%M%S")
        filename = f"daily_report_{report_date}_{_ts}.docx"
        output_path = os.path.join(output_dir, filename)
        docx_bytes = generate_docx(consolidated, output_path=output_path,
                                    all_images=all_images)
        print(f"[SUCCESS] DOCX generated at: {output_path}")
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"message": "Report generation failed", "error": str(e)},
        )

    # Save to Supabase (non-blocking)
    supabase_record = None
    if supabase_client.is_enabled():
        try:
            dept_codes = [r["dept_code"] for r in dept_reports]
            supabase_record = supabase_client.save_report(
                report_date=report_date,
                departments=dept_codes,
                docx_bytes=docx_bytes,
                filename=filename,
                metadata={"fact_issues": issues, "file_errors": errors},
            )
        except Exception as e:
            print(f"[WARNING] Supabase save failed: {e}")

    # Return the DOCX file directly
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


# ── Report history endpoints (Supabase) ──────────────────────────────────────

@app.get("/reports")
def list_reports():
    """List all previously generated reports."""
    if not supabase_client.is_enabled():
        return {"message": "Supabase not configured. Reports are saved locally in generated_reports/ folder."}
    return supabase_client.list_reports()


@app.get("/reports/{report_id}")
def get_report(report_id: str):
    """Get details of a specific report."""
    if not supabase_client.is_enabled():
        raise HTTPException(status_code=503, detail="Supabase not configured.")

    record = supabase_client.get_report(report_id)
    if not record:
        raise HTTPException(status_code=404, detail="Report not found.")
    return record


@app.get("/reports/{report_id}/download")
def download_report(report_id: str):
    """Download a previously generated report file."""
    if not supabase_client.is_enabled():
        raise HTTPException(status_code=503, detail="Supabase not configured.")

    record = supabase_client.get_report(report_id)
    if not record:
        raise HTTPException(status_code=404, detail="Report not found.")

    file_bytes = supabase_client.get_report_file(record["file_path"])
    if not file_bytes:
        raise HTTPException(status_code=404, detail="Report file not found in storage.")

    return Response(
        content=file_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f'attachment; filename="daily_report_{record["report_date"]}.docx"',
        },
    )
