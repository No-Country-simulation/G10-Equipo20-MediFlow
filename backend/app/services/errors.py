class DocumentError(Exception):
    def __init__(self, status_code: int, detail: str, document_id=None):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.document_id = document_id
