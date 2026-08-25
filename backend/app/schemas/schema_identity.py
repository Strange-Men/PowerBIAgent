"""Stable schema identity helpers shared across architecture layers."""

from __future__ import annotations

import hashlib
import json

from backend.app.schemas.data_contracts import SemanticModelSchema


def compute_schema_fingerprint(schema: SemanticModelSchema) -> str:
    """Hash authoritative visible model metadata without runtime or row data."""

    visible_tables = {
        table.name: table
        for table in schema.tables
        if not table.is_hidden and not table.is_system_managed
    }
    visible_columns = {
        (table.name, column.name)
        for table in visible_tables.values()
        for column in table.columns
        if not column.is_hidden
    }
    payload = {
        "tables": [
            {
                "name": table.name,
                "columns": sorted(
                    (
                        {"name": column.name, "data_type": column.data_type}
                        for column in table.columns
                        if not column.is_hidden
                    ),
                    key=lambda item: (item["name"], item["data_type"]),
                ),
                "measures": sorted(
                    (
                        {
                            "name": measure.name,
                            "data_type": measure.data_type,
                            "expression": measure.expression,
                        }
                        for measure in table.measures
                        if not measure.is_hidden
                    ),
                    key=lambda item: (
                        item["name"], item["data_type"], item["expression"]
                    ),
                ),
            }
            for table in sorted(visible_tables.values(), key=lambda item: item.name)
        ],
        "active_relationships": sorted(
            (
                {
                    "from_table": relationship.from_table,
                    "from_column": relationship.from_column,
                    "to_table": relationship.to_table,
                    "to_column": relationship.to_column,
                }
                for relationship in schema.relationships
                if relationship.is_active
                and (relationship.from_table, relationship.from_column)
                in visible_columns
                and (relationship.to_table, relationship.to_column) in visible_columns
            ),
            key=lambda item: (
                item["from_table"], item["from_column"],
                item["to_table"], item["to_column"],
            ),
        ),
    }
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
