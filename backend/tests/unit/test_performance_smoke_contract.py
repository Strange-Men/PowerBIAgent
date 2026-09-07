from __future__ import annotations

import pytest

from scripts.manual_smoke.m5_8_1_local_mcp_performance_smoke import (
    _select_model,
)


def test_raw_adapter_catalog_selects_exact_connected_display_name() -> None:
    items = [
        {
            "key": "opaque-a",
            "display_name": "Model A",
            "available": True,
            "connected": True,
            "selectable": False,
        },
        {
            "key": "opaque-b",
            "display_name": "Model B",
            "available": True,
            "connected": True,
            "selectable": False,
        },
    ]

    assert _select_model(
        items,
        "Model B",
        require_selectable=False,
    ) == "opaque-b"


def test_raw_adapter_catalog_still_rejects_ambiguous_selection() -> None:
    items = [
        {
            "key": "opaque-a",
            "display_name": "Same",
            "available": True,
            "connected": True,
            "selectable": False,
        },
        {
            "key": "opaque-b",
            "display_name": "Same",
            "available": True,
            "connected": True,
            "selectable": False,
        },
    ]

    with pytest.raises(RuntimeError, match="did not resolve uniquely"):
        _select_model(items, "Same", require_selectable=False)


def test_api_catalog_requires_service_owned_selectable_flag() -> None:
    items = [
        {
            "key": "opaque-a",
            "display_name": "Model A",
            "available": True,
            "connected": True,
            "selectable": False,
        }
    ]

    with pytest.raises(RuntimeError, match="selectable_count=0"):
        _select_model(items, "Model A")
