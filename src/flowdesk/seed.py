"""Tenants, accounts, roles and passwords.

Two companies carry the same four usernames on purpose: if tenant scoping ever
leaks, it shows up as the wrong person rather than a tidy error.

Four product roles, which is one more than the library has. The library's V1 RBAC
offers exactly `user`, `manager` and `admin`, and only `admin` may import a
process definition -- so both `admin` and `editor` have to hold the library's
admin role, and the difference between them (an editor publishes flows but does
not operate running instances) is enforced by this app. See FINDINGS.
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

from flowdesk import store
from flowdesk.auth import hash_password

TENANTS: dict[str, str] = {"northwind": "Northwind Traders", "initech": "Initech"}


class Account:
    """One seeded account: who they are, and what they may do."""

    __slots__ = ("username", "name", "title", "library_role", "capabilities")

    def __init__(
        self,
        username: str,
        name: str,
        title: str,
        library_role: str,
        capabilities: frozenset[str],
    ) -> None:
        self.username = username
        self.name = name
        self.title = title
        self.library_role = library_role
        self.capabilities = capabilities


#: App capabilities. The library covers starting flows and working on tasks; these
#: are the decisions it has no vocabulary for.
PUBLISH = "publish"      # add or update a flow
OPERATE = "operate"      # hold, release, cancel, retry a running instance
CONFIGURE = "configure"  # workspace settings
VIEW_ALL = "view_all"    # see other people's runs and the activity log

ACCOUNTS: dict[str, Account] = {
    "admin": Account(
        "admin",
        "Alex Admin",
        "Workspace Administrator",
        ROLE_ADMIN,
        frozenset({PUBLISH, OPERATE, CONFIGURE, VIEW_ALL}),
    ),
    "editor": Account(
        "editor",
        "Erin Editor",
        "Process Designer",
        # Publishing is admin-only in the library, so an editor must hold its
        # admin role. Withholding OPERATE is this app's doing.
        ROLE_ADMIN,
        frozenset({PUBLISH, VIEW_ALL}),
    ),
    "reviewer": Account(
        "reviewer",
        "Riya Reviewer",
        "Approver",
        ROLE_MANAGER,
        frozenset({VIEW_ALL}),
    ),
    "submitter": Account(
        "submitter",
        "Sam Submitter",
        "Team Member",
        ROLE_USER,
        frozenset(),
    ),
}

#: Demo passwords equal the username, and the sign-in screen says so.
DEFAULT_PASSWORD = dict.fromkeys(ACCOUNTS, "")


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
        for account in ACCOUNTS.values():
            user = session.scalar(
                select(UserModel).where(
                    UserModel.service == service_url(tenant_id),
                    UserModel.service_id == account.username,
                )
            )
            if user is None:
                user = UserModel(
                    username=account.username,
                    email=f"{account.username}@{tenant_id}.example.com",
                    service=service_url(tenant_id),
                    service_id=account.username,
                    display_name=account.name,
                    created_at_in_seconds=1,
                    updated_at_in_seconds=1,
                )
                session.add(user)
                session.flush()
            by_role.setdefault(account.library_role, []).append(user.id)

            if store.credential(session, tenant_id, account.username) is None:
                store.set_password(
                    session,
                    tenant_id=tenant_id,
                    username=account.username,
                    password_hash=hash_password(account.username),
                )

        for role, user_ids in by_role.items():
            ensure_v1_role(
                session, tenant_id=tenant_id, role_name=role, user_ids=user_ids
            )
    session.commit()


def account(username: str) -> Account:
    found = ACCOUNTS.get(username)
    if found is None:
        raise KeyError(username)
    return found


def usernames() -> list[str]:
    return list(ACCOUNTS)


def can(username: str, capability: str) -> bool:
    found = ACCOUNTS.get(username)
    return bool(found and capability in found.capabilities)
