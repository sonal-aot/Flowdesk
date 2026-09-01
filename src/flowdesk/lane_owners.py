"""Make lane membership match exactly what the publisher asked for.

The library syncs lane owners additively: publishing a flow adds the named users
to a lane's group and never removes anybody. So narrowing a lane on a later
publish silently does nothing, and a leaver cannot be taken off a lane at all.

There is no public API for group membership, so this reconciles the library's
own `user_group_assignment` rows -- adding what is missing and removing what is
no longer named.

Two things to know about how the library models lanes:

* A lane's group id is a hash of the lane *name* alone, so it is global. A lane
  called "Approver" is one group shared by every company, and by every flow that
  happens to use that name.
* Task assignment intersects that group with the tenant's own users, so work
  never crosses companies. This module therefore only ever touches rows for
  users of the publishing tenant, leaving other companies' membership alone.
"""

from __future__ import annotations

from m8flow_bpmn_core import api
from m8flow_bpmn_core.models.group import GroupModel
from m8flow_bpmn_core.models.user import UserModel
from m8flow_bpmn_core.models.user_group_assignment import UserGroupAssignmentModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from flowdesk.seed import service_url


def _ensure_group(session: Session, lane_name: str) -> GroupModel:
    """The library creates lane groups lazily; do the same so ids line up."""
    group_id = api.resolve_lane_assignment_id(lane_name)
    group = session.get(GroupModel, group_id)
    if group is None:
        group = GroupModel(
            id=group_id,
            name=lane_name,
            identifier=lane_name,
            source_is_open_id=False,
        )
        session.add(group)
        session.flush()
    return group


def apply(
    session: Session, *, tenant_id: str, lane_owners: dict[str, list[str]]
) -> dict[str, list[str]]:
    """Set each lane's membership to exactly the named users, for this tenant.

    Returns what each lane ended up with, so a caller can report it back.
    """
    people = {
        row.service_id: row
        for row in session.scalars(
            select(UserModel).where(UserModel.service == service_url(tenant_id))
        )
    }
    tenant_user_ids = {row.id for row in people.values()}
    applied: dict[str, list[str]] = {}

    for lane_name, usernames in lane_owners.items():
        group = _ensure_group(session, lane_name)
        wanted = {people[name].id for name in usernames if name in people}

        existing = list(
            session.scalars(
                select(UserGroupAssignmentModel).where(
                    UserGroupAssignmentModel.group_id == group.id,
                    UserGroupAssignmentModel.user_id.in_(tenant_user_ids or {0}),
                )
            )
        )
        for assignment in existing:
            if assignment.user_id not in wanted:
                session.delete(assignment)

        already = {
            assignment.user_id
            for assignment in existing
            if assignment.user_id in wanted
        }
        for user_id in sorted(wanted - already):
            session.add(
                UserGroupAssignmentModel(user_id=user_id, group_id=group.id)
            )

        applied[lane_name] = sorted(
            name for name in usernames if name in people
        )

    session.flush()
    return applied


def current(
    session: Session, *, tenant_id: str, lane_names: list[str]
) -> dict[str, list[str]]:
    """Who actually owns each lane in this tenant right now."""
    people = {
        row.id: row.service_id
        for row in session.scalars(
            select(UserModel).where(UserModel.service == service_url(tenant_id))
        )
    }
    out: dict[str, list[str]] = {}
    for lane_name in lane_names:
        group_id = api.resolve_lane_assignment_id(lane_name)
        member_ids = session.scalars(
            select(UserGroupAssignmentModel.user_id).where(
                UserGroupAssignmentModel.group_id == group_id
            )
        ).all()
        out[lane_name] = sorted(
            people[user_id] for user_id in member_ids if user_id in people
        )
    return out
