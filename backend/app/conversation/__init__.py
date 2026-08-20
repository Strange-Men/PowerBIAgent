"""Namespace-first conversation history/search domain contracts."""

from backend.app.conversation.models import (
    ConversationArchiveResult,
    ConversationDeleteResult,
    ConversationHistoryCorruptionError,
    ConversationHistoryItem,
    ConversationHistoryPage,
    ConversationListPage,
    ConversationNotFoundError,
    ConversationReportItem,
    ConversationReportPage,
    ConversationSummary,
)

__all__ = [
    "ConversationArchiveResult",
    "ConversationDeleteResult",
    "ConversationHistoryCorruptionError",
    "ConversationHistoryItem",
    "ConversationHistoryPage",
    "ConversationListPage",
    "ConversationNotFoundError",
    "ConversationReportItem",
    "ConversationReportPage",
    "ConversationSummary",
]
