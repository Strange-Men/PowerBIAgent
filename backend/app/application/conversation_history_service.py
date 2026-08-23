"""Application query service for M4.3 conversation history/search APIs."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from backend.app.conversation.models import (
    ConversationDeleteResult,
    ConversationHistoryPage,
    ConversationListPage,
    ConversationReportPage,
)
from backend.app.conversation.repository import (
    ConversationHistoryRepository,
    ConversationPosition,
    HistoryPosition,
    ReportPosition,
)
from backend.app.memory.models import RuntimeDataMode
from backend.app.report.resources import ReportRepository, ReportStorageError


MAX_PAGE_SIZE = 50
MAX_SEARCH_QUERY_LENGTH = 200


class InvalidConversationCursorError(ValueError):
    """Opaque cursor is malformed or belongs to another query scope."""


class InvalidConversationQueryError(ValueError):
    """Limit or search query is outside the bounded contract."""


class _CursorPayload(BaseModel):
    v: Literal[1]
    kind: Literal["recent", "search", "history", "reports"]
    mode: RuntimeDataMode
    timestamp: datetime
    tie: str
    scope: str

    model_config = ConfigDict(extra="forbid", frozen=True)


def _normalize_cursor_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _encode_cursor(payload: _CursorPayload) -> str:
    raw = json.dumps(
        payload.model_dump(mode="json"),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(
    cursor: str,
    *,
    kind: Literal["recent", "search", "history", "reports"],
    mode: RuntimeDataMode,
    scope: str,
) -> _CursorPayload:
    if not cursor or len(cursor) > 2048:
        raise InvalidConversationCursorError("invalid_cursor")
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.b64decode(
            padded.encode("ascii"), altchars=b"-_", validate=True
        )
        data = json.loads(raw.decode("utf-8"))
        payload = _CursorPayload.model_validate(data)
    except (
        UnicodeError,
        ValueError,
        TypeError,
        json.JSONDecodeError,
        binascii.Error,
        ValidationError,
    ) as exc:
        raise InvalidConversationCursorError("invalid_cursor") from exc
    if payload.kind != kind or payload.mode != mode or payload.scope != scope:
        raise InvalidConversationCursorError("invalid_cursor")
    return payload


def _validate_limit(limit: int) -> None:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_PAGE_SIZE:
        raise InvalidConversationQueryError("invalid_limit")


def _search_scope(query: str) -> str:
    return hashlib.sha256(query.casefold().encode("utf-8")).hexdigest()


class ConversationHistoryService:
    """Orchestrates validation/cursors without owning persisted facts."""

    def __init__(
        self,
        repository: ConversationHistoryRepository,
        *,
        report_repository: ReportRepository | None = None,
    ) -> None:
        self._repository = repository
        self._report_repository = report_repository

    async def list_recent(
        self,
        runtime_mode: RuntimeDataMode,
        *,
        limit: int,
        cursor: str | None = None,
    ) -> ConversationListPage:
        _validate_limit(limit)
        after = None
        if cursor is not None:
            payload = _decode_cursor(
                cursor, kind="recent", mode=runtime_mode, scope=""
            )
            after = ConversationPosition(
                updated_at=_normalize_cursor_time(payload.timestamp),
                conversation_id=payload.tie,
            )
        page = await self._repository.list_recent(
            runtime_mode, limit=limit, after=after
        )
        next_cursor = None
        if page.next_position is not None:
            next_cursor = _encode_cursor(
                _CursorPayload(
                    v=1,
                    kind="recent",
                    mode=runtime_mode,
                    timestamp=page.next_position.updated_at,
                    tie=page.next_position.conversation_id,
                    scope="",
                )
            )
        return ConversationListPage(
            runtime_mode=runtime_mode,
            items=page.items,
            next_cursor=next_cursor,
        )

    async def get_history(
        self,
        runtime_mode: RuntimeDataMode,
        conversation_id: str,
        *,
        limit: int,
        cursor: str | None = None,
    ) -> ConversationHistoryPage:
        _validate_limit(limit)
        after = None
        if cursor is not None:
            payload = _decode_cursor(
                cursor,
                kind="history",
                mode=runtime_mode,
                scope=conversation_id,
            )
            try:
                row_id = int(payload.tie)
            except ValueError as exc:
                raise InvalidConversationCursorError("invalid_cursor") from exc
            if row_id < 1:
                raise InvalidConversationCursorError("invalid_cursor")
            after = HistoryPosition(
                created_at=_normalize_cursor_time(payload.timestamp), row_id=row_id
            )
        page = await self._repository.get_history(
            runtime_mode,
            conversation_id,
            limit=limit,
            after=after,
        )
        next_cursor = None
        if page.next_position is not None:
            next_cursor = _encode_cursor(
                _CursorPayload(
                    v=1,
                    kind="history",
                    mode=runtime_mode,
                    timestamp=page.next_position.created_at,
                    tie=str(page.next_position.row_id),
                    scope=conversation_id,
                )
            )
        return ConversationHistoryPage(
            runtime_mode=runtime_mode,
            conversation_id=conversation_id,
            archived_at=page.archived_at,
            title=page.title,
            items=page.items,
            next_cursor=next_cursor,
        )

    async def search(
        self,
        runtime_mode: RuntimeDataMode,
        *,
        query: str,
        limit: int,
        cursor: str | None = None,
    ) -> ConversationListPage:
        _validate_limit(limit)
        normalized_query = query.strip()
        if not normalized_query or len(normalized_query) > MAX_SEARCH_QUERY_LENGTH:
            raise InvalidConversationQueryError("invalid_search_query")
        scope = _search_scope(normalized_query)
        after = None
        if cursor is not None:
            payload = _decode_cursor(
                cursor, kind="search", mode=runtime_mode, scope=scope
            )
            after = ConversationPosition(
                updated_at=_normalize_cursor_time(payload.timestamp),
                conversation_id=payload.tie,
            )
        page = await self._repository.search(
            runtime_mode,
            normalized_query,
            limit=limit,
            after=after,
        )
        next_cursor = None
        if page.next_position is not None:
            next_cursor = _encode_cursor(
                _CursorPayload(
                    v=1,
                    kind="search",
                    mode=runtime_mode,
                    timestamp=page.next_position.updated_at,
                    tie=page.next_position.conversation_id,
                    scope=scope,
                )
            )
        return ConversationListPage(
            runtime_mode=runtime_mode,
            items=page.items,
            next_cursor=next_cursor,
        )

    async def list_reports(
        self,
        source_mode: RuntimeDataMode,
        conversation_id: str,
        *,
        limit: int,
        cursor: str | None = None,
    ) -> ConversationReportPage:
        _validate_limit(limit)
        after = None
        if cursor is not None:
            payload = _decode_cursor(
                cursor,
                kind="reports",
                mode=source_mode,
                scope=conversation_id,
            )
            after = ReportPosition(
                created_at=_normalize_cursor_time(payload.timestamp),
                report_id=payload.tie,
            )
        page = await self._repository.list_reports(
            source_mode,
            conversation_id,
            limit=limit,
            after=after,
        )
        next_cursor = None
        if page.next_position is not None:
            next_cursor = _encode_cursor(
                _CursorPayload(
                    v=1,
                    kind="reports",
                    mode=source_mode,
                    timestamp=page.next_position.created_at,
                    tie=page.next_position.report_id,
                    scope=conversation_id,
                )
            )
        return ConversationReportPage(
            source_mode=source_mode,
            conversation_id=conversation_id,
            items=page.items,
            next_cursor=next_cursor,
        )

    async def archive(self, runtime_mode: RuntimeDataMode, conversation_id: str):
        return await self._repository.archive(runtime_mode, conversation_id)

    async def rename(
        self, runtime_mode: RuntimeDataMode, conversation_id: str, title: str
    ):
        normalized = title.strip()
        if not normalized or len(normalized) > 80:
            raise InvalidConversationQueryError("invalid_conversation_title")
        return await self._repository.rename(
            runtime_mode, conversation_id, normalized
        )

    async def delete(
        self, runtime_mode: RuntimeDataMode, conversation_id: str
    ) -> ConversationDeleteResult:
        result = await self._repository.delete(runtime_mode, conversation_id)
        if result.report_ids:
            if self._report_repository is None:
                raise ReportStorageError("report_cleanup_repository_unavailable")
            await self._report_repository.delete_html_files(result.report_ids)
        await self._repository.complete_delete(runtime_mode, conversation_id)
        return ConversationDeleteResult(
            runtime_mode=runtime_mode,
            conversation_id=conversation_id,
            deleted=True,
            deleted_counts=result.deleted_counts,
        )
