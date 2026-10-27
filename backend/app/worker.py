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
from app.services.notifications import process_notification
from app.services.email_notifications import process_email_notification
from app.api.documents import get_document_provider
from app.core.login_security import clean_login_attempts

log = logging.getLogger(__name__)


def notification_loop(engine, settings, stop):
    """Own sessions: a slow LLM or R2 backup must not delay urgent notices."""
    while not stop.is_set():
        delivered = False
        try:
            with Session(engine) as session:
                delivered = process_notification(session, settings)
        except Exception:
            log.warning('Slack delivery unavailable; inspect notification status')
        if not delivered:
            stop.wait(2)


def main():
    logging.basicConfig(level=logging.INFO)
    # httpx INFO logs contain the full request URL, including webhook secrets.
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    stop = threading.Event()
    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, lambda *_: stop.set())
            except (ValueError, AttributeError):
                pass
    engine, settings = get_engine(), get_settings()
    notifications = threading.Thread(target=notification_loop, args=(engine, settings, stop), daemon=True)
    notifications.start()
    next_login_cleanup = datetime.now(UTC)
    while not stop.is_set():
        job = None
        try:
            with Session(engine, expire_on_commit=False) as session:
                if datetime.now(UTC) >= next_login_cleanup:
                    clean_login_attempts(session)
                    session.commit()
                    next_login_cleanup = datetime.now(UTC) + timedelta(minutes=15)
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
                for deliver in (process_backup, process_email_notification):
                    try:
                        deliver(session, settings)
                    except Exception:
                        session.rollback()
                        log.warning('Background delivery unavailable; inspect delivery status')
        except Exception:
            log.warning("Worker database/storage unavailable; retrying")
        stop.wait(1 if job else 3)
    notifications.join(timeout=12)


if __name__ == "__main__":
    main()
