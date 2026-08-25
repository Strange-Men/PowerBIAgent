"""Small persisted cache for display translations only."""

from __future__ import annotations

import json
import os
import threading
import uuid
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from backend.app.localization.models import LocalizationRecord


class LocalizationRegistryError(ValueError):
    pass


class LocalizationRegistry:
    """Exact model/object/schema lookup with atomic persistence."""

    _adapter = TypeAdapter(list[LocalizationRecord])

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.RLock()

    def get(
        self,
        *,
        semantic_model_key: str,
        object_identity: str,
        object_type: str,
        canonical_name: str,
        locale: str,
        schema_identity: str,
    ) -> LocalizationRecord | None:
        with self._lock:
            records = self._load()
        return next(
            (
                item
                for item in records
                if item.semantic_model_key == semantic_model_key
                and item.object_identity == object_identity
                and item.object_type == object_type
                and item.canonical_name == canonical_name
                and item.locale == locale
                and item.schema_identity == schema_identity
            ),
            None,
        )

    def put(self, record: LocalizationRecord) -> None:
        identity = (
            record.semantic_model_key,
            record.object_identity,
            record.object_type,
            record.canonical_name,
            record.locale,
            record.schema_identity,
        )
        with self._lock:
            records = [
                item
                for item in self._load()
                if (
                    item.semantic_model_key,
                    item.object_identity,
                    item.object_type,
                    item.canonical_name,
                    item.locale,
                    item.schema_identity,
                )
                != identity
            ]
            records.append(record)
            self._write(records)

    def _load(self) -> list[LocalizationRecord]:
        if not self.path.exists():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return self._adapter.validate_python(raw)
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            raise LocalizationRegistryError("localization_registry_invalid") from exc

    def _write(self, records: list[LocalizationRecord]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{uuid.uuid4().hex}.tmp")
        payload = [item.model_dump(mode="json") for item in records]
        try:
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2),
                encoding="utf-8",
            )
            os.replace(temporary, self.path)
        finally:
            if temporary.exists():
                temporary.unlink()
