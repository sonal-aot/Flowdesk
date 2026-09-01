"""Database wiring for the leave app.

The m8flow-bpmn-core wheel ships no Alembic migrations by design -- the host
application owns its schema. For a sample app of this size the library's own
``create_schema`` helper is enough; a production host would put the library
metadata inside its own migration instead. See FINDINGS.md #1.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

from m8flow_bpmn_core.db import build_engine, create_schema
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

DATABASE_URL = os.environ.get(
    "FLOWDESK_DATABASE_URL", "sqlite+pysqlite:///./flowdesk.db"
)

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = build_engine(DATABASE_URL)
    return _engine


def session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=engine(), autoflush=False, expire_on_commit=False
        )
    return _session_factory


def init_schema() -> None:
    from flowdesk.store import AppBase

    create_schema(engine())                # the library's 21 workflow tables
    AppBase.metadata.create_all(engine())  # flow files and the activity log


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session, one transaction, per request.

    The library accepts a caller-owned Session and never commits, so the commit
    and rollback boundary lives here.
    """
    session = session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reset_for_tests(database_url: str) -> None:
    global _engine, _session_factory
    global DATABASE_URL
    DATABASE_URL = database_url
    _engine = None
    _session_factory = None
