"""PostgreSQL leases fence concurrent/recovered executions; no external queue."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from sqlalchemy import select, or_
from app.models.document import Document
from app.models.execution import ProcessingJob
from app.services.errors import DocumentError

LEASE_SECONDS = 300
ACTIVE = ("QUEUED", "RUNNING")


def active_job(session, document_id):
    return session.scalar(select(ProcessingJob).where(ProcessingJob.document_id == document_id,
                          ProcessingJob.status.in_(ACTIVE)))


def enqueue(session, document_id, *, running=False):
    from app.services.processing import locked_document
    document = locked_document(document_id, session)
    job = active_job(session, document_id)
    if job:
        if running:
            raise DocumentError(409, "DOCUMENT_ALREADY_PROCESSING")
        return job
    if document.status in ("RECHAZADO", "ENTREGADO", "ENRUTADO", "EN_REVISION_HUMANA", "RESUELTO"):
        raise DocumentError(409, "DOCUMENT_ALREADY_FINALIZED")
    now = datetime.now(UTC)
    job = ProcessingJob(document_id=document_id, status="RUNNING" if running else "QUEUED",
        created_at=now, updated_at=now, completed_nodes=[], provider_calls={}, attempt=0,
        token=uuid4() if running else None, lease_until=now + timedelta(seconds=LEASE_SECONDS) if running else None)
    session.add(job)
    session.commit()
    return job


def claim(session):
    now = datetime.now(UTC)
    job = session.scalar(select(ProcessingJob).where(or_(ProcessingJob.status == "QUEUED",
         (ProcessingJob.status == "RUNNING") & (ProcessingJob.lease_until < now)))
         .order_by(ProcessingJob.created_at).with_for_update(skip_locked=True).limit(1))
    if job:
        job.status, job.token = "RUNNING", uuid4()
        job.lease_until = now + timedelta(seconds=LEASE_SECONDS)
        job.updated_at = now
    session.commit()
    return job


def owned_job(session, job_id, token):
    with session.no_autoflush:
        job = session.scalar(select(ProcessingJob).where(ProcessingJob.id == job_id).with_for_update()
                             .execution_options(populate_existing=True))
    if not job or job.token != token or job.status != "RUNNING":
        session.rollback()
        raise DocumentError(409, "PROCESSING_LEASE_LOST")
    job.updated_at = datetime.now(UTC)
    job.lease_until = job.updated_at + timedelta(seconds=LEASE_SECONDS)
    return job


class CountedProvider:
    def __init__(self, provider, before_call):
        self.provider, self.before_call = provider, before_call
        self.name, self.model = getattr(provider, "name", "gemini"), getattr(provider, "model", "unknown")

    def ocr(self, *args):
        self.before_call("ocr")
        return self.provider.ocr(*args)

    def classify(self, *args):
        self.before_call("classify")
        return self.provider.classify(*args)

    def extract(self, *args):
        self.before_call("extract")
        return self.provider.extract(*args)
