import os
from docx import Document

def extract_images(doc_path):
    # Extracts all images from doc into a list of tuples: (image_bytes, ext)
    try:
        doc = Document(doc_path)
    except Exception:
        return []
        
    images = []
    for rel in doc.part.rels.values():
        if "image" in rel.target_ref:
            img_bytes = rel.target_part.blob
            ext = rel.target_ref.split('.')[-1]
            images.append((img_bytes, ext))
            
    return images
