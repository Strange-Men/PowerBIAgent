"""End-to-end FIRST-WRONG-LAYER: a genuine INTERNAL_FAILURE is located.

The public API still collapses an unmapped tool failure into INTERNAL_FAILURE;
this test proves the request-scoped diagnostic persists *where* it happened
without ever copying the exception message or any business value.
"""
import json

from backend.app.harness.errors import ToolExecutionError
from backend.tests.api.test_cloud_factual_e2e import factual_product  # noqa: F401


def test_internal_failure_records_stage_and_error_type_safely(
    factual_product, tmp_path, monkeypatch
):
    c, app, h, s, _identity, _facts, _llm, _results = factual_product
    diagnostics_dir = tmp_path / "diagnostics"
    monkeypatch.setenv("POWERBIAGENT_DIAGNOSTICS_DIR", str(diagnostics_dir))
    adapter = next(iter(app.state.cloud_workspace_service._contexts.values())).adapter

    async def exploding_execute_dax(request):
        raise ToolExecutionError(
            "SENSITIVE_SENTINEL message", error_type="weird_unknown_error")

    monkeypatch.setattr(adapter, "execute_dax", exploding_execute_dax)

    response = c.post(
        "/api/v1/cloud/chat",
        headers=h,
        json={"message": "查询 Total Sales", "request_id": "diag-internal",
              "expected_generation": s["generation"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["failure"]["code"] == "INTERNAL_FAILURE"

    lines = (diagnostics_dir / "turns.jsonl").read_text(encoding="utf-8").splitlines()
    record = next(
        json.loads(line) for line in lines
        if json.loads(line)["request_id"] == "diag-internal"
    )
    # The failure is located: stage, error code and exception-free evidence.
    assert record["first_wrong_stage"] == "TOOL_EXECUTION"
    assert record["failure_code"] == "INTERNAL_FAILURE"
    assert any(
        stage.get("error_type") == "weird_unknown_error"
        for stage in record["stages"]
    )
    # No message, prompt, member literal or business value is ever persisted.
    assert "SENSITIVE_SENTINEL" not in json.dumps(record)


def test_successful_turn_records_the_stage_timeline(
    factual_product, tmp_path, monkeypatch
):
    c, _app, h, s, _identity, _facts, _llm, _results = factual_product
    diagnostics_dir = tmp_path / "diagnostics"
    monkeypatch.setenv("POWERBIAGENT_DIAGNOSTICS_DIR", str(diagnostics_dir))
    response = c.post(
        "/api/v1/cloud/chat",
        headers=h,
        json={"message": "查询 Total Sales", "request_id": "diag-ok",
              "expected_generation": s["generation"]},
    )
    assert response.status_code == 200, response.text
    lines = (diagnostics_dir / "turns.jsonl").read_text(encoding="utf-8").splitlines()
    record = next(
        json.loads(line) for line in lines
        if json.loads(line)["request_id"] == "diag-ok"
    )
    stages = [stage["stage"] for stage in record["stages"]]
    assert stages[0] == "UNDERSTANDING"
    assert "TOOL_EXECUTION" in stages
    assert record["first_wrong_stage"] is None
    assert record["runtime_build_id"]