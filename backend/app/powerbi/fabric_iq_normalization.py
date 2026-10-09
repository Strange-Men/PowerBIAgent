"""Strict Fabric wire normalization. Never infer business or security metadata."""
import base64
import csv
import io
import json
import math
from functools import wraps
from uuid import UUID

from backend.app.powerbi.fabric_iq_contract import fail
from backend.app.schemas.data_contracts import (
    ColumnSchema, MeasureSchema, QueryResult, SemanticModelSchema, TableSchema,
)
from backend.app.powerbi.base import PowerBIAdapterError


def safe_normalization(function):
    @wraps(function)
    def normalized(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except PowerBIAdapterError:
            raise
        except Exception:
            raise fail("CONTRACT_DRIFT") from None
    return normalized


def guid(value):
    try:
        if not isinstance(value, str) or str(UUID(value)) != value.lower(): raise ValueError()
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise fail("CONTRACT_DRIFT") from None


def error_code(raw, default="UPSTREAM_UNAVAILABLE"):
    if not isinstance(raw, dict): return default
    error = raw.get("Error", raw.get("error", raw))
    if not isinstance(error, dict): return default
    status = error.get("HttpStatusCode", error.get("status"))
    return {401: "AUTH_EXPIRED", 403: "RESOURCE_NOT_ACCESSIBLE", 404: "RESOURCE_NOT_ACCESSIBLE",
            429: "RATE_LIMITED", 408: "QUERY_TIMEOUT", 504: "QUERY_TIMEOUT",
            502: "UPSTREAM_UNAVAILABLE", 503: "UPSTREAM_UNAVAILABLE"}.get(status, default)


def _reject_errors(value, default):
    if not isinstance(value, dict): raise fail("CONTRACT_DRIFT")
    if value.get("isError") is True or value.get("is_error") is True:
        raise fail(error_code(value, default))
    for key in ("Error", "error", "errors"):
        if key in value and value[key] not in (None, [], {}):
            raise fail(error_code(value, default))
    if "Status" in value and str(value["Status"]).lower() not in {"success", "succeeded", "ok"}:
        raise fail(error_code(value, default))


def unpack(raw, default):
    """Accept SDK DTO or fixture; embedded resources are consumed, never fetched."""
    if hasattr(raw, "model_dump"):
        raw = raw.model_dump(mode="json", by_alias=True, exclude_none=True)
    _reject_errors(raw, default)
    if "content" not in raw: return raw, None
    content = raw["content"]
    if not isinstance(content, list): raise fail("CONTRACT_DRIFT")
    payloads, resources, citation = [], [], None
    structured = raw.get("structuredContent", raw.get("structured_content"))
    if structured is not None:
        if not isinstance(structured, dict): raise fail("CONTRACT_DRIFT")
        _reject_errors(structured, default)
        if "artifact_citation" in structured and not any(
                key in structured for key in ("schema", "semanticModel", "executionResult")):
            # Runtime structuredContent may contain a citation, while text owns
            # the actual schema/result. A citation alone never grants access.
            citation = structured["artifact_citation"]
            _reject_errors(citation, default)
        else:
            payloads.append(structured)
    for block in content:
        if not isinstance(block, dict): raise fail("CONTRACT_DRIFT")
        if block.get("type") == "text":
            try: value = json.loads(block.get("text", ""))
            except (ValueError, TypeError): raise fail(default) from None
            if not isinstance(value, dict): raise fail("CONTRACT_DRIFT")
            payloads.append(value)
        elif block.get("type") == "resource":
            resource = block.get("resource", {})
            mime = resource.get("mimeType", resource.get("mime_type", ""))
            if mime.split(";", 1)[0] != "text/csv": raise fail("CONTRACT_DRIFT")
            if "text" in resource and "blob" in resource: raise fail("CONTRACT_DRIFT")
            try:
                data = resource["text"] if "text" in resource else base64.b64decode(resource["blob"], validate=True).decode("utf-8")
                if not isinstance(data, str): raise ValueError()
            except (KeyError, ValueError, TypeError, UnicodeError): raise fail("CONTRACT_DRIFT") from None
            resources.append(data)
        else:
            raise fail("CONTRACT_DRIFT")
    if not payloads or len(resources) > 1: raise fail("CONTRACT_DRIFT")
    # SDK structured and text mirrors must agree; no arbitrary success selection.
    if any(p != payloads[0] for p in payloads[1:]): raise fail("CONTRACT_DRIFT")
    _reject_errors(payloads[0], default)
    if citation is not None:
        model = payloads[0].get("semanticModel")
        if not isinstance(model, dict) or guid(citation.get("ArtifactId")) != guid(model.get("ArtifactId")):
            raise fail("CONTRACT_DRIFT")
        # Icons/descriptions/links are optional presentation metadata, not
        # identity or query authority; runtime may vary them between envelopes.
        if "Name" in citation and "Name" in model and citation["Name"] != model["Name"]:
            raise fail("CONTRACT_DRIFT")
    return payloads[0], resources[0] if resources else None


def identity(payload, expected):
    model = payload.get("semanticModel")
    if not isinstance(model, dict) or guid(model.get("ArtifactId")) != expected:
        raise fail("CONTRACT_DRIFT")
    return model


def _name(value):
    if not isinstance(value, str) or not value.strip() or any(not c.isprintable() for c in value):
        raise fail("CONTRACT_DRIFT")
    return value


@safe_normalization
def normalize_schema(raw, model_id, key, epoch):
    payload, resource = unpack(raw, "SCHEMA_UNAVAILABLE")
    if resource is not None: raise fail("CONTRACT_DRIFT")
    model = identity(payload, model_id)
    definition = payload.get("schema")
    if not isinstance(definition, dict): raise fail("SCHEMA_UNAVAILABLE")
    tables, relations = definition.get("Tables"), definition.get("ActiveRelationships", [])
    if not isinstance(tables, list) or not tables or not isinstance(relations, list):
        raise fail("SCHEMA_UNAVAILABLE")
    normalized, names = [], set()
    for table in tables:
        if not isinstance(table, dict): raise fail("SCHEMA_UNAVAILABLE")
        name = _name(table.get("Name"))
        if name in names: raise fail("CONTRACT_DRIFT")
        names.add(name)
        columns, measures = table.get("Columns", []), table.get("Measures", [])
        if not isinstance(columns, list) or not isinstance(measures, list): raise fail("SCHEMA_UNAVAILABLE")
        cn, mn, column_dtos, measure_dtos = set(), set(), [], []
        for column in columns:
            if not isinstance(column, dict): raise fail("SCHEMA_UNAVAILABLE")
            cname, ctype = _name(column.get("Name")), _name(column.get("Type"))
            if cname in cn: raise fail("CONTRACT_DRIFT")
            cn.add(cname)
            column_dtos.append(ColumnSchema(name=cname, data_type=ctype, is_hidden=None,
                is_system_managed=None, is_key=None, description=column.get("Description"),
                format_string=column.get("FormatString")))
        for measure in measures:
            if not isinstance(measure, dict): raise fail("SCHEMA_UNAVAILABLE")
            mname = _name(measure.get("Name"))
            if mname in mn: raise fail("CONTRACT_DRIFT")
            mn.add(mname)
            measure_dtos.append(MeasureSchema(name=mname, data_type=measure.get("Type"),
                expression=None, is_hidden=None, is_system_managed=None,
                format_string=measure.get("FormatString"), description=measure.get("Description")))
        normalized.append(TableSchema(name=name, columns=column_dtos, measures=measure_dtos,
            is_hidden=None, is_system_managed=None, description=table.get("Description")))
    relationship_evidence = []
    for relation in relations:
        if not isinstance(relation, dict): raise fail("SCHEMA_UNAVAILABLE")
        # PK/FK strings prove raw endpoints, not cardinality, direction or Core orientation.
        if not all(isinstance(relation.get(k), str) and relation[k] for k in ("PK", "FK")):
            raise fail("SCHEMA_UNAVAILABLE")
        direction = relation.get("UnidirectionalFilter")
        if direction is not None and not isinstance(direction, str): raise fail("SCHEMA_UNAVAILABLE")
        relationship_evidence.append({"PK": relation["PK"], "FK": relation["FK"],
                                      "UnidirectionalFilter": direction})
    return SemanticModelSchema(name=_name(model.get("Name")), key=key, tables=normalized,
        relationships=[], metadata_source="fabric_iq", session_generation=epoch,
        provider_metadata={"active_relationships": relationship_evidence,
            "unknown": ["hidden", "system_managed", "expression", "hierarchies", "cardinality",
                "relationship_direction", "security", "refresh_time"],
            "relationship_mapping": "NOT_VERIFIED"})


def _cell(value):
    if value is None or isinstance(value, (str, bool, int)): return value
    if isinstance(value, float) and math.isfinite(value): return value
    raise fail("CONTRACT_DRIFT")


def _csv_cell(value, kind):
    kind = kind.lower()
    if kind in {"string", "datetime", "date", "time"}: return value
    if value == "": return None
    try:
        if kind in {"int64", "int32", "integer", "long"}:
            if not __import__('re').fullmatch(r"-?\d+", value): raise ValueError()
            return int(value)
        if kind in {"double", "decimal", "float", "currency"}: return _cell(float(value))
        if kind in {"boolean", "bool"} and value.lower() in {"true", "false"}: return value.lower() == "true"
    except (ValueError, OverflowError): pass
    raise fail("CONTRACT_DRIFT")


@safe_normalization
def normalize_query(raw, model_id, request):
    payload, embedded_csv = unpack(raw, "QUERY_REJECTED")
    identity(payload, model_id)
    execution = payload.get("executionResult")
    _reject_errors(execution, "QUERY_REJECTED")
    tables = execution.get("tables")
    if not isinstance(tables, list) or len(tables) != 1: raise fail("CONTRACT_DRIFT")
    table = tables[0]
    _reject_errors(table, "QUERY_REJECTED")
    columns, rows = table.get("columns"), table.get("rows")
    if not isinstance(columns, list) or not columns or not isinstance(rows, list): raise fail("CONTRACT_DRIFT")
    names, types = [], []
    for column in columns:
        if not isinstance(column, dict): raise fail("CONTRACT_DRIFT")
        names.append(_name(column.get("name")))
        types.append(_name(column.get("type")))
    if len(names) != len(set(names)): raise fail("CONTRACT_DRIFT")
    for row in rows:
        if not isinstance(row, list) or len(row) != len(names): raise fail("CONTRACT_DRIFT")
        for cell in row: _cell(cell)
    if embedded_csv is not None:
        try:
            parsed = list(csv.reader(io.StringIO(embedded_csv, newline=""), strict=True))
        except (csv.Error, UnicodeError): raise fail("CONTRACT_DRIFT") from None
        if not parsed or parsed[0] != names: raise fail("CONTRACT_DRIFT")
        csv_rows = []
        for row in parsed[1:]:
            if len(row) != len(names): raise fail("CONTRACT_DRIFT")
            csv_rows.append([_csv_cell(value, kind) for value, kind in zip(row, types)])
        if csv_rows[:len(rows)] != rows: raise fail("CONTRACT_DRIFT")
        rows = csv_rows
    flags = []
    for obj in (payload, execution, table):
        for field in ("columnCount", "column_count"):
            if field in obj and (type(obj[field]) is not int or obj[field] != len(names)):
                raise fail("CONTRACT_DRIFT")
        for field in ("rowCount", "row_count"):
            if field in obj and (type(obj[field]) is not int or obj[field] != len(rows)):
                raise fail("CONTRACT_DRIFT")
        for field in ("truncated", "isTruncated", "hasMore"):
            if field in obj:
                if type(obj[field]) is not bool: raise fail("CONTRACT_DRIFT")
                flags.append(obj[field])
        if "complete" in obj:
            if type(obj["complete"]) is not bool: raise fail("CONTRACT_DRIFT")
            flags.append(not obj["complete"])
        if "totalRows" in obj:
            count = obj["totalRows"]
            if type(count) is not int or count < len(rows): raise fail("CONTRACT_DRIFT")
            if count > len(rows): flags.append(True)
    if flags and len(set(flags)) != 1: raise fail("CONTRACT_DRIFT")
    # No undocumented row limit is invented. Unknown is conservatively incomplete.
    if len(rows) > request.max_rows: raise fail("CONTRACT_DRIFT")
    # V1 has no verified complete-response semantic in official/runtime evidence.
    # Even an additive 'truncated:false' field cannot silently grant that authority.
    truncated = True
    # REST limits aren't IQ guarantees, but reaching them can never prove complete.
    if len(rows) >= 100000 or len(rows) * len(names) >= 1000000:
        truncated = True
    return QueryResult(semantic_model_key=request.semantic_model_key, columns=names, rows=rows,
        row_count=len(rows), source_mode="real", request_id=request.request_id, truncated=truncated)
