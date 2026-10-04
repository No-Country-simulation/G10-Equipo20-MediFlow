"""Small local account/session layer for the MVP."""
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.models.account import Account, LoginSession

COOKIE_NAME = "mediflow_session"
SESSION_SECONDS = 8 * 60 * 60


def password_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600_000)
    return f"pbkdf2_sha256$600000${salt.hex()}${digest.hex()}"


def password_matches(password: str, stored: str) -> bool:
    try:
        algorithm, count, salt, expected = stored.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(count))
        return hmac.compare_digest(actual, bytes.fromhex(expected))
    except (ValueError, TypeError):
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(account: Account, session: Session, response: Response, request: Request) -> None:
    token = secrets.token_urlsafe(32)
    session.add(LoginSession(token_hash=token_hash(token), account_id=account.id,
                             expires_at=datetime.now(UTC) + timedelta(seconds=SESSION_SECONDS)))
    session.commit()
    response.set_cookie(COOKIE_NAME, token, max_age=SESSION_SECONDS, httponly=True,
                        samesite="lax", secure=request.url.scheme == "https", path="/")
    response.headers["Cache-Control"] = "no-store"


def current_account(request: Request, session: Annotated[Session, Depends(get_session)]) -> Account:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(401, "LOGIN_REQUIRED")
    record = session.get(LoginSession, token_hash(token))
    if record is None or record.expires_at < datetime.now(UTC):
        raise HTTPException(401, "SESSION_EXPIRED")
    account = session.get(Account, record.account_id)
    if account is None:
        raise HTTPException(401, "LOGIN_REQUIRED")
    if not account.active:
        raise HTTPException(403, "ACCOUNT_DISABLED")
    return account


def require_superadmin(account: Annotated[Account, Depends(current_account)]) -> dict[str, str]:
    if account.role != "SUPERADMIN":
        raise HTTPException(403, "SUPERADMIN_REQUIRED")
    return {"id": str(account.id), "role": account.role}


def require_staff(account: Annotated[Account, Depends(current_account)], session: Annotated[Session, Depends(get_session)]):
    if account.role not in ("SUPERADMIN", "EMPLOYEE"):
        raise HTTPException(403, "STAFF_REQUIRED")
    from app.core.permissions import effective_permissions
    granted, denied = effective_permissions(account, session)
    return {"id": str(account.id), "role": account.role, "permissions": granted, "denied_permissions": denied}


def require_permission(code):
    def check(staff: Annotated[dict, Depends(require_staff)]):
        if staff['role'] != 'SUPERADMIN' and (code in staff.get('denied_permissions', []) or code not in staff.get('permissions', [])):
            raise HTTPException(403, "PERMISSION_DENIED:" + code)
        return staff
    return check


def require_patient(account: Annotated[Account, Depends(current_account)]) -> Account:
    if account.role != "PATIENT":
        raise HTTPException(403, "PATIENT_REQUIRED")
    return account


def same_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin and origin != f"{request.url.scheme}://{request.headers.get('host')}":
        raise HTTPException(403, "ORIGIN_NOT_ALLOWED")
