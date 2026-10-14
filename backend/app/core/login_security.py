"""Account-scoped failed-login limits without storing submitted identifiers."""
import hashlib
from datetime import UTC, datetime, timedelta
from functools import lru_cache
import secrets

from fastapi import HTTPException
from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert

from app.core.auth import password_hash, password_matches
from app.models.account import LoginAttempt

FAILURE_LIMIT = 5
WINDOW = timedelta(minutes=15)


@lru_cache(maxsize=1)
def dummy_password_hash():
    return password_hash(secrets.token_urlsafe(32))


def begin_login(session, identity):
    now = datetime.now(UTC)
    key = hashlib.sha256(identity.encode()).hexdigest()
    # An upsert followed by a row lock also serializes the first parallel tries.
    session.execute(insert(LoginAttempt).values(identity_hash=key, failures=0, window_started=now)
                    .on_conflict_do_nothing(index_elements=['identity_hash']))
    row = session.scalar(select(LoginAttempt).where(LoginAttempt.identity_hash == key).with_for_update())
    if now - row.window_started >= WINDOW:
        row.failures, row.window_started = 0, now
    if row.failures >= FAILURE_LIMIT:
        retry = max(1, int((row.window_started + WINDOW - now).total_seconds()))
        session.rollback()
        raise HTTPException(429, 'LOGIN_RATE_LIMITED', headers={'Retry-After': str(retry)})
    return row


def verify_login(session, attempt, account, password):
    # Use the same expensive verification when an account is missing or disabled.
    valid = password_matches(password, account.password_hash if account else dummy_password_hash())
    if account is None or not account.active or not valid:
        attempt.failures += 1
        session.commit()
        raise HTTPException(401, 'INVALID_CREDENTIALS')
    # No record is needed after successful authentication.
    session.delete(attempt)


def clean_login_attempts(session):
    session.execute(delete(LoginAttempt).where(LoginAttempt.window_started < datetime.now(UTC) - WINDOW))
