"""Run with python -m app.worker; jobs and outbox survive container restarts."""
import logging
import signal
import threading
from datetime import UTC, datetime, timedelta
from sqlalchemy import update
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.database import get_engine
from app.models.execution import ProcessingJob
from app.services.jobs import claim, LEASE_SECONDS
from app.services.processing import process_document
from app.services.backups import process_backup
from app.api.documents import get_document_provider

log = logging.getLogger(__name__)


def main():
    logging.basicConfig(level=logging.INFO)
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    engine, settings = get_engine(), get_settings()
    while not stop.is_set():
        job = None
        try:
            with Session(engine, expire_on_commit=False) as session:
                job = claim(session)
                if job:
                    finished = threading.Event()
                    token, job_id = job.token, job.id
                    def heartbeat():
                        while not finished.wait(30):
                            try:
                                with Session(engine) as heart:
                                    now = datetime.now(UTC)
                                    heart.execute(update(ProcessingJob).where(ProcessingJob.id == job_id,
                                        ProcessingJob.token == token, ProcessingJob.status == "RUNNING")
                                        .values(updated_at=now, lease_until=now + timedelta(seconds=LEASE_SECONDS)))
                                    heart.commit()
                            except Exception:
                                log.warning("Worker heartbeat unavailable")
                    thread = threading.Thread(target=heartbeat, daemon=True)
                    thread.start()
                    try:
                        provider = get_document_provider(settings, session)
                        session.commit()
                        process_document(job.document_id, session, settings, provider, job_id=job_id, token=token)
                    except Exception:
                        session.rollback()
                        log.warning("Processing execution failed; inspect document/job API")
                    finally:
                        finished.set()
                        thread.join(timeout=5)
                process_backup(session, settings)
        except Exception:
            log.warning("Worker database/storage unavailable; retrying")
        stop.wait(1 if job else 3)


if __name__ == "__main__":
    main()
