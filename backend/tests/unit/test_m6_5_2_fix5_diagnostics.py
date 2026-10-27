"""FIRST-WRONG-LAYER diagnostics: locate a failure stage without leaking data."""
import json

import pytest

from backend.app.core import turn_diagnostics as diag
from backend.app.core.turn_diagnostics import (
    DAX_BUILD, GROUNDING, MEMBER_DISCOVERY, TERMINAL, TurnDiagnosticRecorder,
    bind_diagnostics, current_diagnostics, coarse_stage, emit_diagnostic,
    mark_stage, safe_metadata,
)


def test_coarse_stage_maps_internal_constants_to_the_canonical_vocabulary():
    assert coarse_stage("semantic_grounding") == GROUNDING
    assert coarse_stage("member_grounding") == MEMBER_DISCOVERY
    assert coarse_stage("dax_semantic_consistency") == DAX_BUILD
    assert coarse_stage("unknown_stage") == TERMINAL
    assert coarse_stage(None) == TERMINAL


def test_safe_metadata_drops_unknown_keys_and_business_values():
    kept = safe_metadata(
        relation="follow_up", hit_count=3, member_literal_present=True,
        # None of the following may ever be retained:
        member_literal="15056BL", rows=[{"Country": "France", "sales": 1.2}],
        prompt="show me everything", token="secret", user="alice@example.com",
    )
    assert kept == {"relation": "follow_up", "hit_count": 3,
                    "member_literal_present": True}


def test_recorder_records_exception_class_and_first_wrong_stage_only():
    recorder = TurnDiagnosticRecorder(request_id="r1", runtime_build_id="b1")
    with bind_diagnostics(recorder):
        assert current_diagnostics() is recorder
        mark_stage(GROUNDING, detail="semantic_grounding")
        mark_stage("member_grounding", detail="value_search", hit_count=0)
        recorder.fail(ValueError("sensitive message 15056BL"), stage="member_grounding")
    record = recorder.finalize(terminal_state="failed",
                               failure_code="INTERNAL_FAILURE")
    assert record["first_wrong_stage"] == MEMBER_DISCOVERY
    assert record["error_class"] == "ValueError"
    assert "15056BL" not in json.dumps(record)
    assert "sensitive message" not in json.dumps(record)


def test_mark_stage_is_a_noop_without_a_bound_recorder():
    assert current_diagnostics() is None
    mark_stage(GROUNDING)  # must not raise


def test_emit_writes_one_bounded_jsonl_line(tmp_path, monkeypatch):
    monkeypatch.setattr(diag, "_DIAGNOSTICS_DIR", tmp_path / "diagnostics")
    recorder = TurnDiagnosticRecorder(request_id="r2", runtime_build_id="b2")
    with bind_diagnostics(recorder):
        mark_stage(DAX_BUILD, detail="dax_generation")
    emit_diagnostic(recorder.finalize(terminal_state="completed"))
    path = tmp_path / "diagnostics" / "turns.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["request_id"] == "r2"
    assert payload["stages"][0]["stage"] == DAX_BUILD