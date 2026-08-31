"""Explicit activation of migrated language profiles for isolated test models.

Only test setup constructs approvals for synthetic identities. Production never
imports this helper and never auto-approves a fingerprint at request time.
"""

from backend.app.query_plan.model_semantic_context import ModelSemanticContextBuilder
from backend.app.query_plan.semantic_catalog import SemanticCatalogBuilder


def bound_registry(schema, profile_keys):
    registry = SemanticCatalogBuilder()._load_glossary()
    context = ModelSemanticContextBuilder().build(schema)
    registry["overrides"] = [{
        "semantic_model_key": context.semantic_model_key,
        "runtime_identity": context.runtime_identity,
        "schema_fingerprint": context.schema_fingerprint,
        "profile_keys": list(profile_keys),
    }]
    return registry


def activate_registry(monkeypatch, registry):
    monkeypatch.setattr(SemanticCatalogBuilder, "_load_glossary", lambda self: registry)
