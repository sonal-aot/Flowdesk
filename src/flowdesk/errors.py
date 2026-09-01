"""Maps the library's error hierarchy onto HTTP status codes and plain English.

Every public failure is a ``BpmnCoreError`` subclass, which is enough to build
an API on without parsing messages -- one of the better parts of the library's
contract.

The engine's own wording ("User 2 is not authorized for process.start in tenant
acme: No matching permission grant...") is accurate and hard to act on, so each
status also carries a plainer sentence. The original text stays in ``technical``,
which this app does show -- its users are running workflows, so the engine's own
words are useful to them.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from m8flow_bpmn_core.errors import (
    AuthorizationError,
    BpmnCoreError,
    InvalidStateError,
    NotFoundError,
    ServiceTaskExecutionError,
    ValidationError,
)

# Order matters: InvalidStateError SUBCLASSES ValidationError, so checking
# ValidationError first would mislabel every 409 as a 422. See FINDINGS.md #4.
STATUS_BY_ERROR: tuple[tuple[type[BpmnCoreError], int], ...] = (
    # A service task is an outbound call, so its failure is a gateway problem,
    # not the caller's mistake.
    (ServiceTaskExecutionError, 502),
    (NotFoundError, 404),
    (AuthorizationError, 403),
    (InvalidStateError, 409),
    (ValidationError, 422),
)


#: What to tell the person, by status code.
MESSAGE_BY_STATUS: dict[int, str] = {
    403: "You do not have permission to do that.",
    404: "We could not find that.",
    409: "That has already moved on — refresh and take another look.",
    422: "Something in the form was not right.",
    502: (
        "A service task failed, so the step was not saved. The activity log has "
        "the details."
    ),
    400: "That did not work.",
}


def message_for(exc: BpmnCoreError, status_code: int) -> str:
    """Prefer our own wording; keep the library's when it is already readable.

    ValidationError is the one case the app raises itself with a user-facing
    sentence, so that text is passed straight through.
    """
    if status_code == 422 and isinstance(exc, ValidationError):
        return str(exc)
    # A conflict the app raised itself already reads as a sentence; the library's
    # own wording ("Cannot suspend a terminal process instance") does not.
    if status_code == 409 and str(exc).startswith("This run is "):
        return str(exc)
    return MESSAGE_BY_STATUS.get(status_code, MESSAGE_BY_STATUS[400])


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(BpmnCoreError)
    async def handle_bpmn_core_error(
        _request: Request, exc: BpmnCoreError
    ) -> JSONResponse:
        status_code = next(
            (code for error_type, code in STATUS_BY_ERROR if isinstance(exc, error_type)),
            400,
        )
        return JSONResponse(
            status_code=status_code,
            content={
                "message": message_for(exc, status_code),
                "error": type(exc).__name__,
                "technical": str(exc),
            },
        )
