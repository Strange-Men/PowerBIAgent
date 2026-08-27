"""Report template and renderer registry authority tests."""

from __future__ import annotations

import pytest

from backend.app.report.base import ReportRenderer
from backend.app.report.registry import (
    ReportRendererDispatcher,
    ReportRendererRegistry,
    ReportTemplateAvailability,
    ReportTemplateDescriptor,
    ReportTemplateRegistry,
    ReportTemplateUnavailableError,
)
from backend.app.schemas.data_contracts import ReportSpec


class _RecordingRenderer(ReportRenderer):
    def __init__(self) -> None:
        self.calls: list[str] = []

    @property
    def supported_templates(self) -> list[str]:
        return ["simple"]

    async def render(self, report: ReportSpec) -> str:
        self.calls.append(report.template_key)
        return "<!DOCTYPE html><html><body>ok</body></html>"


def _descriptor(
    template_key: str = "simple",
    *,
    renderer_key: str = "simple_renderer",
    availability: ReportTemplateAvailability = ReportTemplateAvailability.AVAILABLE,
) -> ReportTemplateDescriptor:
    return ReportTemplateDescriptor(
        template_key=template_key,
        display_name="简易模板",
        description="适合快速查看关键指标、趋势与分类明细",
        renderer_key=renderer_key,
        availability=availability,
        aliases=("简易报表",),
    )


@pytest.mark.asyncio
async def test_known_template_dispatches_through_both_registries():
    renderer = _RecordingRenderer()
    dispatcher = ReportRendererDispatcher(
        template_registry=ReportTemplateRegistry((_descriptor(),)),
        renderer_registry=ReportRendererRegistry((("simple_renderer", renderer),)),
    )

    html = await dispatcher.render(ReportSpec(title="报告", template_key="simple"))

    assert html.endswith("</html>")
    assert renderer.calls == ["simple"]
    assert dispatcher.supported_templates == ["simple"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("descriptor", "template_key"),
    [
        (None, "unknown"),
        (
            _descriptor(availability=ReportTemplateAvailability.UNAVAILABLE),
            "simple",
        ),
        (_descriptor(renderer_key="missing_renderer"), "simple"),
    ],
)
async def test_unknown_unavailable_or_stale_dispatch_fails_without_fallback(
    descriptor,
    template_key,
):
    renderer = _RecordingRenderer()
    dispatcher = ReportRendererDispatcher(
        template_registry=ReportTemplateRegistry(
            (descriptor,) if descriptor is not None else (_descriptor(),)
        ),
        renderer_registry=ReportRendererRegistry((("simple_renderer", renderer),)),
    )

    with pytest.raises(ReportTemplateUnavailableError):
        await dispatcher.render(ReportSpec(title="报告", template_key=template_key))
    assert renderer.calls == []


def test_duplicate_template_and_renderer_keys_are_rejected():
    with pytest.raises(ValueError, match="report_template_registry_duplicate_key"):
        ReportTemplateRegistry((_descriptor(), _descriptor()))

    renderer = _RecordingRenderer()
    with pytest.raises(ValueError, match="report_renderer_registry_duplicate_key"):
        ReportRendererRegistry(
            (("simple_renderer", renderer), ("simple_renderer", renderer))
        )


def test_registries_have_no_default_or_first_item_fallback():
    templates = ReportTemplateRegistry((_descriptor(),))
    renderers = ReportRendererRegistry(
        (("simple_renderer", _RecordingRenderer()),)
    )

    assert not hasattr(templates, "default")
    assert not hasattr(renderers, "default")
    with pytest.raises(ReportTemplateUnavailableError):
        templates.require_available("")
    with pytest.raises(ReportTemplateUnavailableError):
        renderers.require("unknown_renderer")
