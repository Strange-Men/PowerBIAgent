"""Presentation-only conversation title rules."""

from __future__ import annotations

import re


_SPACE = re.compile(r"\s+")


def normalize_conversation_title(value: str, *, max_length: int = 80) -> str:
    normalized = _SPACE.sub(" ", value).strip()
    if not normalized:
        raise ValueError("conversation_title_empty")
    return normalized[:max_length]


def default_conversation_title(user_message: str) -> str:
    normalized = normalize_conversation_title(user_message)
    return normalized if len(normalized) <= 28 else f"{normalized[:28]}…"
