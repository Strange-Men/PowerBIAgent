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


def test_report_intent_without_explicit_template_fails_closed():
    result = DEFAULT_TEMPLATE_CATALOG.ground(
        "请生成 sales_report 销售报告",
        weak_requested_template="satisfaction",
        required=True,
    )
    assert result.status == TemplateGroundingStatus.UNRESOLVED
    assert result.canonical_key is None
    assert result.candidate_keys == ()
    assert result.method == "required_template_missing"
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


def test_unknown_or_disabled_explicit_template_fails_closed():
    for key in ("stale_template", "sales_weekly"):
        result = DEFAULT_TEMPLATE_CATALOG.ground(
            "请生成报告",
            explicit_template_key=key,
            required=True,
        )
        assert result.status == TemplateGroundingStatus.UNRESOLVED
        assert result.canonical_key is None
        assert result.method == "explicit_key_not_allowed"


def test_legacy_templates_are_not_registered_as_production_templates():
    assert DEFAULT_TEMPLATE_CATALOG.allowed_keys == ("sales_report",)
    for key in ("sales_weekly", "satisfaction", "operating_overview"):
        definition = DEFAULT_TEMPLATE_CATALOG.get_definition(key)
        assert definition is None
        result = DEFAULT_TEMPLATE_CATALOG.ground(
            f"生成 {key}", explicit_template_key=key, required=True
        )
        assert result.status == TemplateGroundingStatus.UNRESOLVED
    mentioned = DEFAULT_TEMPLATE_CATALOG.ground("请生成销售周报", required=False)
    assert mentioned.status == TemplateGroundingStatus.NOT_MENTIONED


def test_ambiguous_and_disabled_templates_fail_closed():
    catalog = TemplateCatalog((
        TemplateDefinition(key="a", aliases=("报告",)),
        TemplateDefinition(key="b", aliases=("报告",)),
        TemplateDefinition(key="disabled", aliases=("停用模板",), allowed=False),
    ))
    ambiguous = catalog.ground("报告", required=False)
    disabled = catalog.ground("停用模板", required=False)
    assert ambiguous.status == TemplateGroundingStatus.CONFIG_CONFLICT
    assert disabled.status == TemplateGroundingStatus.UNRESOLVED


def test_catalog_forbids_implicit_default_even_when_registry_owned():
    definitions = (TemplateDefinition(key="simple"),)
    try:
        TemplateCatalog(definitions, default_key="simple")
    except ValueError as exc:
        assert str(exc) == "template_catalog_default_forbidden"
    else:
        raise AssertionError("implicit report-template defaults must be forbidden")
