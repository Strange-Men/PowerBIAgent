"""Shared deterministic evidence for fresh/follow-up/replace classification."""

from __future__ import annotations

import re
from enum import Enum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict


class TurnRelationKind(str, Enum):
    FRESH = "fresh"
    FOLLOW_UP = "follow_up"
    REPLACE = "replace"
    UNSPECIFIED = "unspecified"


class TurnRelationEvidence(BaseModel):
    kind: TurnRelationKind
    explicit: bool = False
    matched_cue: str | None = None
    source: str = "none"

    model_config = ConfigDict(frozen=True)

    _FRESH_CUES: ClassVar[tuple[str, ...]] = (
        "独立问题", "新问题", "重新开始", "忽略之前", "单独问", "重新分析",
        "start over", "new question", "ignore previous", "independently",
    )
    _REPLACE: ClassVar[re.Pattern[str]] = re.compile(r"^\s*(?:改成|改为|换成|换为|调整为|改看|换看|改|换)", re.IGNORECASE)
    _FOLLOW_PREFIX: ClassVar[re.Pattern[str]] = re.compile(r"^\s*(?:那|那么|只看|再看|继续|然后)", re.IGNORECASE)
    _FOLLOW_SUFFIX: ClassVar[re.Pattern[str]] = re.compile(r"呢\s*[？?。.]?\s*$", re.IGNORECASE)

    @classmethod
    def classify(cls, user_input: str) -> "TurnRelationEvidence":
        folded = user_input.casefold()
        for cue in cls._FRESH_CUES:
            if cue.casefold() in folded:
                return cls(
                    kind=TurnRelationKind.FRESH,
                    explicit=True,
                    matched_cue=cue,
                    source="deterministic_fresh_cue",
                )
        match = cls._REPLACE.search(user_input)
        if match:
            return cls(
                kind=TurnRelationKind.REPLACE,
                explicit=True,
                matched_cue=match.group(0).strip(),
                source="deterministic_replace_cue",
            )
        match = cls._FOLLOW_PREFIX.search(user_input) or cls._FOLLOW_SUFFIX.search(user_input)
        if match:
            return cls(
                kind=TurnRelationKind.FOLLOW_UP,
                explicit=True,
                matched_cue=match.group(0).strip(),
                source="deterministic_follow_up_cue",
            )
        return cls(kind=TurnRelationKind.UNSPECIFIED)
