"""App-owned tables.

The library owns the workflow tables. Flowdesk additionally has to remember the
files that make up a published flow -- the diagram, any decision tables, and the
form schemas the library does not keep -- plus a log of what its connectors did.
"""

from __future__ import annotations

import time

from m8flow_bpmn_core.models.base import NAMING_CONVENTION
from sqlalchemy import Integer, MetaData, String, Text, UniqueConstraint, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class AppBase(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class FlowAsset(AppBase):
    """One file belonging to one published flow."""

    __tablename__ = "flow_asset"
    __table_args__ = (
        UniqueConstraint("tenant_id", "process_id", "filename", name="flow_asset_unique"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    process_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # bpmn|dmn|form
    content: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at_in_seconds: Mapped[int] = mapped_column(Integer, nullable=False)


class Credential(AppBase):
    """A password for one account in one company.

    The library manages neither users nor credentials, so this is ours.
    """

    __tablename__ = "credential"
    __table_args__ = (
        UniqueConstraint("tenant_id", "username", name="credential_unique"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)


class ConnectorCall(AppBase):
    """What a service task asked for, and what came back."""

    __tablename__ = "connector_call"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    process_instance_id: Mapped[int | None] = mapped_column(Integer, index=True)
    operation_id: Mapped[str] = mapped_column(String(255), nullable=False)
    parameters: Mapped[str] = mapped_column(Text, nullable=False, default="")
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)  # ok|failed
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at_in_seconds: Mapped[int] = mapped_column(Integer, nullable=False)


def save_asset(
    session: Session,
    *,
    tenant_id: str,
    process_id: str,
    filename: str,
    kind: str,
    content: str,
) -> FlowAsset:
    existing = session.scalar(
        select(FlowAsset).where(
            FlowAsset.tenant_id == tenant_id,
            FlowAsset.process_id == process_id,
            FlowAsset.filename == filename,
        )
    )
    if existing is not None:
        existing.content = content
        existing.kind = kind
        existing.updated_at_in_seconds = int(time.time())
        return existing
    asset = FlowAsset(
        tenant_id=tenant_id,
        process_id=process_id,
        filename=filename,
        kind=kind,
        content=content,
        updated_at_in_seconds=int(time.time()),
    )
    session.add(asset)
    session.flush()
    return asset


def assets_for(session: Session, tenant_id: str, process_id: str) -> list[FlowAsset]:
    return list(
        session.scalars(
            select(FlowAsset)
            .where(FlowAsset.tenant_id == tenant_id, FlowAsset.process_id == process_id)
            .order_by(FlowAsset.filename)
        )
    )


def asset(
    session: Session, tenant_id: str, process_id: str, filename: str
) -> FlowAsset | None:
    return session.scalar(
        select(FlowAsset).where(
            FlowAsset.tenant_id == tenant_id,
            FlowAsset.process_id == process_id,
            FlowAsset.filename == filename,
        )
    )


def log_call(
    session: Session,
    *,
    tenant_id: str,
    process_instance_id: int | None,
    operation_id: str,
    parameters: str,
    outcome: str,
    detail: str = "",
) -> ConnectorCall:
    call = ConnectorCall(
        tenant_id=tenant_id,
        process_instance_id=process_instance_id,
        operation_id=operation_id,
        parameters=parameters,
        outcome=outcome,
        detail=detail,
        created_at_in_seconds=int(time.time()),
    )
    session.add(call)
    session.flush()
    return call


def credential(session: Session, tenant_id: str, username: str) -> Credential | None:
    return session.scalar(
        select(Credential).where(
            Credential.tenant_id == tenant_id, Credential.username == username
        )
    )


def set_password(
    session: Session, *, tenant_id: str, username: str, password_hash: str
) -> Credential:
    existing = credential(session, tenant_id, username)
    if existing is not None:
        existing.password_hash = password_hash
        return existing
    row = Credential(
        tenant_id=tenant_id, username=username, password_hash=password_hash
    )
    session.add(row)
    session.flush()
    return row
