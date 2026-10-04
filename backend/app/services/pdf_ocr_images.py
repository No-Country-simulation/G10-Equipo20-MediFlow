"""Bounded PDF rasterization in an isolated process for OpenAI vision."""
import base64
import json
import sys
import pymupdf


def render(path, max_pages, max_bytes):
    with pymupdf.open(path) as document:
        if document.is_encrypted or not 0 < document.page_count <= max_pages:
            return {"error": "PDF_PAGE_LIMIT_OR_INVALID"}
        images, size = [], 0
        for page in document:
            scale = min(2, 1500 / max(page.rect.width, 1), 2000 / max(page.rect.height, 1))
            image = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False).tobytes("png")
            size += len(image)
            if size > max_bytes:
                return {"error": "OCR_PAYLOAD_TOO_LARGE"}
            images.append(base64.b64encode(image).decode("ascii"))
        return {"images": images}


if __name__ == "__main__":
    pymupdf.TOOLS.mupdf_display_errors(False)
    pymupdf.TOOLS.mupdf_display_warnings(False)
    try:
        result = render(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]))
    except Exception:
        result = {"error": "PDF_CONTENT_UNREADABLE"}
    print(json.dumps(result))
