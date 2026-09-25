"""Render one original PDF page in an isolated PyMuPDF process."""
import base64
import json
import sys
import pymupdf


def render(path, page_number):
    with pymupdf.open(path) as document:
        if document.is_encrypted or not document.page_count:
            return {"error": "PDF_CONTENT_UNREADABLE"}
        if page_number < 1 or page_number > document.page_count:
            return {"error": "PAGE_NOT_FOUND"}
        page = document[page_number - 1]
        scale = min(2, 1500 / max(page.rect.width, 1), 2000 / max(page.rect.height, 1))
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
        return {"pages": document.page_count, "image": base64.b64encode(pixmap.tobytes("png")).decode("ascii")}


if __name__ == "__main__":
    pymupdf.TOOLS.mupdf_display_errors(False)
    pymupdf.TOOLS.mupdf_display_warnings(False)
    try:
        result = render(sys.argv[1], int(sys.argv[2]))
    except Exception:
        result = {"error": "PDF_CONTENT_UNREADABLE"}
    print(json.dumps(result))
