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


def headers(tenant: str, user: str) -> dict[str, str]:
    return {"X-Tenant-Id": tenant, "X-User": user}


@pytest.fixture()
def session(client):
    """A raw session on the same test database, for library-level assertions."""
    from flowdesk import db as db_module

    session = db_module.session_factory()()
    try:
        yield session
    finally:
        session.close()
