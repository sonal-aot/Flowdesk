from __future__ import annotations

import json
import pathlib
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from flowdesk import db

FIXTURES = pathlib.Path(__file__).parent.parent / "examples"

#: Lane assignments used by the tests. The app ships no flows, so every test
#: publishes what it needs -- which is also how a real workspace starts.
FIXTURE_LANES: dict[str, dict[str, list[str]]] = {
    "two_step_request": {
        "Requester": ["submitter"],
        "Approver": ["reviewer"],
    },
    "expense_approval": {
        "Submitter": ["submitter"],
        "Approver": ["reviewer"],
    },
    "incident_response": {
        "Reporter": ["submitter"],
        "Engineering": ["reviewer"],
        "Support": ["editor"],
    },
    "access_request": {
        "Requester": ["submitter"],
        "System Owner": ["reviewer"],
        "Security": ["admin"],
    },
    "capability_tour": {
        "Requester": ["submitter"],
        "Approver": ["reviewer"],
        "Finance": ["editor"],
    },
}


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


def publish_fixture(
    client,
    name: str,
    *,
    tenant: str = "northwind",
    actor: str = "admin",
    lanes: dict[str, list[str]] | None = None,
    edit=None,
) -> dict:
    """Publish one of the example diagrams in tests/fixtures."""
    bpmn = (FIXTURES / f"{name}.bpmn").read_text(encoding="utf-8")
    if edit is not None:
        bpmn = edit(bpmn)

    body: dict = {
        "bpmn": bpmn,
        "lane_owners": lanes if lanes is not None else FIXTURE_LANES[name],
        "forms": {},
    }
    forms = FIXTURES / f"{name}.forms.json"
    if forms.exists():
        body["forms"] = json.loads(forms.read_text(encoding="utf-8"))
    dmn = FIXTURES / f"{name}.dmn"
    if dmn.exists():
        body["dmn"] = dmn.read_text(encoding="utf-8")

    response = client.post(
        "/flows", json=body, headers=auth_headers(client, tenant, actor)
    )
    assert response.status_code == 201, response.text
    return response.json()
