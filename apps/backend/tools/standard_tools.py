"""
AILIZA Standard Tools
DSGVO Art. 5: Datensparsamkeit | EU AI Act Art. 14: Risikoklassen
"""
from __future__ import annotations
import json, logging, os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

def get_standard_tools():
    return {
        "get_current_time": {"func": tool_get_time, "requires_approval": False, "risk_level": "minimal", "schema": {"description": "Gibt die aktuelle Uhrzeit zurueck.", "parameters": {"type": "object", "properties": {"timezone": {"type": "string", "description": "Zeitzone z.B. Europe/Berlin"}}, "required": []}}},
        "read_file": {"func": tool_read_file, "requires_approval": False, "risk_level": "low", "schema": {"description": "Liest den Inhalt einer Datei.", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Dateipfad"}, "encoding": {"type": "string", "description": "Kodierung Standard utf-8"}}, "required": ["path"]}}},
        "write_file": {"func": tool_write_file, "requires_approval": True, "risk_level": "medium", "schema": {"description": "Schreibt in eine Datei. Erfordert Genehmigung.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}, "mode": {"type": "string", "enum": ["write","append"]}}, "required": ["path","content"]}}},
        "list_directory": {"func": tool_list_directory, "requires_approval": False, "risk_level": "minimal", "schema": {"description": "Listet Verzeichnisinhalt auf.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "show_hidden": {"type": "boolean"}}, "required": ["path"]}}},
        "calculate": {"func": tool_calculate, "requires_approval": False, "risk_level": "minimal", "schema": {"description": "Fuehrt mathematische Berechnungen durch.", "parameters": {"type": "object", "properties": {"expression": {"type": "string", "description": "Mathematischer Ausdruck z.B. 2+2"}}, "required": ["expression"]}}},
        "read_pdf": {"func": tool_read_pdf, "requires_approval": False, "risk_level": "low", "schema": {"description": "Liest Text aus einer PDF-Datei.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "pages": {"type": "string", "description": "Seitenbereich z.B. 1-5 oder all"}}, "required": ["path"]}}},
        "read_image": {"func": tool_read_image, "requires_approval": False, "risk_level": "low", "schema": {"description": "Liest Text aus Bild/Screenshot via OCR.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "language": {"type": "string", "description": "Sprache z.B. deu+eng"}}, "required": ["path"]}}},
    }

def tool_get_time(timezone="UTC"):
    now = datetime.utcnow()
    return {"datetime_utc": now.isoformat()+"Z", "date": now.strftime("%d.%m.%Y"), "time": now.strftime("%H:%M:%S"), "timezone": timezone}

def tool_read_file(path, encoding="utf-8"):
    try:
        p = Path(path)
        if not p.exists(): return {"error": f"Datei nicht gefunden: {path}"}
        if p.stat().st_size > 10*1024*1024: return {"error": "Datei zu gross (max 10MB)"}
        return {"path": str(p.resolve()), "content": p.read_text(encoding=encoding, errors="replace"), "size_bytes": p.stat().st_size}
    except Exception as e:
        return {"error": str(e)}

def tool_write_file(path, content, mode="write"):
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        if mode == "append":
            with p.open("a", encoding="utf-8") as f: f.write(content)
        else:
            p.write_text(content, encoding="utf-8")
        return {"success": True, "path": str(p.resolve()), "mode": mode}
    except Exception as e:
        return {"error": str(e)}

def tool_list_directory(path, show_hidden=False):
    try:
        p = Path(path)
        if not p.exists(): return {"error": f"Nicht gefunden: {path}"}
        items = [{"name": i.name, "type": "directory" if i.is_dir() else "file", "size_bytes": i.stat().st_size if i.is_file() else None} for i in sorted(p.iterdir()) if show_hidden or not i.name.startswith(".")]
        return {"path": str(p.resolve()), "items": items, "count": len(items)}
    except Exception as e:
        return {"error": str(e)}

def tool_calculate(expression):
    if not all(c in "0123456789+-*/()., " for c in expression):
        return {"error": "Ungueltige Zeichen"}
    try:
        return {"expression": expression, "result": eval(expression, {"__builtins__": {}}, {})}
    except Exception as e:
        return {"error": str(e)}

def tool_read_pdf(path, pages="all"):
    try:
        import pdfplumber
        p = Path(path)
        if not p.exists(): return {"error": f"PDF nicht gefunden: {path}"}
        with pdfplumber.open(str(p)) as pdf:
            total = len(pdf.pages)
            page_range = range(total) if pages == "all" else range(int(pages.split("-")[0])-1, min(int(pages.split("-")[1]), total))
            text_pages = [{"page": i+1, "text": pdf.pages[i].extract_text() or ""} for i in page_range]
        return {"path": str(p.resolve()), "total_pages": total, "pages": text_pages}
    except ImportError:
        return {"error": "pdfplumber nicht installiert"}
    except Exception as e:
        return {"error": str(e)}

def tool_read_image(path, language="deu+eng"):
    try:
        import pytesseract
        from PIL import Image
        p = Path(path)
        if not p.exists(): return {"error": f"Bild nicht gefunden: {path}"}
        img = Image.open(str(p))
        return {"path": str(p.resolve()), "text": pytesseract.image_to_string(img, lang=language).strip(), "language": language}
    except ImportError:
        return {"error": "pytesseract oder Pillow nicht installiert"}
    except Exception as e:
        return {"error": str(e)}
