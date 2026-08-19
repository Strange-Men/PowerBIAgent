"""SQLAlchemy ORM persistence models — M4.0 schema baseline.

IMPORTANT
---------
These are **persistence models**, NOT business domain models.
Business logic must go through Pydantic domain models (``StructuredWorkMemory``
etc.) and ``MemoryRepository`` / ``SnapshotRepository`` ABCs.

Mapping policy
--------------
*   Search / concurrency-critical fields (``request_id``, ``conversation_id``,
    ``runtime_mode``, ``state_status``, version numbers, timestamps) are
    always separate columns.
*   Rich structured payloads use JSON TEXT columns.
*   Serialization:  ``pydantic_model.model_dump(mode="json")``
*   Deserialization:  ``DomainModel.model_validate(json.loads(db_value))``
*   No pickle, no raw Python object serialisation, no secrets, no raw LLM
    responses.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# ---------------------------------------------------------------------------
# Re-export the runtime mode enum used by persistence models
# ---------------------------------------------------------------------------
from backend.app.memory.models import MemoryStatus, RuntimeDataMode

# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------


class ConversationModel(Base):
    """One conversation root.

    Identity: (runtime_mode, conversation_id).
    This allows ``mock`` and ``real`` conversations to share the same
    ``conversation_id`` while remaining fully isolated.
    """

    __tablename__ = "conversations"

    conversation_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, comment="UUIDv4 conversation identifier"
    )
    runtime_mode: Mapped[str] = mapped_column(
        String(16), primary_key=True, comment="mock | real"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
        comment="UTC creation timestamp",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="UTC last-update timestamp",
    )

    __table_args__ = (
        # Composite primary key is (runtime_mode, conversation_id)
    )

    # Relationships
    work_memories = relationship(
        "WorkMemoryModel", back_populates="conversation", lazy="select"
    )
    result_snapshots = relationship(
        "ResultSnapshotModel", back_populates="conversation", lazy="select"
    )


# ---------------------------------------------------------------------------
# Work Memories (StructuredWorkMemory)
# ---------------------------------------------------------------------------


class WorkMemoryModel(Base):
    """Persistent storage for ``StructuredWorkMemory``."""

    __tablename__ = "work_memories"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    request_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True, comment="幂等请求 ID"
    )
    conversation_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True,
    )
    runtime_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="mock | real"
    )
    state_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=MemoryStatus.PENDING.value,
        comment="pending | committed | failed",
    )
    base_memory_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="本轮开始时 committed 版本"
    )
    memory_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="当前版本号"
    )
    semantic_model_key: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True
    )
    report_template_key: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    current_intent: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    analysis_goal: Mapped[Optional[str]] = mapped_column(
        String(512), nullable=True
    )
    # Structured payload as JSON TEXT
    payload_json: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="StructuredWorkMemory full payload (JSON)"
    )
    failure_reason: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    failure_stage: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    conversation = relationship(
        "ConversationModel", back_populates="work_memories"
    )

    __table_args__ = (
        UniqueConstraint(
            "runtime_mode",
            "request_id",
            name="uq_work_memories_runtime_request",
        ),
        ForeignKeyConstraint(
            ["runtime_mode", "conversation_id"],
            ["conversations.runtime_mode", "conversations.conversation_id"],
            name="fk_work_memories_conv_composite",
        ),
    )


# ---------------------------------------------------------------------------
# Pending Clarifications
# ---------------------------------------------------------------------------


class PendingClarificationModel(Base):
    """Persistent storage for ``PendingClarificationContext``."""

    __tablename__ = "pending_clarifications"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    conversation_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    runtime_mode: Mapped[str] = mapped_column(
        String(16), nullable=False
    )
    chain_id: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="澄清链唯一 ID"
    )
    semantic_model_key: Mapped[str] = mapped_column(
        String(128), nullable=False
    )
    schema_fingerprint: Mapped[str] = mapped_column(
        String(64), nullable=False
    )
    # Structured payload as JSON TEXT
    payload_json: Mapped[str] = mapped_column(
        Text, nullable=False, comment="PendingClarificationContext full payload (JSON)"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "runtime_mode",
            "conversation_id",
            name="uq_pending_clarifications_runtime_conv",
        ),
        ForeignKeyConstraint(
            ["runtime_mode", "conversation_id"],
            ["conversations.runtime_mode", "conversations.conversation_id"],
            name="fk_pending_clarifications_conv_composite",
        ),
    )


# ---------------------------------------------------------------------------
# Result Snapshots
# ---------------------------------------------------------------------------


class ResultSnapshotModel(Base):
    """Persistent storage for ``TurnResultSnapshot``."""

    __tablename__ = "result_snapshots"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    request_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    runtime_mode: Mapped[str] = mapped_column(
        String(16), nullable=False
    )
    conversation_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True,
    )
    request_fingerprint_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="SHA-256 request fingerprint"
    )
    terminal_state: Mapped[str] = mapped_column(
        String(32), nullable=False
    )
    response_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default=""
    )
    # Structured payload as JSON TEXT
    payload_json: Mapped[str] = mapped_column(
        Text, nullable=False, comment="TurnResultSnapshot full payload (JSON)"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
    )

    conversation = relationship(
        "ConversationModel", back_populates="result_snapshots"
    )

    __table_args__ = (
        UniqueConstraint(
            "runtime_mode",
            "request_id",
            name="uq_result_snapshots_runtime_request",
        ),
        ForeignKeyConstraint(
            ["runtime_mode", "conversation_id"],
            ["conversations.runtime_mode", "conversations.conversation_id"],
            name="fk_result_snapshots_conv_composite",
        ),
    )


# ---------------------------------------------------------------------------
# Report Artifacts (metadata only — HTML stays on filesystem)
# ---------------------------------------------------------------------------


class ReportArtifactModel(Base):
    """Persistent metadata for managed HTML report artifacts.

    The actual HTML content continues to live on the filesystem at
    ``<root>/<report_id>.html`` where root is the LocalReportRepository root.
    """

    __tablename__ = "report_artifacts"

    report_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, comment="rpt_<uuidhex>"
    )
    conversation_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True
    )
    request_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    template_key: Mapped[str] = mapped_column(
        String(64), nullable=False
    )
    semantic_model_key: Mapped[str] = mapped_column(
        String(128), nullable=False
    )
    schema_fingerprint: Mapped[str] = mapped_column(
        String(64), nullable=False
    )
    source_mode: Mapped[str] = mapped_column(
        String(16), nullable=False
    )
    content_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="SHA-256 of stored HTML"
    )
    relative_path: Mapped[str] = mapped_column(
        String(256), nullable=False, comment="<report_id>.html relative to LocalReportRepository root"
    )
    # Structured metadata payload
    payload_json: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="metadata-only ReportArtifactMetadata payload, no HTML"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        {"sqlite_autoincrement": False},
    )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_all_tables(engine: Any) -> None:
    """Create all tables defined in this module.

    Intended for tests and migration smoke tests.
    Production schema management is via Alembic.
    """
    Base.metadata.create_all(engine)