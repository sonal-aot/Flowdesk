"""Password login and signed session tokens.

m8flow authenticates through Keycloak. There is no identity provider here, so
this is a self-contained stand-in: passwords are hashed with PBKDF2 and a
successful login returns an HMAC-signed token carrying the tenant, the username
and an expiry. Nothing is stored server-side, so the token is the session.

It is deliberately small and deliberately not a substitute for an IdP -- swapping
it for real OIDC means replacing `resolve_token` and the login route.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time

from m8flow_bpmn_core.errors import AuthorizationError

SECRET = os.environ.get("FLOWDESK_SECRET_KEY", "flowdesk-development-secret")
TOKEN_TTL_SECONDS = int(os.environ.get("FLOWDESK_SESSION_HOURS", "12")) * 3600
PBKDF2_ROUNDS = 120_000


# --------------------------------------------------------------------------- #
# Passwords
# --------------------------------------------------------------------------- #


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    """`pbkdf2$<rounds>$<salt>$<digest>`, all base64."""
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt, PBKDF2_ROUNDS
    )
    return "$".join(
        (
            "pbkdf2",
            str(PBKDF2_ROUNDS),
            base64.b64encode(salt).decode(),
            base64.b64encode(digest).decode(),
        )
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, rounds, salt_b64, digest_b64 = stored.split("$")
        if scheme != "pbkdf2":
            return False
        candidate = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode(),
            base64.b64decode(salt_b64),
            int(rounds),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate, base64.b64decode(digest_b64))


# --------------------------------------------------------------------------- #
# Tokens
# --------------------------------------------------------------------------- #


def _sign(payload: bytes) -> str:
    signature = hmac.new(SECRET.encode(), payload, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(signature).decode().rstrip("=")


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def issue_token(*, tenant_id: str, username: str) -> tuple[str, int]:
    """Returns the token and when it expires, in epoch seconds."""
    expires_at = int(time.time()) + TOKEN_TTL_SECONDS
    payload = json.dumps(
        {"tenant": tenant_id, "user": username, "exp": expires_at},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    body = _b64(payload)
    return f"{body}.{_sign(payload)}", expires_at


def resolve_token(token: str) -> tuple[str, str]:
    """Returns (tenant_id, username), or raises if the token is no good."""
    try:
        body, signature = token.split(".", 1)
        payload = _unb64(body)
    except (ValueError, TypeError) as exc:
        raise AuthorizationError("That session token is malformed") from exc

    if not hmac.compare_digest(signature, _sign(payload)):
        raise AuthorizationError("That session token has been tampered with")

    claims = json.loads(payload)
    if int(claims.get("exp", 0)) < time.time():
        raise AuthorizationError("Your session has expired — sign in again")
    return str(claims["tenant"]), str(claims["user"])
