"""
Test script: uploads all department .docx files to the consolidation API
and saves the resulting DOCX report locally.
"""

import requests
import os
import sys
from datetime import date

URL = "http://127.0.0.1:8000/consolidate"
FOLDER = os.path.join(os.path.dirname(__file__), "data", "16th_March_2026")
REPORT_DATE = "2026-03-16"

def main():
    if not os.path.isdir(FOLDER):
        print(f"ERROR: Data folder not found: {FOLDER}")
        sys.exit(1)

    files = []
    for filename in sorted(os.listdir(FOLDER)):
        if filename.endswith((".docx", ".pdf")):
            path = os.path.join(FOLDER, filename)
            mime = (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                if filename.endswith(".docx")
                else "application/pdf"
            )
            files.append(("files", (filename, open(path, "rb"), mime)))

    if not files:
        print("ERROR: No .docx or .pdf files found in", FOLDER)
        sys.exit(1)

    print(f"Uploading {len(files)} files for date {REPORT_DATE}...")
    print(f"Files: {[f[1][0] for f in files]}")
    print()

    try:
        response = requests.post(
            URL,
            data={"report_date": REPORT_DATE},
            files=files,
            timeout=300,  # 5 min timeout for AI processing
        )
    except requests.ConnectionError:
        print("ERROR: Could not connect to server. Make sure it's running:")
        print("  uvicorn backend.main:app --reload")
        sys.exit(1)

    print(f"STATUS: {response.status_code}")

    if response.status_code == 200:
        # Save the DOCX file
        output_path = f"daily_report_{REPORT_DATE}.docx"
        with open(output_path, "wb") as f:
            f.write(response.content)
        print(f"SUCCESS! Report saved to: {output_path}")
        print(f"File size: {len(response.content):,} bytes")
    else:
        print(f"FAILED!")
        try:
            print(f"Response: {response.json()}")
        except Exception:
            print(f"Response: {response.text[:500]}")

    # Close file handles
    for _, (_, fh, _) in files:
        fh.close()


if __name__ == "__main__":
    main()