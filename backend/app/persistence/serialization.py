"""JSON serialization helpers for Pydantic ↔ SQLAlchemy roundtrips.

Usage
-----
.. code-block:: python

    from backend.app.persistence.serialization import (
        domain_to_json,
        json_to_domain,
    )

    # Store
    row.payload_json = domain_to_json(work_memory)

    # Load
    memory = json_to_domain(WorkMemorySchema, row.payload_json)
"""

from __future__ import annotations

import json
from typing import Any, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def domain_to_json(domain: BaseModel) -> str:
    """Serialize a Pydantic domain model to a JSON string.

    Uses ``model_dump(mode="json")`` which ensures all values are
    JSON-compatible types (no Pydantic custom types, no datetime objects),
    then serializes to a JSON string.
    """
    raw = domain.model_dump(mode="json", by_alias=False)
    return json.dumps(raw, ensure_ascii=False, default=str)


def json_to_domain(model_cls: type[T], json_str: str) -> T:
    """Deserialize a JSON string back into a Pydantic domain model.

    Raises ``ValidationError`` if the JSON does not match the schema —
    this is the intended fail-closed behaviour for corrupted payloads.
    """
    raw: dict[str, Any] = json.loads(json_str)
    return model_cls.model_validate(raw)


def safe_json_loads(json_str: str | None) -> dict[str, Any] | None:
    """Load a JSON string, returning ``None`` for empty/null input.

    Raises ``json.JSONDecodeError`` for invalid JSON (fail-closed).
    """
    if not json_str:
        return None
    return json.loads(json_str)