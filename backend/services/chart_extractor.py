import os
import time

def extract_charts_from_docx(doc_path: str, output_dir: str) -> list[str]:
    """
    Extract embedded charts from a DOCX file as PNG images using win32com.
    Returns a list of paths to the extracted images.
    Returns empty list if win32com is unavailable or extraction fails.
    """
    try:
        import win32com.client
        from PIL import ImageGrab
    except ImportError:
        return []

    if not os.path.exists(doc_path):
        return []

    word = None
    doc = None
    extracted_paths = []
    
    try:
        # Initialize Word invisibly
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = False
        
        doc = word.Documents.Open(os.path.abspath(doc_path), ReadOnly=True)
        
        for i, shape in enumerate(doc.InlineShapes):
            if shape.HasChart:
                shape.Select()
                word.Selection.CopyAsPicture()
                time.sleep(0.5) # Wait for clipboard
                img = ImageGrab.grabclipboard()
                
                if img:
                    out_path = os.path.abspath(os.path.join(output_dir, f"chart_{os.path.basename(doc_path)}_{i}.png"))
                    img.save(out_path, "PNG")
                    extracted_paths.append(out_path)
                    
    except Exception as e:
        print(f"Chart extraction error: {e}")
    finally:
        if doc:
            doc.Close(False)
        if word:
            word.Quit()
            
    return extracted_paths
