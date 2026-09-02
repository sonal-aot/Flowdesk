"""Flowdesk -- a workflow console on m8flow-bpmn-core.

Designers publish BPMN flows; everybody else picks one, starts it and works
through its tasks. Nothing about any particular flow is compiled in: the console
reads what it needs out of the diagram, and the library runs whatever it is
given.

Who may publish is not this app's decision -- `process_definition.import` is an
admin-only command in the library's V1 RBAC, so the engine enforces it.
"""

from __future__ import annotations

import contextlib
import json
import os
import time
from typing import Any

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from m8flow_bpmn_core import api
from m8flow_bpmn_core.errors import (
    AuthorizationError,
    InvalidStateError,
    NotFoundError,
    ValidationError,
)
from m8flow_bpmn_core.models.bpmn_process_definition import (
    BpmnProcessDefinitionModel,
)
from m8flow_bpmn_core.models.human_task import HumanTaskModel
from m8flow_bpmn_core.models.process_instance import ProcessInstanceModel
from m8flow_bpmn_core.models.human_task_user import HumanTaskUserModel
from m8flow_bpmn_core.models.user import UserModel
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from flowdesk import bpmn_inspect, lane_owners, store
from flowdesk.connectors import available_operations, service_tasks
from flowdesk.db import get_session, init_schema, session_factory
from flowdesk.errors import register_error_handlers
from flowdesk.identity import Caller, current_caller
from flowdesk.scheduler import scheduler_running
from flowdesk.auth import hash_password, issue_token, verify_password
from flowdesk.seed import (
    ACCOUNTS,
    CONFIGURE,
    OPERATE,
    PUBLISH,
    TENANTS,
    VIEW_ALL,
    account,
    can,
    can_start,
    seed,
    service_url,
    usernames,
)

# --------------------------------------------------------------------------- #
# Bodies
# --------------------------------------------------------------------------- #


class PublishIn(BaseModel):
    bpmn: str = Field(min_length=1)
    name: str | None = None
    dmn: str | None = None
    #: filename -> JSON Schema document, for the diagram's user-task forms
    forms: dict[str, Any] = Field(default_factory=dict)
    #: lane name -> usernames who pick up that lane's work
    lane_owners: dict[str, list[str]] = Field(default_factory=dict)


class LoginIn(BaseModel):
    company_id: str = Field(min_length=1)
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class ProfileIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    email: str | None = Field(default=None, min_length=3, max_length=255)


class PasswordIn(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=128)


class InspectIn(BaseModel):
    bpmn: str = Field(min_length=1)


class StartIn(BaseModel):
    summary: str | None = None


class CompleteIn(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


class ScheduleRetryIn(BaseModel):
    in_seconds: int = Field(default=60, ge=1, le=86_400)


def now() -> int:
    return int(time.time())


def require(caller: Caller, capability: str) -> None:
    """App-level permission.

    The library's V1 RBAC covers starting flows and working on tasks. It has no
    vocabulary for "may publish but may not operate", which is the difference
    between this product's admin and editor, so those checks live here.
    """
    if not can(caller.username, capability):
        raise AuthorizationError(
            f"{caller.username} may not {capability} in {caller.tenant_id}"
        )


# --------------------------------------------------------------------------- #
# Startup
# --------------------------------------------------------------------------- #


def publish(
    session: Session,
    *,
    tenant_id: str,
    actor_user_id: int,
    body: PublishIn,
) -> tuple[BpmnProcessDefinitionModel, bpmn_inspect.Flow]:
    """Store a flow's files and import its definition.

    ``actor_user_id`` is who the library authorizes, so it is always the real
    caller -- never a service account.
    """
    flow = bpmn_inspect.inspect(body.bpmn)
    if flow.errors:
        raise ValidationError(" ".join(flow.errors))

    problems: list[str] = []

    missing = [
        name
        for name in flow.form_files
        if name not in body.forms and not name.endswith("uischema.json")
    ]
    if missing:
        problems.append(
            "This diagram asks for form schemas that were not supplied: "
            + ", ".join(missing)
        )

    assigned = {
        lane: sorted(set(body.lane_owners.get(lane) or [])) for lane in flow.lanes
    }
    unknown = sorted(
        {
            person
            for owners in assigned.values()
            for person in owners
            if person not in ACCOUNTS
        }
    )
    if unknown:
        problems.append(f"No such people: {', '.join(unknown)}")

    unassigned = sorted(lane for lane, owners in assigned.items() if not owners)
    if unassigned:
        problems.append(
            "Every lane needs somebody to pick up its work. Nobody is assigned "
            f"to: {', '.join(unassigned)}"
        )

    if problems:
        raise ValidationError(" ".join(problems))

    definition = api.execute_command(
        session,
        api.ImportBpmnProcessDefinitionCommand(
            tenant_id=tenant_id,
            bpmn_identifier=flow.process_id,
            user_id=actor_user_id,
            bpmn_name=body.name or flow.name,
            source_bpmn_xml=body.bpmn,
            source_dmn_xml=body.dmn,
            properties_json={
                "lane_owners": assigned,
                "display_name": body.name or flow.name,
            },
            created_at_in_seconds=now(),
            updated_at_in_seconds=now(),
        ),
    )

    # The library only ever adds lane members, so make the groups match exactly
    # what was asked for -- otherwise narrowing a lane silently does nothing.
    lane_owners.apply(session, tenant_id=tenant_id, lane_owners=assigned)

    store.save_asset(
        session,
        tenant_id=tenant_id,
        process_id=flow.process_id,
        filename="process.bpmn",
        kind="bpmn",
        content=body.bpmn,
    )
    if body.dmn:
        store.save_asset(
            session,
            tenant_id=tenant_id,
            process_id=flow.process_id,
            filename="decisions.dmn",
            kind="dmn",
            content=body.dmn,
        )
    for filename, schema in body.forms.items():
        store.save_asset(
            session,
            tenant_id=tenant_id,
            process_id=flow.process_id,
            filename=filename,
            kind="form",
            content=json.dumps(schema),
        )
    return definition, flow


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    init_schema()
    session = session_factory()()
    try:
        seed(session)
        session.commit()
    finally:
        session.close()
    async with scheduler_running():
        yield


app = FastAPI(title="Flowdesk", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get(
        "FLOWDESK_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
register_error_handlers(app)

CallerDep = Depends(current_caller)
SessionDep = Depends(get_session)


# --------------------------------------------------------------------------- #
# Shared reads
# --------------------------------------------------------------------------- #


def people(session: Session, tenant_id: str) -> dict[int, UserModel]:
    rows = session.scalars(
        select(UserModel).where(UserModel.service == service_url(tenant_id))
    ).all()
    return {row.id: row for row in rows}


def display_name(directory: dict[int, UserModel], user_id: int | None) -> str | None:
    person = directory.get(user_id) if user_id is not None else None
    return person.display_name or person.username if person else None


def definitions_for(
    session: Session, tenant_id: str, process_id: str | None = None
) -> list[BpmnProcessDefinitionModel]:
    """The library has no read query for definitions, so go to the model (#6)."""
    statement = select(BpmnProcessDefinitionModel).where(
        BpmnProcessDefinitionModel.m8f_tenant_id == tenant_id
    )
    if process_id is not None:
        statement = statement.where(
            BpmnProcessDefinitionModel.bpmn_identifier == process_id
        )
    return list(
        session.scalars(statement.order_by(BpmnProcessDefinitionModel.id.desc()))
    )


def newest_definition(
    session: Session, tenant_id: str, process_id: str
) -> BpmnProcessDefinitionModel:
    found = definitions_for(session, tenant_id, process_id)
    if not found:
        raise NotFoundError(f"No flow is published with the id {process_id!r}")
    return found[0]


def flow_summary(
    definition: BpmnProcessDefinitionModel,
    session: Session | None = None,
) -> dict[str, Any]:
    """A flow as the console shows it.

    When a session is given, lane owners are read back from the groups that
    actually decide assignment rather than from what was recorded at publish
    time -- so the screen cannot disagree with reality.
    """
    properties = definition.properties_json or {}
    flow = bpmn_inspect.inspect(definition.source_bpmn_xml or "")
    owners = properties.get("lane_owners") or {}
    if session is not None and flow.lanes:
        owners = lane_owners.current(
            session,
            tenant_id=definition.m8f_tenant_id,
            lane_names=list(flow.lanes),
        )
    return {
        "process_id": definition.bpmn_identifier,
        "name": properties.get("display_name") or definition.bpmn_name or flow.name,
        "version_id": definition.id,
        "lanes": list(flow.lanes),
        "lane_owners": owners,
        "steps": [
            {"name": task.name, "lane": task.lane, "has_form": bool(task.form_schema)}
            for task in flow.user_tasks
        ],
        "decisions": list(flow.decisions),
        "service_operations": list(flow.service_operations),
        "timers": list(flow.timers),
        "gateways": sorted(set(flow.gateways)),
        "script_tasks": flow.script_tasks,
        "has_dmn": bool(definition.source_dmn_xml),
    }


# --------------------------------------------------------------------------- #
# Identity
# --------------------------------------------------------------------------- #


@app.get("/health", include_in_schema=False)
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/companies")
def companies() -> list[dict[str, str]]:
    """For the sign-in screen's company picker."""
    return [
        {"company_id": tenant_id, "company": name}
        for tenant_id, name in TENANTS.items()
    ]


@app.post("/auth/login")
def login(body: LoginIn, session: Session = SessionDep) -> dict[str, Any]:
    if body.company_id not in TENANTS:
        raise AuthorizationError("Unknown company, username or password")
    stored = store.credential(session, body.company_id, body.username)
    if stored is None or not verify_password(body.password, stored.password_hash):
        # One message for every failure, so it cannot be used to enumerate users.
        raise AuthorizationError("Unknown company, username or password")

    token, expires_at = issue_token(
        tenant_id=body.company_id,
        username=body.username,
        password_hash=stored.password_hash,
    )
    return {"token": token, "expires_at": expires_at}


@app.get("/me")
def me(caller: Caller = CallerDep, session: Session = SessionDep) -> dict[str, Any]:
    directory = people(session, caller.tenant_id)
    person = directory[caller.user_id]
    entry = account(caller.username)
    open_tasks = api.execute_query(
        session,
        api.GetPendingTasksQuery(tenant_id=caller.tenant_id, user_id=caller.user_id),
    )
    return {
        "name": person.display_name or entry.name,
        "username": caller.username,
        "email": person.email or "",
        "title": entry.title,
        "role": caller.username,
        "library_role": entry.library_role,
        "company": TENANTS[caller.tenant_id],
        "company_id": caller.tenant_id,
        "can_start": can_start(caller.username),
        "can_publish": can(caller.username, PUBLISH),
        "can_operate": can(caller.username, OPERATE),
        "can_configure": can(caller.username, CONFIGURE),
        "can_view_all": can(caller.username, VIEW_ALL),
        "open_tasks": len(open_tasks),
        "people": [
            {"username": entry.username, "name": entry.name}
            for entry in ACCOUNTS.values()
        ],
    }


# --------------------------------------------------------------------------- #
# Flows
# --------------------------------------------------------------------------- #


@app.patch("/me")
def update_profile(
    body: ProfileIn,
    caller: Caller = CallerDep,
    session: Session = SessionDep,
) -> dict[str, Any]:
    """Change your own display name or email address.

    These live on the library's `user` table, and the library has no user
    management API, so the app writes the model directly. Only the two display
    fields are editable: `service` and `service_id` are what the library parses
    to decide tenant membership, so letting anybody edit those would let them
    move themselves between companies. See FINDINGS #8.
    """
    person = session.get(UserModel, caller.user_id)
    if person is None:  # pragma: no cover - the caller was just resolved
        raise NotFoundError("That account no longer exists")

    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise ValidationError("Your name cannot be blank")
        person.display_name = name

    if body.email is not None:
        email = body.email.strip()
        if "@" not in email or email.startswith("@") or email.endswith("@"):
            raise ValidationError("That does not look like an email address")
        person.email = email

    person.updated_at_in_seconds = now()
    session.flush()
    return {
        "name": person.display_name,
        "email": person.email or "",
        "username": caller.username,
    }


@app.post("/me/password")
def change_password(
    body: PasswordIn,
    caller: Caller = CallerDep,
    session: Session = SessionDep,
) -> dict[str, Any]:
    """Change your own password, proving you know the current one.

    Every token carries a fingerprint of the password it was issued against, so
    changing it signs out every other session. A fresh token comes back so the
    caller doing the changing stays signed in.
    """
    stored = store.credential(session, caller.tenant_id, caller.username)
    if stored is None or not verify_password(
        body.current_password, stored.password_hash
    ):
        raise AuthorizationError("That is not your current password")
    if body.new_password == body.current_password:
        raise ValidationError("The new password must be different")

    stored.password_hash = hash_password(body.new_password)
    session.flush()
    token, expires_at = issue_token(
        tenant_id=caller.tenant_id,
        username=caller.username,
        password_hash=stored.password_hash,
    )
    return {"token": token, "expires_at": expires_at}


@app.get("/operations")
def operations(caller: Caller = CallerDep) -> list[dict[str, str]]:
    """The service-task operations a diagram may call here."""
    return available_operations()


@app.post("/inspect")
def inspect_bpmn(body: InspectIn, caller: Caller = CallerDep) -> dict[str, Any]:
    """Read a diagram without publishing it, so the designer can check it first."""
    require(caller, PUBLISH)
    flow = bpmn_inspect.inspect(body.bpmn)
    known = {operation["operation_id"] for operation in available_operations()}
    return {
        "process_id": flow.process_id,
        "name": flow.name,
        "lanes": list(flow.lanes),
        "steps": [
            {
                "name": task.name,
                "lane": task.lane,
                "form_schema": task.form_schema,
            }
            for task in flow.user_tasks
        ],
        "decisions": list(flow.decisions),
        "service_operations": list(flow.service_operations),
        "unknown_operations": sorted(set(flow.service_operations) - known),
        "timers": list(flow.timers),
        "gateways": sorted(set(flow.gateways)),
        "script_tasks": flow.script_tasks,
        "form_files": list(flow.form_files),
        "problems": list(flow.errors),
        "people": usernames(),
    }


@app.post("/flows", status_code=201)
def publish_flow(
    body: PublishIn,
    caller: Caller = CallerDep,
    session: Session = SessionDep,
) -> dict[str, Any]:
    """Publish a flow. Designers only.

    The library enforces this too -- `process_definition.import` is admin-only --
    but its check runs during the import, after the diagram has been parsed. A
    caller who may not publish should not learn whether their file was valid, so
    the permission is settled first.
    """
    require(caller, PUBLISH)
    definition, _flow = publish(
        session,
        tenant_id=caller.tenant_id,
        actor_user_id=caller.user_id,
        body=body,
    )
    session.flush()
    return flow_summary(definition, session)


@app.get("/flows")
def list_flows(
    caller: Caller = CallerDep, session: Session = SessionDep
) -> list[dict[str, Any]]:
    """Every flow anybody may start, newest version of each."""
    seen: dict[str, dict[str, Any]] = {}
    for definition in definitions_for(session, caller.tenant_id):
        if definition.bpmn_identifier in seen:
            seen[definition.bpmn_identifier]["versions"] += 1
            continue
        summary = flow_summary(definition, session)
        summary["versions"] = 1
        seen[definition.bpmn_identifier] = summary
    return sorted(seen.values(), key=lambda row: row["name"].lower())


@app.get("/flows/{process_id}")
def get_flow(
    process_id: str,
    caller: Caller = CallerDep,
    session: Session = SessionDep,
) -> dict[str, Any]:
    definition = newest_definition(session, caller.tenant_id, process_id)
    summary = flow_summary(definition, session)
    summary["versions"] = [
        {"version_id": row.id, "published_at": row.created_at_in_seconds}
        for row in definitions_for(session, caller.tenant_id, process_id)
    ]
    summary["files"] = [
        {"filename": item.filename, "kind": item.kind, "bytes": len(item.content)}
        for item in store.assets_for(session, caller.tenant_id, process_id)
    ]
    return summary


@app.get("/flows/{process_id}/diagram")
def get_diagram(
    process_id: str,
    caller: Caller = CallerDep,
    session: Session = SessionDep,
) -> dict[str, str]:
    definition = newest_definition(session, caller.tenant_id, process_id)
    return {"bpmn": definition.source_bpmn_xml or ""}


@app.post("/flows/{process_id}/start", status_code=201)
def start_flow(
    process_id: str,
    body: StartIn | None = None,
    caller: Caller = CallerDep,
    session: Session = SessionDep,
) -> dict[str, Any]:
    """Start an instance of a published flow."""
    definition = newest_definition(session, caller.tenant_id, process_id)
    summary = (body.summary if body else None) or (
        (definition.properties_json or {}).get("display_name")
        or definition.bpmn_name
        or process_id
    )
    with service_tasks(session, caller.tenant_id):
        instance = api.execute_command(
            session,
            api.InitializeProcessInstanceFromDefinitionCommand(
                tenant_id=caller.tenant_id,
                bpmn_process_definition_id=definition.id,
                process_initiator_id=caller.user_id,
                summary=summary[:255],
                process_version=1,
                started_at_in_seconds=now(),
                bpmn_process_id=process_id,
            ),
        )
    session.flush()
    return {
        "id": instance.id,
        "status": str(instance.status),
        "process_id": process_id,
        "summary": instance.summary,
    }


# --------------------------------------------------------------------------- #
# Instances
# --------------------------------------------------------------------------- #


def instance_row(
    instance: Any,
    directory: dict[int, UserModel],
    pending: dict[int, list[Any]],
    assignees: dict[int, list[str]] | None = None,
) -> dict[str, Any]:
    waiting = pending.get(instance.id, [])
    return {
        "id": instance.id,
        "process_id": instance.process_model_identifier,
        "summary": instance.summary,
        "status": str(instance.status),
        "started_by": display_name(directory, instance.process_initiator_id),
        "waiting_on": sorted(
            {task.lane_name or task.task_title or task.task_name for task in waiting}
        ),
        "waiting_step": ", ".join(
            sorted({task.task_title or task.task_name for task in waiting})
        ),
        "waiting_people": sorted(
            {
                name
                for task in waiting
                for name in (assignees or {}).get(task.id, [])
            }
        ),
        "open_steps": len(waiting),
    }


def assignees_by_task(
    session: Session, tenant_id: str, directory: dict[int, UserModel]
) -> dict[int, list[str]]:
    """human task id -> the people who may act on it, from `human_task_user`."""
    out: dict[int, list[str]] = {}
    for assignment in session.scalars(
        select(HumanTaskUserModel).where(
            HumanTaskUserModel.m8f_tenant_id == tenant_id
        )
    ):
        name = display_name(directory, assignment.user_id)
        if name is not None:
            out.setdefault(assignment.human_task_id, []).append(name)
    return out


@app.get("/instances")
def list_instances(
    scope: str = "all",
    status: str | None = None,
    caller: Caller = CallerDep,
    session: Session = SessionDep,
) -> list[dict[str, Any]]:
    instances = api.execute_query(
        session,
        api.ListProcessInstancesQuery(tenant_id=caller.tenant_id, status=status),
    )
    if scope == "mine" or not can(caller.username, VIEW_ALL):
        instances = [
            row for row in instances if row.process_initiator_id == caller.user_id
        ]
    directory = people(session, caller.tenant_id)
    pending: dict[int, list[Any]] = {}
    for task in api.execute_query(
        session, api.GetPendingTasksQuery(tenant_id=caller.tenant_id)
    ):
        pending.setdefault(task.process_instance_id, []).append(task)
    assignees = assignees_by_task(session, caller.tenant_id, directory)
    rows = [instance_row(row, directory, pending, assignees) for row in instances]
    return sorted(rows, key=lambda row: row["id"], reverse=True)


@app.get("/instances/{instance_id}")
def get_instance(
    instance_id: int,
    caller: Caller = CallerDep,
    session: Session = SessionDep,
) -> dict[str, Any]:
    instance = api.execute_query(
        session,
        api.GetProcessInstanceQuery(
            tenant_id=caller.tenant_id, process_instance_id=instance_id
        ),
    )
    directory = people(session, caller.tenant_id)
    pending: dict[int, list[Any]] = {}
    for task in api.execute_query(
        session, api.GetPendingTasksQuery(tenant_id=caller.tenant_id)
    ):
        pending.setdefault(task.process_instance_id, []).append(task)

    row = instance_row(
        instance,
        directory,
        pending,
        assignees_by_task(session, caller.tenant_id, directory),
    )
    row["data"] = {
        item.key: item.value
        for item in api.execute_query(
            session,
            api.GetProcessInstanceMetadataQuery(
                tenant_id=caller.tenant_id, process_instance_id=instance_id
            ),
        )
    }
    row["events"] = [
        {
            "event": str(event.event_type),
            "by": display_name(directory, event.user_id),
            "at": time.strftime(
                "%d %b %Y, %H:%M:%S", time.localtime(float(event.timestamp))
            ),
        }
        for event in api.execute_query(
            session,
            api.GetProcessInstanceEventsQuery(
                tenant_id=caller.tenant_id, process_instance_id=instance_id
            ),
        )
    ]
    row["progress"] = progress_for(
        session,
        tenant_id=caller.tenant_id,
        instance=instance,
        directory=directory,
    )
    row["next_action"] = next_action_line(row["progress"], str(instance.status))
    row["allowed_actions"] = allowed_actions(instance)
    row["no_actions_reason"] = (
        None if row["allowed_actions"] else why_no_actions(str(instance.status))
    )
    row["activity"] = [
        {
            "operation_id": call.operation_id,
            "outcome": call.outcome,
            "detail": call.detail,
            "at": time.strftime(
                "%d %b %Y, %H:%M:%S", time.localtime(call.created_at_in_seconds)
            ),
        }
        for call in session.scalars(
            select(store.ConnectorCall)
            .where(
                store.ConnectorCall.tenant_id == caller.tenant_id,
                store.ConnectorCall.process_instance_id == instance_id,
            )
            .order_by(store.ConnectorCall.id)
        )
    ]
    return row


#: What each lifecycle action needs to be true, taken from the library's own
#: preconditions rather than guessed:
#:   suspend   -- not terminal, not already suspended  (process_instances.py:264)
#:   resume    -- suspended only                                        (:361)
#:   terminate -- not terminal                                          (:521)
#:   retry     -- errored only                                          (:407)
ACTION_LABELS = {
    "hold": "put on hold",
    "release": "released",
    "cancel": "cancelled",
    "retry": "retried",
}


def allowed_actions(instance: Any) -> list[str]:
    """Which lifecycle actions the engine would actually accept right now."""
    status = str(instance.status)
    terminal = status in ProcessInstanceModel.terminal_statuses()
    actions: list[str] = []
    if not terminal and status != "suspended":
        actions.append("hold")
    if status == "suspended":
        actions.append("release")
    if not terminal:
        actions.append("cancel")
    if status == "error":
        actions.append("retry")
    return actions


def why_no_actions(status: str) -> str:
    return {
        "complete": "This run has finished, so there is nothing to operate.",
        "terminated": "This run was cancelled, so there is nothing to operate.",
    }.get(status, "There is nothing to operate on this run right now.")


WHY_ASSIGNED = {
    "lane_owner": "owns this lane",
    "lane_assignment": "assigned to this lane",
    "process_initiator": "started the run",
    "manual": "added by hand",
    "guest": "guest access",
}


def progress_for(
    session: Session,
    *,
    tenant_id: str,
    instance: Any,
    directory: dict[int, UserModel],
) -> list[dict[str, Any]]:
    """Every step of the flow, in order, with where the run has got to.

    The library only knows about steps it has already created -- a step the run
    has not reached yet has no row anywhere. So the shape comes from the stored
    diagram and is matched against the human tasks that exist:

    * matched and completed  -> done, by whom, when
    * matched and open       -> waiting, on exactly these people
    * unmatched              -> still to come, or never needed if the run has
                                already finished down another branch
    """
    definition = newest_definition(session, tenant_id, instance.process_model_identifier)
    flow = bpmn_inspect.inspect(definition.source_bpmn_xml or "")

    rows = list(
        session.scalars(
            select(HumanTaskModel)
            .where(
                HumanTaskModel.m8f_tenant_id == tenant_id,
                HumanTaskModel.process_instance_id == instance.id,
            )
            .order_by(HumanTaskModel.id)
        )
    )
    by_element: dict[str, HumanTaskModel] = {}
    for row in rows:
        by_element[row.task_name] = row  # the latest wins if a step repeats

    finished = str(instance.status) in {"complete", "terminated"}
    out: list[dict[str, Any]] = []

    for step in flow.user_tasks:
        task = by_element.get(step.element_id)
        entry: dict[str, Any] = {
            "name": step.name,
            "lane": step.lane,
            "task_id": task.id if task is not None else None,
            "by": None,
            "at": None,
            "people": [],
        }
        if task is None:
            entry["state"] = "not_needed" if finished else "upcoming"
            out.append(entry)
            continue

        when = task.updated_at_in_seconds or task.created_at_in_seconds
        entry["at"] = (
            time.strftime("%d %b %Y, %H:%M", time.localtime(when)) if when else None
        )
        if task.completed:
            entry["state"] = "done"
            entry["by"] = display_name(directory, task.completed_by_user_id)
        else:
            entry["state"] = "waiting"
            entry["people"] = [
                {
                    "name": display_name(directory, assignment.user_id)
                    or str(assignment.user_id),
                    "why": WHY_ASSIGNED.get(
                        assignment.added_by or "", assignment.added_by or ""
                    ),
                }
                for assignment in session.scalars(
                    select(HumanTaskUserModel)
                    .where(
                        HumanTaskUserModel.m8f_tenant_id == tenant_id,
                        HumanTaskUserModel.human_task_id == task.id,
                    )
                    .order_by(HumanTaskUserModel.id)
                )
                if assignment.user_id in directory
            ]
        out.append(entry)
    return out


def next_action_line(progress: list[dict[str, Any]], status: str) -> str:
    """One sentence for the top of the screen."""
    waiting = [step for step in progress if step["state"] == "waiting"]
    if not waiting:
        return {
            "complete": "Finished.",
            "terminated": "Cancelled.",
            "suspended": "On hold — nobody can act until it is released.",
            "error": "Stopped with an error.",
        }.get(status, "Nothing is waiting on a person.")

    parts = []
    for step in waiting:
        people = ", ".join(person["name"] for person in step["people"]) or (
            f"anyone in {step['lane']}" if step["lane"] else "anyone"
        )
        parts.append(f"{step['name']} — {people}")
    if len(parts) == 1:
        return f"Waiting on {parts[0]}"
    return "Waiting on " + "; ".join(parts)


LIFECYCLE = {
    "hold": api.SuspendProcessInstanceCommand,
    "release": api.ResumeProcessInstanceCommand,
    "cancel": api.TerminateProcessInstanceCommand,
    "retry": api.RetryProcessInstanceCommand,
}


@app.post("/instances/{instance_id}/{action}")
def lifecycle(
    instance_id: int,
    action: str,
    caller: Caller = CallerDep,
    session: Session = SessionDep,
) -> dict[str, Any]:
    """hold / release / cancel / retry. Needs the operate capability."""
    require(caller, OPERATE)
    command_type = LIFECYCLE.get(action)
    if command_type is None:
        raise NotFoundError(f"There is no '{action}' action")

    # The engine would refuse this anyway; saying so plainly beats a generic
    # conflict, and it keeps the API honest if a screen is out of date.
    current = api.execute_query(
        session,
        api.GetProcessInstanceQuery(
            tenant_id=caller.tenant_id, process_instance_id=instance_id
        ),
    )
    if action not in allowed_actions(current):
        raise InvalidStateError(
            f"This run is {str(current.status).replace('_', ' ')}, so it cannot be "
            f"{ACTION_LABELS[action]}."
        )
    with service_tasks(session, caller.tenant_id):
        instance = api.execute_command(
            session,
            command_type(
                tenant_id=caller.tenant_id,
                process_instance_id=instance_id,
                user_id=caller.user_id,
            ),
        )
    return {"id": instance.id, "status": str(instance.status)}


@app.post("/instances/{instance_id}/schedule-retry")
def schedule_retry(
    instance_id: int,
    body: ScheduleRetryIn,
    caller: Caller = CallerDep,
    session: Session = SessionDep,
) -> dict[str, Any]:
    """Ask the scheduler to retry an errored instance later."""
    require(caller, OPERATE)
    instance = api.execute_command(
        session,
        api.ScheduleProcessInstanceRetryCommand(
            tenant_id=caller.tenant_id,
            process_instance_id=instance_id,
            user_id=caller.user_id,
            retry_at_in_seconds=now() + body.in_seconds,
        ),
    )
    return {
        "id": instance.id,
        "status": str(instance.status),
        "retry_in_seconds": body.in_seconds,
    }


# --------------------------------------------------------------------------- #
# Tasks
# --------------------------------------------------------------------------- #


def form_for(
    session: Session, tenant_id: str, process_id: str, task_name: str
) -> dict[str, Any] | None:
    """The JSON Schema a task wants, if the diagram named one and it was supplied.

    The library records a `form_file_name` column but never fills it in, so the
    reference is read out of the stored diagram instead.
    """
    definition = newest_definition(session, tenant_id, process_id)
    flow = bpmn_inspect.inspect(definition.source_bpmn_xml or "")
    wanted = next(
        (
            task.form_schema
            for task in flow.user_tasks
            if task.element_id == task_name or task.name == task_name
        ),
        None,
    )
    if not wanted:
        return None
    found = store.asset(session, tenant_id, process_id, wanted)
    if found is None:
        return None
    try:
        return json.loads(found.content)
    except ValueError:  # pragma: no cover - stored by us as JSON
        return None


@app.get("/tasks")
def list_tasks(
    mine: bool = True,
    caller: Caller = CallerDep,
    session: Session = SessionDep,
) -> list[dict[str, Any]]:
    """Your worklist, or everything open in the company."""
    tasks = api.execute_query(
        session,
        api.GetPendingTasksQuery(
            tenant_id=caller.tenant_id,
            user_id=caller.user_id if mine else None,
        ),
    )
    directory = people(session, caller.tenant_id)
    out: list[dict[str, Any]] = []
    for task in tasks:
        instance = api.execute_query(
            session,
            api.GetProcessInstanceQuery(
                tenant_id=caller.tenant_id,
                process_instance_id=task.process_instance_id,
            ),
        )
        out.append(
            {
                "id": task.id,
                "name": task.task_title or task.task_name,
                "lane": task.lane_name,
                "instance_id": task.process_instance_id,
                "process_id": instance.process_model_identifier,
                "flow": task.process_model_display_name,
                "summary": instance.summary,
                "claimed_by": display_name(directory, task.actual_owner_id),
            }
        )
    return out


@app.get("/tasks/{task_id}")
def get_task(
    task_id: int,
    caller: Caller = CallerDep,
    session: Session = SessionDep,
) -> dict[str, Any]:
    """One task, with its form and whatever the flow already knows."""
    task = session.get(HumanTaskModel, task_id)
    if task is None or task.m8f_tenant_id != caller.tenant_id:
        raise NotFoundError(f"There is no task {task_id}")

    instance = api.execute_query(
        session,
        api.GetProcessInstanceQuery(
            tenant_id=caller.tenant_id, process_instance_id=task.process_instance_id
        ),
    )
    directory = people(session, caller.tenant_id)
    data = {
        item.key: item.value
        for item in api.execute_query(
            session,
            api.GetProcessInstanceMetadataQuery(
                tenant_id=caller.tenant_id,
                process_instance_id=task.process_instance_id,
            ),
        )
    }
    return {
        "id": task.id,
        "name": task.task_title or task.task_name,
        "element_id": task.task_name,
        "lane": task.lane_name,
        "instance_id": task.process_instance_id,
        "process_id": instance.process_model_identifier,
        "summary": instance.summary,
        "claimed_by": display_name(directory, task.actual_owner_id),
        "completed": bool(task.completed),
        "form": form_for(
            session,
            caller.tenant_id,
            instance.process_model_identifier,
            task.task_name,
        ),
        "known_data": data,
    }


@app.post("/tasks/{task_id}/claim")
def claim_task(
    task_id: int,
    caller: Caller = CallerDep,
    session: Session = SessionDep,
) -> dict[str, Any]:
    task = api.execute_command(
        session,
        api.ClaimTaskCommand(
            tenant_id=caller.tenant_id, human_task_id=task_id, user_id=caller.user_id
        ),
    )
    return {"id": task.id, "claimed_by": caller.username}


@app.post("/tasks/{task_id}/complete")
def complete_task(
    task_id: int,
    body: CompleteIn,
    caller: Caller = CallerDep,
    session: Session = SessionDep,
) -> dict[str, Any]:
    """Submit a task's form.

    Claiming first is the engine's bookkeeping, not something a person should
    have to do twice, so it happens here.
    """
    with contextlib.suppress(Exception):
        api.execute_command(
            session,
            api.ClaimTaskCommand(
                tenant_id=caller.tenant_id,
                human_task_id=task_id,
                user_id=caller.user_id,
            ),
        )
    with service_tasks(session, caller.tenant_id):
        task = api.execute_command(
            session,
            api.CompleteTaskCommand(
                tenant_id=caller.tenant_id,
                human_task_id=task_id,
                user_id=caller.user_id,
                completed_at_in_seconds=now(),
                task_payload=body.payload,
            ),
        )
    instance = api.execute_query(
        session,
        api.GetProcessInstanceQuery(
            tenant_id=caller.tenant_id, process_instance_id=task.process_instance_id
        ),
    )
    return {
        "id": task.id,
        "instance_id": task.process_instance_id,
        "instance_status": str(instance.status),
    }


@app.get("/activity")
def activity(
    caller: Caller = CallerDep, session: Session = SessionDep
) -> list[dict[str, Any]]:
    """Everything the connectors did, newest first."""
    require(caller, VIEW_ALL)
    return [
        {
            "id": call.id,
            "instance_id": call.process_instance_id,
            "operation_id": call.operation_id,
            "parameters": call.parameters,
            "outcome": call.outcome,
            "detail": call.detail,
            "at": time.strftime(
                "%d %b %Y, %H:%M:%S", time.localtime(call.created_at_in_seconds)
            ),
        }
        for call in session.scalars(
            select(store.ConnectorCall)
            .where(store.ConnectorCall.tenant_id == caller.tenant_id)
            .order_by(store.ConnectorCall.id.desc())
        )
    ]


def run() -> None:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8020)
