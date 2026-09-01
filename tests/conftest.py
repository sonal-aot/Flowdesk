from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from flowdesk import db


@pytest.fixture()
def client(tmp_path) -> Iterator[TestClient]:
    db.reset_for_tests(f"sqlite+pysqlite:///{tmp_path / 'test.db'}")
    from flowdesk.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def session(client):
    """A raw session on the same test database, for library-level assertions."""
    from flowdesk import db as db_module

    session = db_module.session_factory()()
    try:
        yield session
    finally:
        session.close()


_tokens: dict[tuple[str, str], str] = {}


def sign_in(client, tenant: str, username: str, password: str | None = None) -> str:
    """Log in and return the bearer token. Demo passwords equal the username."""
    response = client.post(
        "/auth/login",
        json={
            "company_id": tenant,
            "username": username,
            "password": password if password is not None else username,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["token"]


def headers(tenant: str, username: str) -> dict[str, str]:
    """Authorization header for a seeded account, signing in once per test run."""
    raise RuntimeError("use auth_headers(client, tenant, username)")


def auth_headers(client, tenant: str, username: str) -> dict[str, str]:
    key = (tenant, username)
    if key not in _tokens:
        _tokens[key] = sign_in(client, tenant, username)
    return {"Authorization": f"Bearer {_tokens[key]}"}


@pytest.fixture(autouse=True)
def _clear_tokens():
    """Each test gets a fresh database, so tokens must not be reused across them."""
    _tokens.clear()
    yield
    _tokens.clear()
