"""意图识别模块 — M1.2"""

from backend.app.intent.context import IntentContextSnapshot
from backend.app.intent.models import FilterOperator, FilterSpec, IntentSpec, IntentType
from backend.app.intent.question_router import (
    CalculatorError,
    QuestionRoute,
    QuestionRouter,
    QuestionRoutingDecision,
    QueryShape,
    SafeCalculator,
)
from backend.app.intent.service import IntentRecognitionError, IntentService

__all__ = [
    "CalculatorError",
    "FilterOperator",
    "FilterSpec",
    "IntentContextSnapshot",
    "IntentRecognitionError",
    "IntentService",
    "IntentSpec",
    "IntentType",
    "QuestionRoute",
    "QuestionRouter",
    "QuestionRoutingDecision",
    "QueryShape",
    "SafeCalculator",
]
