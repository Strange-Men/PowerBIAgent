"""Compare unchanged Real facts and timing with an exact committed baseline.

Only a temporary backend source snapshot is created. Child processes use the
normal root Settings, the same real providers, and isolated owned databases.
Business results stay in child memory; only equality digests leave the child.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import json
import statistics
import subprocess
import sys
import tarfile
import time
import traceback
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.acceptance_tempdir import owned_acceptance_tempdir


def require(condition, label):
    if not condition:
        raise RuntimeError(label)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def normalized(value, model_identity=None):
    if isinstance(value, dict):
        # Per-execution IDs/timing and LLM paraphrase are not semantic slots or
        # data facts. Keep model, ownership, filters, time, order and all values.
        result = {}
        for key, item in value.items():
            if key in {"result_id", "fact_id", "fact_set_id", "request_id", "execution_time_ms", "normalized_question", "inherited_context"}:
                continue
            if key == "semantic_model_key":
                require(model_identity is not None and item == model_identity[0], "unproven_comparison_model")
                result[key] = model_identity[1]
            else:
                result[key] = normalized(item, model_identity)
        return result
    if isinstance(value, list):
        return [normalized(v, model_identity) for v in value]
    return value


async def child(args):
    sys.path.insert(0, str(args.source_root))
    import httpx
    import yaml
    from backend.app.config.settings import Settings, LLMMode, PowerBIMode, PersistenceBackend
    from backend.app.main import create_app
    from backend.app.harness.runtime.tool_gateway import ToolExecutionContext
    from backend.app.harness.tool_registry import SchemaInput
    from backend.app.memory.models import RuntimeDataMode
    from backend.app.persistence.database import create_engine
    from backend.app.persistence.models import Base
    from backend.app.persistence.artifact_ownership import ArtifactOwnershipRegistry, managed_test_run, probe_owned_sqlite_residuals
    from backend.app.schemas.data_contracts import CanonicalQueryPlan, UserContext
    from backend.app.facts.verified import VerifiedFactSetBuilder
    from backend.app.powerbi.local_mcp import PowerBILocalMCPClient
    require(Path(sys.modules["backend.app.config.settings"].__file__).resolve().is_relative_to(args.source_root.resolve()), "comparison_source_isolation_failed")
    # Opaque keys deliberately use a per-process HMAC secret. Observe the exact
    # identity inputs only inside the adapter; return its original key unchanged.
    # No raw process/connection identity is printed or persisted. The shared
    # per-run nonce makes this proof private to this manually invoked comparison.
    identity_proofs = {}
    original_key = PowerBILocalMCPClient._desktop_semantic_model_key

    def observe_identity(**identity):
        key = original_key(**identity)
        identity_proofs[key] = digest({"comparison_nonce":args.identity_nonce, "identity":identity})
        return key

    PowerBILocalMCPClient._desktop_semantic_model_key = staticmethod(observe_identity)

    root = args.owned_root
    root.mkdir()
    database = root / "runtime.db"
    settings_kw = dict(llm_mode=LLMMode.OPENAI_COMPATIBLE, powerbi_mode=PowerBIMode.LOCAL_MCP,
        persistence_backend=PersistenceBackend.SQLITE, persistence_database_path=str(database),
        report_artifacts_path=str(root / "reports"), presentation_localization_registry_path=str(root / "display.json"))
    if args.current:
        from backend.app.query_plan.semantic_catalog import DEFAULT_GLOSSARY_PATH, SemanticCatalogBuilder
        from backend.app.query_plan.model_semantic_context import ModelSemanticContextBuilder
        from backend.app.query_plan.model_override import resolve_model_override
        override_path = root / "override.yaml"
        raw = yaml.safe_load(DEFAULT_GLOSSARY_PATH.read_text(encoding="utf-8"))
        override_path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
        settings_kw["powerbi_semantic_override_path"] = str(override_path)
    settings = Settings(**settings_kw)
    require(settings.is_real_ready, "real_not_ready")
    engine = create_engine(settings)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()
    app = create_app(settings)
    signatures, metrics = {}, {}
    owner_registry = ArtifactOwnershipRegistry(root / "ownership.json")
    run_id = "comparison-" + uuid.uuid4().hex
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=180) as client:
            response = await client.get("/api/v1/semantic-models")
            matches = [o for o in response.json().get("items", []) if o.get("selectable") and o.get("display_name") == args.rich_model]
            require(len(matches) == 1, "exact_model_not_unique")
            key = matches[0]["key"]
            require(key in identity_proofs, "desktop_identity_not_observed")
            model_identity = (key, identity_proofs[key])
            service = app.state.turn_service
            if args.current:
                execution = ToolExecutionContext(runtime_mode=RuntimeDataMode.REAL, user=UserContext(allowed_semantic_models=[key]))
                schema = await service.tool_gateway.execute("get_semantic_model_schema", execution, SchemaInput(semantic_model_key=key))
                context = ModelSemanticContextBuilder().build(schema)
                raw["overrides"] = [{"semantic_model_key":key,"runtime_identity":context.runtime_identity,
                    "schema_fingerprint":context.schema_fingerprint,"profile_keys":["desktop_sales_language","desktop_order_language","desktop_calendar_roles","desktop_region_language"]}]
                SemanticCatalogBuilder().build_from_context(context, resolve_model_override(context, raw))
                override_path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")

            captured = {}
            tool = service.tool_gateway._tools["execute_dax"]
            execute = tool.handler

            async def observe(request):
                result = await execute(request)
                captured[result.result_id] = result
                return result

            tool.handler = observe

            async def delete_conversation(identity):
                reply = await client.delete(f"/api/v1/conversations/{identity}", params={"runtime_mode":"real"})
                require(reply.status_code in (200, 404), "cleanup_failed")

            async def delete_report(identity):
                raise RuntimeError("unexpected_report")

            async def probe(run):
                return probe_owned_sqlite_residuals(database, run)

            try:
                async with managed_test_run(owner_registry, test_run_id=run_id, test_namespace=run_id,
                    runtime_mode="real", source_mode="real", delete_conversation=delete_conversation,
                    delete_report=delete_report, residual_probe=probe) as owner:
                    owner.add_sqlite_path(database)

                    async def post(label, question):
                        conversation = str(uuid.uuid4())
                        owner.add_conversation(conversation)
                        reply = await client.post("/api/v1/chat", json={"message":question,"conversation_id":conversation,
                            "request_id":str(uuid.uuid4()),"semantic_model_key":key,"llm_profile_key":"deepseek"})
                        body = reply.json()
                        require(reply.status_code == 200 and body.get("terminal_state") == "completed", label + ":real_turn_failed")
                        audit = body["execution_audit"]
                        result = captured[audit["result_id"]]
                        plan = CanonicalQueryPlan.model_validate(audit["canonical_query_plan"])
                        facts = VerifiedFactSetBuilder().build(plan, result)
                        require(facts.fact_set_id == audit["verified_fact_set_id"], label + ":fact_identity_mismatch")
                        signatures[label] = {"plan":digest(normalized(plan.model_dump(mode="json"), model_identity)),
                            "result":digest(normalized(result.model_dump(mode="json"), model_identity)),
                            "facts":digest(normalized(facts.model_dump(mode="json"), model_identity)),"dax":audit["dax_fingerprint"],
                            "plan_fields":{k:digest(v) for k,v in normalized(plan.model_dump(mode="json"), model_identity).items()},
                            "result_fields":{k:digest(v) for k,v in normalized(result.model_dump(mode="json"), model_identity).items()}}
                        performance = audit["performance"]
                        operations = {}
                        for entry in performance["operations"]:
                            operations[entry["operation"]] = operations.get(entry["operation"], 0) + entry["duration_ms"]
                        metrics[label] = {"total_turn_ms":performance["total_turn_ms"],"operations_ms":operations,
                            "cache_hit_rate":performance["cache_hit_rate"],"session_reuse_rate":performance["session_reuse_rate"]}
                        print(json.dumps({"probe": "current" if args.current else "baseline", "case":label,"completed":True}), flush=True)

                    sequence = ("总销售额是多少？", "2025年5月销售额", "华南区销售额", "每个月销售额趋势")
                    for index, question in enumerate(sequence):
                        await post(f"prime_{index}", question)
                    for index, question in enumerate(("平均订单金额是多少", "总订单数是多少", "我们销售了哪些产品？", "销量最高的是哪款产品？", "2025年8月到2026年1月销售额月趋势")):
                        await post(f"facts_{index}", question)
                    for index, question in enumerate(sequence):
                        await post(f"warm_{index}", question)
                    started = time.perf_counter()
                    await asyncio.gather(*(post(f"concurrent_{index}", question) for index, question in enumerate(sequence)))
                    concurrent_ms = (time.perf_counter()-started)*1000
            finally:
                tool.handler = execute
    print("COMPARISON_RESULT " + json.dumps({"identity_proof":model_identity[1],"signatures":signatures,"metrics":metrics,
        "concurrent_wall_ms":concurrent_ms,"business_residual":0}), flush=True)


def parent(args):
    require(subprocess.check_output(["git","rev-parse",args.baseline], cwd=ROOT, text=True).strip() == args.baseline, "baseline_not_exact_sha")
    with owned_acceptance_tempdir(prefix="powerbiagent-semantic-comparison-") as root:
        source = root / "baseline"
        source.mkdir()
        archive = subprocess.check_output(["git","archive","--format=tar",args.baseline,"backend/app","harness/fixtures"], cwd=ROOT)
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            for member in tar.getmembers():
                target = (source / member.name).resolve()
                require(target.is_relative_to(source) and not member.issym() and not member.islnk(), "unsafe_snapshot_path")
                require(not target.name.startswith(".env"), "snapshot_secret_path")
            tar.extractall(source, filter="data")
        outputs = []
        identity_nonce = uuid.uuid4().hex
        for current, code in ((False, source), (True, ROOT)):
            command = [sys.executable, "-u", str(Path(__file__).resolve()), "--child", "--source-root", str(code),
                "--owned-root", str(root / ("current-run" if current else "baseline-run")), "--rich-model",args.rich_model,
                "--identity-nonce", identity_nonce]
            if current:
                command.append("--current")
            result = None
            # Close pipe/process handles before the owned temp context exits,
            # including an interrupted comparison. Never print provider stderr.
            with subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8") as process:
                try:
                    for line in process.stdout:
                        if line.startswith("COMPARISON_RESULT "):
                            result = json.loads(line.removeprefix("COMPARISON_RESULT "))
                        else:
                            print(line.rstrip(), flush=True)
                    process.wait()
                finally:
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=5)
            # Never dump a provider traceback or response body on failure.
            require(process.returncode == 0 and result is not None, "comparison_child_failed")
            outputs.append(result)
        baseline, current = outputs
        require(baseline["identity_proof"] == current["identity_proof"], "different_desktop_instances")
        differences = [{"case":key,
            "components":[name for name in ("plan","result","facts","dax") if baseline["signatures"][key][name] != current["signatures"][key][name]],
            "plan_fields":[name for name,value in baseline["signatures"][key]["plan_fields"].items() if current["signatures"][key]["plan_fields"].get(name) != value],
            "result_fields":[name for name,value in baseline["signatures"][key]["result_fields"].items() if current["signatures"][key]["result_fields"].get(name) != value]}
            for key in baseline["signatures"] if baseline["signatures"][key] != current["signatures"][key]]
        def warm_mean(output):
            return statistics.mean(v["total_turn_ms"] for k,v in output["metrics"].items() if k.startswith("warm_"))
        summary = {"exact_baseline":args.baseline,"exact_desktop_identity_equal":True,"equal_plan_result_facts_dax_cases":len(current["signatures"])-len(differences), "differences":differences,
            "baseline_warm_mean_ms":warm_mean(baseline),"current_warm_mean_ms":warm_mean(current),
            "baseline_concurrent_4_ms":baseline["concurrent_wall_ms"],"current_concurrent_4_ms":current["concurrent_wall_ms"],
            "baseline_metrics":baseline["metrics"],"current_metrics":current["metrics"],"business_residual":0}
        print(json.dumps(summary), flush=True)
        require(not differences, "baseline_plan_result_fact_or_dax_changed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rich-model", required=True)
    parser.add_argument("--baseline", default="3b811dec214679bb556d4c96506e5e8f536fc5fc")
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--current", action="store_true")
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--owned-root", type=Path)
    parser.add_argument("--identity-nonce")
    args = parser.parse_args()
    try:
        if args.child:
            asyncio.run(child(args))
        else:
            parent(args)
    except Exception as error:
        print(json.dumps({"failed":type(error).__name__,"check":str(error) if type(error) is RuntimeError else "runtime_failure",
            "error_code":getattr(error,"error_code",None),
            "frames":[{"file":Path(frame.filename).name,"line":frame.lineno,"function":frame.name} for frame in traceback.extract_tb(error.__traceback__)]}), flush=True)
        raise SystemExit(1)
