"""Read-only presentation contracts derived from authoritative artifacts."""

from backend.app.presentation.builder import StructuredPresentationBuilder
from backend.app.presentation.formatter import (
    PresentationFormatKind,
    PresentationFormatter,
)
from backend.app.presentation.localization import (
    BoundedLLMDisplayTranslator,
    DisplayLocalization,
    DisplayLocalizationError,
    DisplayLocalizationService,
    DisplayLocalizationSource,
    JsonDisplayLocalizationRegistry,
)
from backend.app.presentation.models import (
    ChartPresentationBlock,
    MetricPresentationBlock,
    PresentationDataset,
    PresentationEnvelope,
    PresentationField,
    ReportPresentationBlock,
    TablePresentationBlock,
    TextPresentationBlock,
)

__all__ = [
    "ChartPresentationBlock",
    "BoundedLLMDisplayTranslator",
    "DisplayLocalization",
    "DisplayLocalizationError",
    "DisplayLocalizationService",
    "DisplayLocalizationSource",
    "JsonDisplayLocalizationRegistry",
    "MetricPresentationBlock",
    "PresentationDataset",
    "PresentationEnvelope",
    "PresentationField",
    "PresentationFormatKind",
    "PresentationFormatter",
    "ReportPresentationBlock",
    "StructuredPresentationBuilder",
    "TablePresentationBlock",
    "TextPresentationBlock",
]
