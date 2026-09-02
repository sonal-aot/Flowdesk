"""Background poller that drives BPMN timers.

The library never decides when a timer fires: it persists due work in its
``scheduler_job`` table and expects the host to wake up and call
``api.run_due_scheduler_jobs``. This app runs that poll as an asyncio task and
hands the synchronous DB work to a worker thread, which is the honest shape for
a sync-SQLAlchemy library inside an async framework. See FINDINGS.md #5.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os

from m8flow_bpmn_core import api

from flowdesk.connectors import service_tasks
from flowdesk.db import session_factory
from flowdesk.seed import TENANTS

POLL_SECONDS = float(os.environ.get("FLOWDESK_SCHEDULER_POLL_SECONDS", "1.0"))
WORKER_ID = os.environ.get("FLOWDESK_SCHEDULER_WORKER_ID", "flowdesk-poller")

logger = logging.getLogger(__name__)


def run_due_jobs_once() -> int:
    """Run every due scheduler job. Returns how many fired.

    Per tenant, because the connectors have to be installed for the run this is
    about to advance: a timer is a perfectly ordinary way to arrive at a service
    task, and the registry is a context manager the calling code owns. Without
    this the flow fails with "no service task connector is registered" -- not on
    the request path, only for the shape "timer, then a service task". See
    FINDINGS.
    """
    executed = 0
    for tenant_id in TENANTS:
        session = session_factory()()
        try:
            with service_tasks(session, tenant_id):
                executed += api.run_due_scheduler_jobs(
                    session, worker_id=WORKER_ID, tenant_id=tenant_id
                )
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    return executed


async def poll_forever() -> None:
    while True:
        try:
            executed = await asyncio.to_thread(run_due_jobs_once)
            if executed:
                logger.info("scheduler fired %s job(s)", executed)
        except Exception:
            logger.exception("scheduler poll failed; continuing")
        await asyncio.sleep(POLL_SECONDS)


@contextlib.asynccontextmanager
async def scheduler_running():
    task = asyncio.create_task(poll_forever())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
