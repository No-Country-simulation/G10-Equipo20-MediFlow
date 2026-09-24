import base64
import json
from pathlib import Path
import subprocess
import sys

from app.core.config import Settings
from app.providers.base import DocumentProvider, ProviderError
from app.schemas.processing import ContentPage, ContentResult
from app.services.errors import DocumentError


class ContentReader:
    def __init__(self, provider: DocumentProvider, settings: Settings):
        self.provider = provider
        self.settings = settings

    def read(self, path: Path, format: str) -> ContentResult:
        if not path.is_file():
            raise DocumentError(422, "DOCUMENT_FILE_MISSING")
        if path.stat().st_size > self.settings.max_upload_bytes:
            raise DocumentError(413, "PROCESSING_FILE_TOO_LARGE")
        if format != "pdf":
            result = self.provider.ocr(path.read_bytes(), "image/jpeg" if format == "jpeg" else "image/png")
            pages = self._ocr_pages(result, [1])
        else:
            try:
                process = subprocess.run(
                    [sys.executable, "-m", "app.services.pdf_reader", str(path),
                     str(self.settings.processing_max_pages), str(self.settings.processing_max_characters)],
                    capture_output=True, check=True, timeout=self.settings.pdf_timeout_seconds,
                )
                extracted = json.loads(process.stdout)
            except subprocess.TimeoutExpired:
                raise DocumentError(504, "PDF_EXTRACTION_TIMEOUT") from None
            except (subprocess.CalledProcessError, ValueError, OSError):
                raise DocumentError(422, "PDF_CONTENT_UNREADABLE") from None
            if extracted.get("error"):
                raise DocumentError(422, extracted["error"])
            pages = [ContentPage(**page, method="embedded_text", engine="pymupdf") for page in extracted["pages"]]
            if extracted["ocr_pdf"] is not None:
                payload = base64.b64decode(extracted["ocr_pdf"])
                if len(payload) > self.settings.max_upload_bytes:
                    raise DocumentError(413, "OCR_PAYLOAD_TOO_LARGE")
                pages.extend(self._ocr_pages(self.provider.ocr(payload, "application/pdf"), extracted["ocr_numbers"]))
        pages.sort(key=lambda page: page.page)
        if sum(len(page.text) for page in pages) > self.settings.processing_max_characters:
            raise DocumentError(422, "PROCESSING_TEXT_LIMIT")
        return ContentResult(pages=pages)

    @staticmethod
    def _ocr_pages(result, original_numbers):
        if [page.page for page in result.pages] != list(range(1, len(original_numbers) + 1)):
            raise ProviderError("OCR_PAGE_MAPPING_INVALID")
        return [ContentPage(
            page=original, text=page.text, method="gemini_ocr", engine="gemini",
            uncertain=page.uncertain or "[ILEGIBLE]" in page.text.upper(),
        ) for original, page in zip(original_numbers, result.pages, strict=True)]
