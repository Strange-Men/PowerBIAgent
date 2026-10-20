"""Current-turn language hints for Cloud targeted lookup, never semantic authority.

Only the existing SemanticFrame's verbatim literal is transported. The adapter
must still prove model/table/column/value. No Memory, schema, result or token is
stored here; context is task-local and always reset on completion/cancellation.
"""
from contextlib import contextmanager
from contextvars import ContextVar

from backend.app.intent.semantic_interpreter import SemanticFrame


_literals = ContextVar('cloud_explicit_literals', default=None)


@contextmanager
def literal_scope():
    token = _literals.set(())
    try:
        yield
    finally:
        _literals.reset(token)


def capture_frame(message, frame):
    if _literals.get() is None:
        return
    _literals.set(())
    if not isinstance(frame, SemanticFrame) or frame.mode.value not in {'data', 'report'}:
        return
    if not isinstance(message, str):
        return
    hints = []
    represented = set()
    for item in frame.filter_mentions:
        literal = item.member_mention
        represented.add(literal)
        # Weak language is useful only as verbatim current input, never inherited
        # canonical spelling. Any malformed hint drops the whole targeted scope.
        if (not literal or literal not in message or not item.evidence_span
                or item.evidence_span not in message
                or literal not in item.evidence_span
                or (item.field_mention and item.field_mention not in message)):
            return
        hints.append((item.field_mention, literal))
    for literal in frame.member_mentions:
        if literal in represented:
            continue
        if not literal or literal not in message or not any(
            span.slot == 'member' and span.text == literal for span in frame.evidence_spans
        ):
            return
        hints.append((None, literal))
    if len(hints) > 12 or any(len(literal) > 200 for _, literal in hints):
        return
    _literals.set(tuple(hints))


def requested_literals(table, column, *, input_name=None):
    hints = _literals.get() or ()
    names = {column, f'{table}[{column}]', f"'{table}'[{column}]"}
    if input_name:
        names.update({input_name, f'{table}[{input_name}]', f"'{table}'[{input_name}]"})
    return tuple(dict.fromkeys(literal for field,literal in hints if field is None or field in names))


@contextmanager
def grounded_literal_scope(field, catalog, schema):
    """Transport search terms to the field supplied by existing Grounding.

    This callback does not resolve the language field. Searches remain scoped
    to the exact catalog field, and every candidate still requires runtime
    exact member proof followed by the existing Grounding checks.
    """
    from backend.app.query_plan.semantic_catalog import (
        SemanticObjectType)
    from backend.app.query_plan.model_semantic_context import ModelSemanticContextBuilder
    hints = _literals.get()
    valid = (
        hints is not None and not catalog.schema_drift
        and catalog.semantic_model_key == schema.key
        and catalog.schema_fingerprint == ModelSemanticContextBuilder().build(schema).schema_fingerprint
        and field.object_type == SemanticObjectType.FIELD
        and catalog.get(field.object_id) == field
        and any(t.name == field.table_name and any(
            c.name == field.canonical_name and c.data_type == field.data_type
            for c in t.columns) for t in schema.tables)
    )
    token = _literals.set(tuple(
        (f'{field.table_name}[{field.canonical_name}]', literal)
        for _, literal in hints) if valid else hints)
    try:
        yield
    finally:
        _literals.reset(token)
