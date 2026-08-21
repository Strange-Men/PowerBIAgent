"""Deterministic application template authority."""

from backend.app.query_plan.template_catalog import (
    DEFAULT_TEMPLATE_CATALOG,
    TemplateCatalog,
    TemplateDefinition,
    TemplateGroundingStatus,
)


def test_canonical_key_and_approved_alias_resolve():
    canonical = DEFAULT_TEMPLATE_CATALOG.ground("生成 sales_report")
    alias = DEFAULT_TEMPLATE_CATALOG.ground("请生成销售报表")
    assert canonical.canonical_key == "sales_report"
    assert canonical.method == "canonical_exact"
    assert alias.canonical_key == "sales_report"
    assert alias.method == "approved_alias_exact"


def test_backend_default_ignores_non_catalog_llm_draft_for_report_intent():
    result = DEFAULT_TEMPLATE_CATALOG.ground(
        "请生成一份报告",
        weak_requested_template="satisfaction",
        required=True,
    )
    assert result.status == TemplateGroundingStatus.RESOLVED
    assert result.canonical_key == "sales_report"
    assert result.method == "backend_default_for_report_intent"
    assert result.weak_signal_disagrees is True


def test_no_template_for_data_question_remains_not_mentioned():
    result = DEFAULT_TEMPLATE_CATALOG.ground("查询销售额", required=False)
    assert result.status == TemplateGroundingStatus.NOT_MENTIONED
    assert result.canonical_key is None


def test_explicit_application_key_is_authoritative():
    result = DEFAULT_TEMPLATE_CATALOG.ground(
        "请生成报告",
        weak_requested_template="satisfaction",
        explicit_template_key="sales_report",
        required=True,
    )
    assert result.status == TemplateGroundingStatus.RESOLVED
    assert result.canonical_key == "sales_report"
    assert result.weak_signal_disagrees is True


def test_legacy_templates_are_known_but_not_m3_available():
    assert DEFAULT_TEMPLATE_CATALOG.allowed_keys == ("sales_report",)
    for key in ("sales_weekly", "satisfaction", "operating_overview"):
        definition = DEFAULT_TEMPLATE_CATALOG.get_definition(key)
        assert definition is not None
        assert definition.allowed is False
        result = DEFAULT_TEMPLATE_CATALOG.ground(
            f"生成 {key}", explicit_template_key=key, required=True
        )
        assert result.status == TemplateGroundingStatus.UNRESOLVED
    mentioned = DEFAULT_TEMPLATE_CATALOG.ground("请生成销售周报", required=True)
    assert mentioned.status == TemplateGroundingStatus.UNRESOLVED
    assert mentioned.method == "disabled_template_mentioned"


def test_ambiguous_and_disabled_templates_fail_closed():
    catalog = TemplateCatalog((
        TemplateDefinition(key="a", aliases=("报告",)),
        TemplateDefinition(key="b", aliases=("报告",)),
        TemplateDefinition(key="disabled", aliases=("停用模板",), allowed=False),
    ))
    ambiguous = catalog.ground("报告", required=True)
    disabled = catalog.ground("停用模板", required=True)
    assert ambiguous.status == TemplateGroundingStatus.CONFIG_CONFLICT
    assert disabled.status == TemplateGroundingStatus.UNRESOLVED


def test_default_must_be_registry_owned_and_allowed():
    definitions = (TemplateDefinition(key="disabled", allowed=False),)
    try:
        TemplateCatalog(definitions, default_key="disabled")
    except ValueError as exc:
        assert str(exc) == "template_catalog_default_not_allowed"
    else:
        raise AssertionError("disabled default must fail closed")
