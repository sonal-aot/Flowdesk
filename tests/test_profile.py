"""Editing your own profile: name, email and password."""

from __future__ import annotations

from conftest import auth_headers, sign_in

NORTHWIND = "northwind"


def me(client, headers):
    response = client.get("/me", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_the_profile_starts_from_the_seeded_details(client):
    body = me(client, auth_headers(client, NORTHWIND, "submitter"))
    assert body["name"] == "Sam Submitter"
    assert body["email"] == "submitter@northwind.example.com"


def test_a_user_can_change_their_name_and_email(client):
    headers = auth_headers(client, NORTHWIND, "submitter")
    response = client.patch(
        "/me",
        json={"name": "Samantha Submitter", "email": "sam@northwind.test"},
        headers=headers,
    )
    assert response.status_code == 200, response.text

    body = me(client, headers)
    assert body["name"] == "Samantha Submitter"
    assert body["email"] == "sam@northwind.test"


def test_either_field_can_be_changed_on_its_own(client):
    headers = auth_headers(client, NORTHWIND, "reviewer")
    client.patch("/me", json={"name": "Riya R."}, headers=headers)
    assert me(client, headers)["email"] == "reviewer@northwind.example.com"

    client.patch("/me", json={"email": "riya@northwind.test"}, headers=headers)
    assert me(client, headers)["name"] == "Riya R."


def test_a_blank_name_is_refused(client):
    headers = auth_headers(client, NORTHWIND, "submitter")
    response = client.patch("/me", json={"name": "   "}, headers=headers)
    assert response.status_code == 422, response.text
    assert response.json()["message"] == "Your name cannot be blank"


def test_a_bad_email_is_refused(client):
    headers = auth_headers(client, NORTHWIND, "submitter")
    response = client.patch("/me", json={"email": "not-an-email"}, headers=headers)
    assert response.status_code == 422, response.text
    assert "email address" in response.json()["message"]
    # The original is untouched.
    assert me(client, headers)["email"] == "submitter@northwind.example.com"


def test_editing_a_profile_does_not_move_you_between_companies(client):
    """`service` decides tenant membership, so it is not an editable field."""
    headers = auth_headers(client, NORTHWIND, "submitter")
    client.patch(
        "/me",
        json={"name": "Sam", "email": "sam@initech.example.com"},
        headers=headers,
    )
    assert me(client, headers)["company_id"] == NORTHWIND
    # Initech's own submitter is a different account and is unaffected.
    other = me(client, auth_headers(client, "initech", "submitter"))
    assert other["name"] == "Sam Submitter"


def test_a_user_can_change_their_password(client):
    headers = auth_headers(client, NORTHWIND, "editor")
    response = client.post(
        "/me/password",
        json={"current_password": "editor", "new_password": "much-better-secret"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert "token" in response.json()

    # The old password no longer works, the new one does.
    assert (
        client.post(
            "/auth/login",
            json={
                "company_id": NORTHWIND,
                "username": "editor",
                "password": "editor",
            },
        ).status_code
        == 403
    )
    assert sign_in(client, NORTHWIND, "editor", "much-better-secret")


def test_the_wrong_current_password_is_refused(client):
    headers = auth_headers(client, NORTHWIND, "editor")
    response = client.post(
        "/me/password",
        json={"current_password": "guessing", "new_password": "long-enough-secret"},
        headers=headers,
    )
    assert response.status_code == 403, response.text
    assert response.json()["technical"] == "That is not your current password"
    # Still signed in with the original.
    assert sign_in(client, NORTHWIND, "editor")


def test_a_short_password_is_refused(client):
    headers = auth_headers(client, NORTHWIND, "editor")
    response = client.post(
        "/me/password",
        json={"current_password": "editor", "new_password": "short"},
        headers=headers,
    )
    assert response.status_code == 422, response.text


def test_the_new_password_must_differ(client):
    headers = auth_headers(client, NORTHWIND, "submitter")
    response = client.post(
        "/me/password",
        json={"current_password": "submitter", "new_password": "submitter"},
        headers=headers,
    )
    assert response.status_code == 422, response.text
    assert response.json()["message"] == "The new password must be different"


def test_changing_a_password_signs_other_sessions_out(client):
    """Tokens carry a fingerprint of the password they were issued against."""
    laptop = auth_headers(client, NORTHWIND, "admin")
    phone = {"Authorization": f"Bearer {sign_in(client, NORTHWIND, 'admin')}"}
    assert client.get("/me", headers=phone).status_code == 200

    changed = client.post(
        "/me/password",
        json={"current_password": "admin", "new_password": "a-brand-new-secret"},
        headers=laptop,
    )
    assert changed.status_code == 200

    # The other session is out...
    stale = client.get("/me", headers=phone)
    assert stale.status_code == 403
    assert "password changed" in stale.json()["technical"]

    # ...and so is the one that made the change, unless it uses its new token.
    fresh = {"Authorization": f"Bearer {changed.json()['token']}"}
    assert client.get("/me", headers=fresh).status_code == 200


def test_a_profile_change_survives_signing_out_and_in(client):
    headers = auth_headers(client, NORTHWIND, "reviewer")
    client.patch("/me", json={"name": "Riya Reviewer-Smith"}, headers=headers)
    again = {"Authorization": f"Bearer {sign_in(client, NORTHWIND, 'reviewer')}"}
    assert me(client, again)["name"] == "Riya Reviewer-Smith"
