"""Signing in, and what each of the four roles may do."""

from __future__ import annotations

import pytest
from conftest import auth_headers, publish_fixture, sign_in

NORTHWIND = "northwind"
ROLES = ["admin", "editor", "reviewer", "submitter"]


def test_every_seeded_account_can_sign_in(client):
    for username in ROLES:
        assert sign_in(client, NORTHWIND, username)


def test_a_wrong_password_is_refused(client):
    response = client.post(
        "/auth/login",
        json={"company_id": NORTHWIND, "username": "admin", "password": "nope"},
    )
    assert response.status_code == 403, response.text
    assert response.json()["message"] == "You do not have permission to do that."


def test_failures_do_not_reveal_whether_the_account_exists(client):
    def message(payload):
        response = client.post("/auth/login", json=payload)
        assert response.status_code == 403
        return response.json()["technical"]

    real_user = message(
        {"company_id": NORTHWIND, "username": "admin", "password": "wrong"}
    )
    unknown_user = message(
        {"company_id": NORTHWIND, "username": "nobody", "password": "wrong"}
    )
    unknown_company = message(
        {"company_id": "nowhere", "username": "admin", "password": "admin"}
    )
    assert real_user == unknown_user == unknown_company


def test_the_api_needs_a_token(client):
    assert client.get("/flows").status_code == 403
    assert client.get("/flows", headers={"Authorization": "Bearer nonsense"}).status_code == 403


def test_a_tampered_token_is_refused(client):
    token = sign_in(client, NORTHWIND, "admin")
    body, signature = token.split(".", 1)
    forged = f"{body}.{signature[:-2]}xx"
    response = client.get("/flows", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 403, response.text
    assert "tampered" in response.json()["technical"]


def test_an_expired_token_is_refused(client, monkeypatch):
    from flowdesk import auth

    # Rather than travel in time, sign a token whose lifetime has already passed.
    monkeypatch.setattr(auth, "TOKEN_TTL_SECONDS", -10)
    stale, _expires = auth.issue_token(tenant_id=NORTHWIND, username="admin")
    response = client.get("/flows", headers={"Authorization": f"Bearer {stale}"})
    assert response.status_code == 403, response.text
    assert "expired" in response.json()["technical"]


def test_a_token_only_works_for_its_own_company(client):
    """The tenant is inside the signed token, so it cannot be swapped.

    Northwind's admin gets Northwind's flows, and Initech's admin gets
    Initech's -- the caller never gets to name the tenant.
    """
    northwind = client.get(
        "/instances", headers=auth_headers(client, NORTHWIND, "admin")
    ).json()
    initech = client.get(
        "/instances", headers=auth_headers(client, "initech", "admin")
    ).json()
    assert northwind == [] and initech == []

    publish_fixture(client, "expense_approval", tenant=NORTHWIND)
    started = client.post(
        "/flows/Process_expense_approval/start",
        json={},
        headers=auth_headers(client, NORTHWIND, "submitter"),
    )
    assert started.status_code == 201
    assert (
        client.get("/instances", headers=auth_headers(client, "initech", "admin")).json()
        == []
    )


@pytest.mark.parametrize(
    "username,expected",
    [
        ("admin", {"publish": True, "operate": True, "configure": True}),
        ("editor", {"publish": True, "operate": False, "configure": False}),
        ("reviewer", {"publish": False, "operate": False, "configure": False}),
        ("submitter", {"publish": False, "operate": False, "configure": False}),
    ],
)
def test_me_reports_the_right_capabilities(client, username, expected):
    body = client.get("/me", headers=auth_headers(client, NORTHWIND, username)).json()
    assert body["can_publish"] is expected["publish"]
    assert body["can_operate"] is expected["operate"]
    assert body["can_configure"] is expected["configure"]
    assert body["role"] == username


def test_an_editor_publishes_but_does_not_operate(client):
    """The library cannot express this: both admin and editor hold its admin role.

    `process_definition.import` is admin-only, so an editor must have the
    library's admin role -- which also grants suspend/resume/terminate. Keeping
    an editor out of the lifecycle is this app's own policy.
    """
    editor = auth_headers(client, NORTHWIND, "editor")
    assert client.get("/me", headers=editor).json()["library_role"] == "admin"

    publish_fixture(client, "expense_approval", tenant=NORTHWIND)
    instance_id = client.post(
        "/flows/Process_expense_approval/start",
        json={},
        headers=auth_headers(client, NORTHWIND, "submitter"),
    ).json()["id"]

    # The engine would allow it; the app does not.
    assert client.post(f"/instances/{instance_id}/hold", headers=editor).status_code == 403
    assert (
        client.post(
            f"/instances/{instance_id}/hold",
            headers=auth_headers(client, NORTHWIND, "admin"),
        ).status_code
        == 200
    )


def test_a_submitter_only_sees_their_own_runs(client):
    submitter = auth_headers(client, NORTHWIND, "submitter")
    admin = auth_headers(client, NORTHWIND, "admin")

    publish_fixture(
        client,
        "expense_approval",
        tenant=NORTHWIND,
        lanes={"Submitter": ["submitter", "admin"], "Approver": ["reviewer"]},
    )
    mine = client.post(
        "/flows/Process_expense_approval/start", json={}, headers=submitter
    ).json()["id"]
    theirs = client.post(
        "/flows/Process_expense_approval/start", json={}, headers=admin
    ).json()["id"]

    visible = [row["id"] for row in client.get("/instances", headers=submitter).json()]
    assert visible == [mine]
    everything = [row["id"] for row in client.get("/instances", headers=admin).json()]
    assert sorted(everything) == sorted([mine, theirs])


def test_only_view_all_roles_see_the_activity_log(client):
    assert (
        client.get(
            "/activity", headers=auth_headers(client, NORTHWIND, "submitter")
        ).status_code
        == 403
    )
    for username in ("admin", "editor", "reviewer"):
        assert (
            client.get(
                "/activity", headers=auth_headers(client, NORTHWIND, username)
            ).status_code
            == 200
        )
