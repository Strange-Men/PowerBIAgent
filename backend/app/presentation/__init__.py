"""Read-only presentation contracts derived from authoritative artifacts."""

from backend.app.presentation.builder import StructuredPresentationBuilder
from backend.app.presentation.models import (
    ChartPresentationBlock,
    MetricPresentationBlock,
    PresentationDataset,
    PresentationEnvelope,
    ReportPresentationBlock,
    TablePresentationBlock,
    TextPresentationBlock,
)

__all__ = [
    "ChartPresentationBlock",
    "MetricPresentationBlock",
    "PresentationDataset",
    "PresentationEnvelope",
    "ReportPresentationBlock",
    "StructuredPresentationBuilder",
    "TablePresentationBlock",
    "TextPresentationBlock",
]
