"""Quick audit script to see what images are being extracted from source files."""
import os, sys
sys.path.insert(0, os.getcwd())
from backend.services.normalizer import extract_images

FOLDER = "backend/data/16th_March_2026"
for f in sorted(os.listdir(FOLDER)):
    if f.endswith(".docx") and not f.startswith("~"):
        path = os.path.join(FOLDER, f)
        with open(path, "rb") as fh:
            imgs = extract_images(fh.read(), f, f.split(".")[0].lower())
        if imgs:
            for img in imgs:
                size_kb = round(len(img["image_bytes"]) / 1024, 1)
                print(f"  {f} -> {img['filename']}  ({size_kb} KB)")
        else:
            print(f"  {f} -> (no images)")
