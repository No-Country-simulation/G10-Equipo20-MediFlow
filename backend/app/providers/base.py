from typing import Protocol

from app.schemas.processing import ClassificationResult, ContentResult, ExtractionResult, OCRResult


class ProviderError(Exception):
    """Error publico sin mensaje crudo del SDK, secretos ni contenido documental."""
    def __init__(self, code: str, http_status: int = 502):
        super().__init__(code)
        self.code = code
        self.http_status = http_status


class DocumentProvider(Protocol):
    def ocr(self, data: bytes, mime_type: str) -> OCRResult: ...
    def classify(self, content: ContentResult) -> ClassificationResult: ...
    def extract(self, content: ContentResult, classification: ClassificationResult) -> ExtractionResult: ...
