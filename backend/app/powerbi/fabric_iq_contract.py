"""Pinned required capabilities; runtime inventory remains the authority."""
import hashlib
import json
from importlib.metadata import version

from backend.app.powerbi.base import PowerBIAdapterError

PUBLIC_ENDPOINT = "https://fabriciq.svc.cloud.microsoft/v1/mcp/fabriciq"
PRIVATE_ENDPOINT = "https://api.fabric.microsoft.com/v1/mcp/fabriciq"
VARIANT = "Fabric.Routing.FabricIQ.V1"
REQUIRED = {
    "ResolveFabricItem": {"fabricItemId": "string"},
    "GetSemanticModelSchema": {"artifactId": "string"},
    "ExecuteQuery": {"artifactId": "string", "daxQueries": "array"},
}
RESPONSE_EXPECTATIONS = {
    "ResolveFabricItem": "SemanticModel;fabricItemId+workspaceId",
    "GetSemanticModelSchema": "semanticModel.ArtifactId;schema.Tables;unknown-metadata",
    "ExecuteQuery": "semanticModel.ArtifactId;executionResult.tables[1];columns;positional-rows;fail-closed-completeness",
}


def fail(code: str) -> PowerBIAdapterError:
    return PowerBIAdapterError(code, provider="fabric_iq", error_type=code,
                               retryable=code in {"QUERY_TIMEOUT", "RATE_LIMITED", "UPSTREAM_UNAVAILABLE"})


def validate_endpoint(endpoint: str) -> str:
    if endpoint not in {PUBLIC_ENDPOINT, PRIVATE_ENDPOINT}:
        raise ValueError("Fabric IQ endpoint must match an official allowlisted endpoint")
    return endpoint


def _types(field):
    if not isinstance(field, dict): return set()
    value = field.get("type")
    if isinstance(value, str): return {value}
    if isinstance(value, list) and all(isinstance(v, str) for v in value): return set(value)
    if isinstance(field.get("anyOf"), list):
        return set().union(*(_types(v) for v in field["anyOf"]))
    return set()


def capability_fingerprint(tools: list[dict]) -> str:
    if not isinstance(tools, list): raise fail("CONTRACT_DRIFT")
    inventory = {}
    for tool in tools:
        name = tool.get("name") if isinstance(tool, dict) else None
        if not isinstance(name, str) or name in inventory: raise fail("CONTRACT_DRIFT")
        inventory[name] = tool
    canonical = {}
    for name, fields in REQUIRED.items():
        schema = inventory.get(name, {}).get("inputSchema", {})
        props, required = schema.get("properties", {}), schema.get("required", [])
        if (schema.get("type") != "object" or not isinstance(props, dict)
                or not isinstance(required, list) or set(required) != set(fields)):
            raise fail("CONTRACT_DRIFT")
        for field, kind in fields.items():
            if _types(props.get(field)) != {kind}: raise fail("CONTRACT_DRIFT")
            if kind == "array" and _types(props[field].get("items")) != {"string"}:
                raise fail("CONTRACT_DRIFT")
        if name == "ExecuteQuery":
            if _types(props.get("maxRows")) not in ({"integer"}, {"integer", "null"}):
                raise fail("CONTRACT_DRIFT")
        canonical[name] = {"required": fields, "response": RESPONSE_EXPECTATIONS[name]}
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def safe_capability_evidence(fingerprint, endpoint):
    return {"fingerprint": fingerprint, "client_version": version("mcp"),
            "selector": VARIANT, "endpoint_category": "public" if endpoint == PUBLIC_ENDPOINT else "private_link"}
