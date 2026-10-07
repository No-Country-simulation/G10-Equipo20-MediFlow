"""Transactional result outbox; exact recorded keys are the deletion boundary."""
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
import json
from sqlalchemy import select
from app.models.document import Document
from app.models.execution import ResultBackup
from app.services.storage import get_storage


def schedule_backup(session, document, settings):
    if not document.processing_result or document.storage_backend != "r2":
        return
    now = datetime.now(UTC)
    key = f"{settings.r2_object_prefix}/{document.country}/results/{document.document_id}/{document.status}/{uuid4()}.json"
    session.add(ResultBackup(document_id=document.document_id, storage_key=key,
        payload={"schema_version": "mediflow-result-backup-v1", "snapshot_at": now.isoformat(),
                 "document_id": str(document.document_id), "country": document.country,
                 "metadata": {"original_filename": document.original_filename, "format": document.format,
                              "size_bytes": document.size_bytes, "origin_channel": document.origin_channel,
                              "original_storage_key": document.storage_key, "storage_bucket": document.storage_bucket},
                 "sha256": document.sha256, "result": document.processing_result,
                 "history": document.state_history, "reviews": document.review_history},
        status="PENDING", attempts=0, created_at=now, retry_at=now))


def process_backup(session, settings):
    # Lock the outbox row across this bounded storage operation. Delete locks the
    # same rows before deleting any objects, preventing uploads after deletion.
    row = session.scalar(select(ResultBackup).where(ResultBackup.status.in_(("PENDING", "FAILED")),
                         ResultBackup.retry_at <= datetime.now(UTC)).order_by(ResultBackup.id)
                         .with_for_update(skip_locked=True).limit(1))
    if not row:
        session.commit()
        return False
    document = session.get(Document, row.document_id)
    row.attempts += 1
    try:
        with TemporaryDirectory(prefix="mediflow-backup-") as temporary:
            path = Path(temporary) / "result.json"
            data = json.dumps(row.payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            path.write_bytes(data)
            storage = get_storage(settings, document.storage_backend, document.storage_bucket)
            storage.put_snapshot(row.storage_key, path)
        row.status, row.error_code = "SYNCED", None
    except OSError:
        row.status, row.error_code = "FAILED", "RESULT_BACKUP_UNAVAILABLE"
        row.retry_at = datetime.now(UTC) + timedelta(seconds=min(3600, 30 * 2 ** min(row.attempts, 7)))
    session.commit()
    return True
