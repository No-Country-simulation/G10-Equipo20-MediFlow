"""PyMuPDF aislado en un proceso: la biblioteca no admite uso multihilo."""
import base64
import json
import sys

import pymupdf


def read_pdf(path: str, max_pages: int, max_characters: int) -> dict:
    with pymupdf.open(path) as document, pymupdf.open() as visual:
        if document.is_encrypted or document.page_count == 0:
            return {"error": "PDF_CONTENT_UNREADABLE"}
        if document.page_count > max_pages:
            return {"error": "PROCESSING_PAGE_LIMIT"}
        pages, ocr_numbers = [], []
        total_characters = 0
        for index, page in enumerate(document):
            text = page.get_text("text", sort=True)
            if not text.strip() or page.get_image_info():
                ocr_numbers.append(index + 1)
                visual.insert_pdf(document, from_page=index, to_page=index)
            else:
                total_characters += len(text)
                if total_characters > max_characters:
                    return {"error": "PROCESSING_TEXT_LIMIT"}
                pages.append({"page": index + 1, "text": text})
        return {
            "pages": pages,
            "ocr_numbers": ocr_numbers,
            "ocr_pdf": base64.b64encode(visual.tobytes(garbage=3, deflate=True)).decode("ascii") if ocr_numbers else None,
        }


if __name__ == "__main__":
    # Sin mensajes nativos que puedan mezclarse con el protocolo JSON.
    pymupdf.TOOLS.mupdf_display_errors(False)
    pymupdf.TOOLS.mupdf_display_warnings(False)
    try:
        result = read_pdf(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]))
    except Exception:
        result = {"error": "PDF_CONTENT_UNREADABLE"}
    print(json.dumps(result, ensure_ascii=True))
