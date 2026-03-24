from docx import Document

def extract_mtp(doc_path):
    try:
        doc = Document(doc_path)
    except Exception:
        return []

    mtp_texts = []
    capture = False
    
    for p in doc.paragraphs:
        text = p.text.strip()
        lower_text = text.lower()
        
        # MTP sections typically found at the bottom
        if not capture and ("any other matter" in lower_text or "placement" in lower_text):
            capture = True
            mtp_texts.append(text)
            continue
            
        if capture:
            if text:
                mtp_texts.append(text)
                
    return mtp_texts
