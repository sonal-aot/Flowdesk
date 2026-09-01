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

from flowdesk.db import session_factory

POLL_SECONDS = float(os.environ.get("FLOWDESK_SCHEDULER_POLL_SECONDS", "1.0"))
WORKER_ID = os.environ.get("FLOWDESK_SCHEDULER_WORKER_ID", "flowdesk-poller")

logger = logging.getLogger(__name__)


def run_due_jobs_once() -> int:
    """Run every due scheduler job. Returns how many fired."""
    session = session_factory()()
    try:
        executed = api.run_due_scheduler_jobs(session, worker_id=WORKER_ID)
        session.commit()
        return executed
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


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
