from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import select

from app.core.auth import password_hash, password_matches
from app.core.config import Settings
from app.core import bootstrap_admin
from app.core.login_security import WINDOW, clean_login_attempts
from app.models.account import Account, LoginAttempt


@pytest.mark.parametrize('role', ['SUPERADMIN', 'PATIENT'])
def test_failed_logins_are_limited_and_recover_after_window(client, session, role):
    account = Account(email='security-test@example.com', role=role, active=True,
        password_hash=password_hash('private-test-password'), created_at=datetime.now(UTC),
        country='CO' if role == 'PATIENT' else None,
        identity_type='CC' if role == 'PATIENT' else None,
        identity_number='1099900100' if role == 'PATIENT' else None)
    session.add(account); session.flush()
    path = '/auth/patient-login' if role == 'PATIENT' else '/auth/admin-login'
    body = {'country': 'CO', 'identity_number': '1099900100'} if role == 'PATIENT' else {'email': account.email}
    for _ in range(5):
        assert client.post(path, json={**body, 'password': 'wrong-password'}).status_code == 401
    response = client.post(path, json={**body, 'password': 'private-test-password'})
    assert response.status_code == 429 and int(response.headers['retry-after']) > 0
    attempt = session.scalar(select(LoginAttempt))
    assert attempt.failures == 5
    assert account.email not in attempt.identity_hash
    assert '1099900100' not in attempt.identity_hash
    attempt.window_started = datetime.now(UTC) - WINDOW - timedelta(seconds=1)
    session.commit()
    response = client.post(path, json={**body, 'password': 'private-test-password'})
    assert response.status_code == 200, response.text
    assert session.scalar(select(LoginAttempt)) is None


def test_unknown_and_disabled_accounts_keep_generic_error(client, session):
    response = client.post('/auth/admin-login', json={'email': 'missing@example.com', 'password': 'wrong-password'})
    assert response.status_code == 401 and response.json()['detail'] == 'INVALID_CREDENTIALS'
    session.add(Account(email='disabled@example.com', role='SUPERADMIN', active=False,
        password_hash=password_hash('private-test-password'), created_at=datetime.now(UTC)))
    session.flush()
    response = client.post('/auth/admin-login', json={'email': 'disabled@example.com', 'password': 'private-test-password'})
    assert response.status_code == 401 and response.json()['detail'] == 'INVALID_CREDENTIALS'


def test_auth_rejects_oversized_password_and_other_origins(client):
    assert client.post('/auth/admin-login', json={'email': 'test@example.com', 'password': 'x' * 129}).status_code == 422
    assert client.post('/auth/admin-login', json={'email': 'test@example.com', 'password': 'wrong-password'},
                       headers={'Origin': 'https://untrusted.example.com'}).status_code == 403


def test_login_cleanup_removes_expired_records_only(session):
    old = LoginAttempt(identity_hash='a'*64, failures=5, window_started=datetime.now(UTC)-WINDOW-timedelta(seconds=1))
    current = LoginAttempt(identity_hash='b'*64, failures=2, window_started=datetime.now(UTC))
    session.add_all([old, current]); session.flush()
    clean_login_attempts(session)
    session.flush()
    assert session.scalars(select(LoginAttempt.identity_hash)).all() == ['b'*64]


@pytest.mark.parametrize('settings,error', [
    (Settings(postgres_password='test'), 'ADMIN_BOOTSTRAP_EMAIL_REQUIRED'),
    (Settings(postgres_password='test', admin_bootstrap_email='setup@example.com'), 'ADMIN_BOOTSTRAP_PASSWORD_REQUIRED'),
    (Settings(postgres_password='test', admin_bootstrap_email='setup@example.com', admin_bootstrap_password='short'), 'ADMIN_BOOTSTRAP_PASSWORD_LENGTH_INVALID'),
])
def test_bootstrap_requires_private_configuration(settings, error):
    with patch.object(bootstrap_admin, 'get_settings', return_value=settings), pytest.raises(SystemExit, match=error):
        bootstrap_admin.main()


def test_bootstrap_uses_configured_identity_and_does_not_reset_existing_password():
    settings = Settings(postgres_password='test', admin_bootstrap_email='Setup@example.com',
                        admin_bootstrap_password='private-test-password')
    session = Mock()
    session.scalar.return_value = None
    with patch.object(bootstrap_admin, 'get_settings', return_value=settings), patch.object(
            bootstrap_admin, 'get_session', return_value=iter([session])):
        bootstrap_admin.main()
    account = session.add.call_args.args[0]
    assert account.email == 'setup@example.com'
    assert account.role == 'SUPERADMIN'
    assert password_matches('private-test-password', account.password_hash)
    existing = Mock(role='SUPERADMIN', password_hash='existing-hash')
    session.reset_mock(); session.scalar.return_value = existing
    with patch.object(bootstrap_admin, 'get_settings', return_value=settings), patch.object(
            bootstrap_admin, 'get_session', return_value=iter([session])):
        bootstrap_admin.main()
    session.add.assert_not_called()
    assert existing.password_hash == 'existing-hash'
