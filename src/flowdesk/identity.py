"""Request identity, from a bearer token.

The token is the session (see auth.py). Resolving it gives a tenant and a
username; this module turns those into the tenant id and integer user id every
library command needs, and verifies the two actually belong together.

That last check matters because the library authorizes the WRITE side only:
`execute_query` never checks tenant membership and most queries do not even
accept a user id, so whatever tenant id the host passes is trusted. This module
is the only thing standing between a caller and another tenant's data on reads.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header
from m8flow_bpmn_core.errors import AuthorizationError
from m8flow_bpmn_core.models.user import UserModel
from m8flow_bpmn_core.services.tenant_users import ensure_user_belongs_to_tenant
from sqlalchemy import select
from sqlalchemy.orm import Session

from flowdesk import store
from flowdesk.auth import password_version, resolve_token
from flowdesk.db import get_session
from flowdesk.seed import service_url


@dataclass(frozen=True, slots=True)
class Caller:
    tenant_id: str
    user_id: int
    username: str


def current_caller(
    session: Session = Depends(get_session),
    authorization: str | None = Header(default=None),
) -> Caller:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthorizationError("Sign in to continue")
    tenant_id, username, version = resolve_token(
        authorization.split(" ", 1)[1].strip()
    )

    # Usernames repeat across companies, so resolve within the token's tenant.
    user = session.scalar(
        select(UserModel).where(
            UserModel.service == service_url(tenant_id),
            UserModel.service_id == username,
        )
    )
    if user is None:
        raise AuthorizationError("That account no longer exists")

    # A token issued before a password change must stop working.
    stored = store.credential(session, tenant_id, username)
    if stored is None or version != password_version(stored.password_hash):
        raise AuthorizationError("Your password changed — sign in again")

    # The library's own membership rule, applied to reads as well as writes.
    ensure_user_belongs_to_tenant(session, tenant_id=tenant_id, user_id=user.id)
    return Caller(tenant_id=tenant_id, user_id=user.id, username=username)
