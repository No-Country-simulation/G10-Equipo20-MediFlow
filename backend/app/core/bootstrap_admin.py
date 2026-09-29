"""Run after migrations: python -m app.core.bootstrap_admin."""
from datetime import UTC, datetime
from sqlalchemy import select

from app.core.auth import password_hash
from app.core.config import get_settings
from app.core.database import get_session
from app.models.account import Account


def main():
    password = get_settings().admin_bootstrap_password.get_secret_value()
    if not password:
        raise SystemExit("ADMIN_BOOTSTRAP_PASSWORD_REQUIRED")
    session = next(get_session())
    try:
        account = session.scalar(select(Account).where(Account.email == "admin@admin.com"))
        if account is None:
            session.add(Account(email="admin@admin.com", password_hash=password_hash(password),
                                role="SUPERADMIN", created_at=datetime.now(UTC)))
            session.commit()
        elif account.role != "SUPERADMIN":
            raise SystemExit("ADMIN_EMAIL_ALREADY_USED")
    finally:
        session.close()


if __name__ == "__main__":
    main()
