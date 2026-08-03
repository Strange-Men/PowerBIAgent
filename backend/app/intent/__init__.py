"""意图识别模块 — M1.2"""

from backend.app.intent.context import IntentContextSnapshot
from backend.app.intent.models import FilterOperator, FilterSpec, IntentSpec, IntentType
from backend.app.intent.service import IntentRecognitionError, IntentService

__all__ = [
    "FilterOperator",
    "FilterSpec",
    "IntentContextSnapshot",
    "IntentRecognitionError",
    "IntentService",
    "IntentSpec",
    "IntentType",
]
