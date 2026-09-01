"""Request identity and the app-owned read guard.

Every request carries ``X-Tenant-Id`` and ``X-User`` headers, standing in for
the claims a real deployment would read off a Keycloak JWT. Faking the claims
keeps the RBAC surface visible instead of buried in an OIDC flow.

The guard matters because the library authorizes the WRITE side only:
``execute_query`` never checks tenant membership and most queries do not even
accept a user id, so whatever tenant id the host passes is trusted. This module
is the only thing standing between a caller and another tenant's data on reads.
See FINDINGS.md #2.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header
from m8flow_bpmn_core.errors import AuthorizationError, NotFoundError
from m8flow_bpmn_core.models.user import UserModel
from m8flow_bpmn_core.services.tenant_users import ensure_user_belongs_to_tenant
from sqlalchemy import select
from sqlalchemy.orm import Session

from flowdesk.db import get_session


@dataclass(frozen=True, slots=True)
class Caller:
    tenant_id: str
    user_id: int
    username: str


def current_caller(
    session: Session = Depends(get_session),
    x_tenant_id: str = Header(..., alias="X-Tenant-Id"),
    x_user: str = Header(..., alias="X-User"),
) -> Caller:
    # Usernames are deliberately duplicated across tenants, so pick the namesake
    # whose service realm resolves to the requested tenant.
    namesakes = session.scalars(
        select(UserModel).where(UserModel.username == x_user).order_by(UserModel.id)
    ).all()
    if not namesakes:
        raise NotFoundError(f"Unknown user {x_user!r}")

    for candidate in namesakes:
        try:
            ensure_user_belongs_to_tenant(
                session, tenant_id=x_tenant_id, user_id=candidate.id
            )
        except AuthorizationError:
            continue
        return Caller(
            tenant_id=x_tenant_id, user_id=candidate.id, username=candidate.username
        )

    raise AuthorizationError(
        f"User {x_user!r} does not belong to tenant {x_tenant_id!r}"
    )
