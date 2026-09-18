from uuid import UUID

from sqlalchemy.orm import Session

from app.models.document import Document


class DocumentRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, document_id: UUID) -> Document | None:
        return self.session.get(Document, document_id)

    def add(self, document: Document) -> None:
        self.session.add(document)
        self.session.flush()

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()
