import requests
import os

URL = "http://127.0.0.1:8000/consolidate"
FOLDER = "data/16th_March_2026"

files = []

for filename in os.listdir(FOLDER):
    if filename.endswith(".docx"):
        path = os.path.join(FOLDER, filename)
        files.append(("files", (filename, open(path, "rb"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")))

print(f"Uploading {len(files)} files...")

response = requests.post(URL, files=files)

print("\nSTATUS:", response.status_code)
print("\nRESPONSE:\n")
print(response.text)