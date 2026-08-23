"""Repository boundary for namespace-scoped conversation queries."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Generic, TypeVar

from backend.app.conversation.models import (
    ConversationArchiveResult,
    ConversationHistoryItem,
    ConversationReportItem,
    ConversationSummary,
    ConversationRenameResult,
)
from backend.app.memory.models import RuntimeDataMode


T = TypeVar("T")
P = TypeVar("P")


@dataclass(frozen=True)
class ConversationPosition:
    updated_at: datetime
    conversation_id: str


@dataclass(frozen=True)
class HistoryPosition:
    created_at: datetime
    row_id: int


@dataclass(frozen=True)
class ReportPosition:
    created_at: datetime
    report_id: str


@dataclass(frozen=True)
class RepositoryPage(Generic[T, P]):
    items: list[T]
    next_position: P | None


@dataclass(frozen=True)
class HistoryRepositoryPage:
    archived_at: datetime | None
    title: str | None
    items: list[ConversationHistoryItem]
    next_position: HistoryPosition | None


@dataclass(frozen=True)
class RepositoryDeleteResult:
    deleted_counts: dict[str, int]
    report_ids: list[str]


class ConversationHistoryRepository(ABC):
    """Every query and mutation requires its namespace explicitly."""

    @abstractmethod
    async def list_recent(
        self,
        runtime_mode: RuntimeDataMode,
        *,
        limit: int,
        after: ConversationPosition | None,
    ) -> RepositoryPage[ConversationSummary, ConversationPosition]: ...

    @abstractmethod
    async def get_history(
        self,
        runtime_mode: RuntimeDataMode,
        conversation_id: str,
        *,
        limit: int,
        after: HistoryPosition | None,
    ) -> HistoryRepositoryPage: ...

    @abstractmethod
    async def search(
        self,
        runtime_mode: RuntimeDataMode,
        query: str,
        *,
        limit: int,
        after: ConversationPosition | None,
    ) -> RepositoryPage[ConversationSummary, ConversationPosition]: ...

    @abstractmethod
    async def list_reports(
        self,
        source_mode: RuntimeDataMode,
        conversation_id: str,
        *,
        limit: int,
        after: ReportPosition | None,
    ) -> RepositoryPage[ConversationReportItem, ReportPosition]: ...

    @abstractmethod
    async def archive(
        self, runtime_mode: RuntimeDataMode, conversation_id: str
    ) -> ConversationArchiveResult: ...

    @abstractmethod
    async def rename(
        self, runtime_mode: RuntimeDataMode, conversation_id: str, title: str
    ) -> ConversationRenameResult: ...

    @abstractmethod
    async def delete(
        self, runtime_mode: RuntimeDataMode, conversation_id: str
    ) -> RepositoryDeleteResult: ...

    @abstractmethod
    async def complete_delete(
        self, runtime_mode: RuntimeDataMode, conversation_id: str
    ) -> None:
        """Clear a durable delete intent after report cleanup succeeds."""
        ...
