"""Tenants, people and roles.

Two companies carry the same four usernames on purpose: if tenant scoping ever
leaks, it shows up as the wrong person rather than a tidy error.

The roles map onto the library's V1 RBAC, which is what actually decides who may
publish a flow:

* ``designer`` -> admin: may import process definitions, and run the lifecycle
* ``analyst``  -> user: may start flows and work on tasks
* ``reviewer`` -> manager: may work on tasks but NOT start anything
* ``auditor``  -> manager: same, kept separate so lane assignment has somebody
  to hand work to

`reviewer` being unable to start a flow is the library's behaviour, not a
choice: V1 grants `process.start` to `user` and `admin` but not to `manager`.
"""

from __future__ import annotations

from m8flow_bpmn_core.models.tenant import M8flowTenantModel
from m8flow_bpmn_core.models.user import UserModel
from m8flow_bpmn_core.services.authorization import (
    ROLE_ADMIN,
    ROLE_MANAGER,
    ROLE_USER,
    ensure_v1_role,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

TENANTS: dict[str, str] = {"northwind": "Northwind Traders", "initech": "Initech"}

#: username -> (display name, job title, V1 role)
USERS: dict[str, tuple[str, str, str]] = {
    "designer": ("Dana Designer", "Process Designer", ROLE_ADMIN),
    "analyst": ("Amir Analyst", "Business Analyst", ROLE_USER),
    "reviewer": ("Rosa Reviewer", "Team Lead", ROLE_MANAGER),
    "auditor": ("Aki Auditor", "Compliance Auditor", ROLE_MANAGER),
}


def service_url(tenant_id: str) -> str:
    """The realm suffix is what the library reads as the tenant."""
    return f"http://localhost:7002/realms/{tenant_id}"


def seed(session: Session) -> None:
    for tenant_id, tenant_name in TENANTS.items():
        if session.get(M8flowTenantModel, tenant_id) is None:
            session.add(
                M8flowTenantModel(id=tenant_id, name=tenant_name, slug=tenant_id)
            )
        session.flush()

        by_role: dict[str, list[int]] = {}
        for username, (display_name, _title, role) in USERS.items():
            user = session.scalar(
                select(UserModel).where(
                    UserModel.service == service_url(tenant_id),
                    UserModel.service_id == username,
                )
            )
            if user is None:
                user = UserModel(
                    username=username,
                    email=f"{username}@{tenant_id}.example.com",
                    service=service_url(tenant_id),
                    service_id=username,
                    display_name=display_name,
                    created_at_in_seconds=1,
                    updated_at_in_seconds=1,
                )
                session.add(user)
                session.flush()
            by_role.setdefault(role, []).append(user.id)

        for role, user_ids in by_role.items():
            ensure_v1_role(
                session, tenant_id=tenant_id, role_name=role, user_ids=user_ids
            )
    session.commit()


def usernames() -> list[str]:
    return list(USERS)
