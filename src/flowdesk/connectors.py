"""Service-task connectors, registered on the library's in-process seam.

Two are shipped, both configuration-free so any uploaded diagram can use them:

* ``log/Write`` -- records its parameters in the activity log. Useful for
  tracing what a flow computed at a given point.
* ``http/GetRequest`` and ``http/PostRequest`` -- real outbound HTTP over the
  standard library.

The operation ids follow m8flow's ``<connector>/<command>`` convention, so a
diagram written against the connector-proxy catalogue keeps working.

Every call is logged whether it succeeded or not. Failures are buffered rather
than written immediately: a service task runs inside the caller's transaction,
so writing the record there would roll back with the failure, and writing it
from a second connection deadlocks against the still-open transaction.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from m8flow_bpmn_core import api
from m8flow_bpmn_core.errors import ServiceTaskExecutionError
from sqlalchemy.orm import Session

from flowdesk import store

HTTP_TIMEOUT = 10.0
MAX_BODY = 4000


def _readable(parameters: dict[str, Any]) -> str:
    try:
        return json.dumps(parameters, default=str)[:2000]
    except Exception:  # noqa: BLE001 - logging must never be the thing that fails
        return str(parameters)[:2000]


@dataclass
class _Recording:
    """Shared bookkeeping: log successes now, hold failures for later."""

    session: Session
    tenant_id: str
    failures: list[dict[str, Any]] = field(default_factory=list)

    def ok(self, request: api.ServiceTaskRequest, detail: str) -> None:
        store.log_call(
            self.session,
            tenant_id=self.tenant_id,
            process_instance_id=(
                request.context.process_instance_id if request.context else None
            ),
            operation_id=request.operation_id,
            parameters=_readable(dict(request.parameters or {})),
            outcome="ok",
            detail=detail[:MAX_BODY],
        )

    def failed(self, request: api.ServiceTaskRequest, detail: str) -> None:
        self.failures.append(
            {
                "tenant_id": self.tenant_id,
                "process_instance_id": (
                    request.context.process_instance_id if request.context else None
                ),
                "operation_id": request.operation_id,
                "parameters": _readable(dict(request.parameters or {})),
                "outcome": "failed",
                "detail": detail[:MAX_BODY],
            }
        )


@dataclass
class LogConnector:
    recording: _Recording
    connector_key: str = "log"

    def list_commands(self) -> tuple[api.ServiceTaskCommandDefinition, ...]:
        return tuple(
            api.ServiceTaskCommandDefinition(
                connector_key="log",
                command_name=command,
                display_name=f"Log ({command})",
                description="Records the task's parameters in the activity log.",
            )
            for command in ("Write", "Trace")
        )

    def execute(self, request: api.ServiceTaskRequest) -> api.ServiceTaskResult:
        parameters = dict(request.parameters or {})
        self.recording.ok(request, f"logged {len(parameters)} parameter(s)")
        return api.ServiceTaskResult(payload={"logged": True, **parameters})


@dataclass
class HttpConnector:
    recording: _Recording
    connector_key: str = "http"

    def list_commands(self) -> tuple[api.ServiceTaskCommandDefinition, ...]:
        return tuple(
            api.ServiceTaskCommandDefinition(
                connector_key="http",
                command_name=command,
                display_name=f"HTTP {command}",
                description="Calls a URL and returns the status and body.",
                parameters=(
                    api.ServiceTaskParameterDefinition(
                        name="url", parameter_type="str", required=True
                    ),
                    api.ServiceTaskParameterDefinition(
                        name="headers", parameter_type="any"
                    ),
                    api.ServiceTaskParameterDefinition(
                        name="body", parameter_type="any"
                    ),
                ),
            )
            for command in ("GetRequest", "PostRequest")
        )

    def execute(self, request: api.ServiceTaskRequest) -> api.ServiceTaskResult:
        parameters = dict(request.parameters or {})
        url = str(parameters.get("url") or "")
        if not url.startswith(("http://", "https://")):
            self.recording.failed(request, f"refused a non-HTTP url: {url!r}")
            raise ServiceTaskExecutionError(
                f"{request.operation_id} needs an http:// or https:// url"
            )

        method = "POST" if request.command_name == "PostRequest" else "GET"
        payload = parameters.get("body")
        data = None
        if method == "POST" and payload is not None:
            data = (
                payload.encode()
                if isinstance(payload, str)
                else json.dumps(payload, default=str).encode()
            )

        outbound = urllib.request.Request(url, data=data, method=method)
        outbound.add_header("Content-Type", "application/json")
        for key, value in (parameters.get("headers") or {}).items():
            outbound.add_header(str(key), str(value))

        try:
            with urllib.request.urlopen(outbound, timeout=HTTP_TIMEOUT) as response:
                body = response.read(MAX_BODY).decode("utf-8", "replace")
                status = response.status
        except urllib.error.HTTPError as exc:
            body = exc.read(MAX_BODY).decode("utf-8", "replace")
            status = exc.code
        except Exception as exc:  # noqa: BLE001 - reported to the workflow
            self.recording.failed(request, f"{type(exc).__name__}: {exc}")
            raise ServiceTaskExecutionError(
                f"{method} {url} failed: {exc}"
            ) from exc

        self.recording.ok(request, f"{method} {url} -> {status}")
        parsed: Any = body
        try:
            parsed = json.loads(body)
        except ValueError:
            pass
        return api.ServiceTaskResult(payload={"status": status, "body": parsed})


@contextmanager
def service_tasks(session: Session, tenant_id: str) -> Iterator[_Recording]:
    """Install the connectors for the duration of a workflow call."""
    recording = _Recording(session=session, tenant_id=tenant_id)
    registry = api.ServiceTaskRegistry(
        [LogConnector(recording=recording), HttpConnector(recording=recording)]
    )
    try:
        with api.service_task_registry_scope(registry):
            yield recording
    except ServiceTaskExecutionError:
        # Let go of the transaction first, then keep the evidence.
        session.rollback()
        for record in recording.failures:
            store.log_call(session, **record)
        session.commit()
        raise


def available_operations() -> list[dict[str, str]]:
    """What a diagram may call, for the publishing screen to show."""
    recording = _Recording(session=None, tenant_id="")  # type: ignore[arg-type]
    out: list[dict[str, str]] = []
    for connector in (LogConnector(recording), HttpConnector(recording)):
        for command in connector.list_commands():
            out.append(
                {
                    "operation_id": f"{command.connector_key}/{command.command_name}",
                    "description": command.description or "",
                }
            )
    return out
