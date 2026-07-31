"""M0.2 意图识别单元测试

测试：
1. IntentSpec 合法模型
2. 四类 Intent 枚举
3. IntentSpec 非法 confidence
"""

import pytest
from pydantic import ValidationError

from backend.app.intent.models import IntentType, IntentSpec


class TestIntentType:
    """四类 Intent 枚举测试"""

    def test_data_question_value(self):
        assert IntentType.DATA_QUESTION.value == "data_question"

    def test_report_generation_value(self):
        assert IntentType.REPORT_GENERATION.value == "report_generation"

    def test_clarification_value(self):
        assert IntentType.CLARIFICATION.value == "clarification"

    def test_unsupported_value(self):
        assert IntentType.UNSUPPORTED.value == "unsupported"

    def test_all_four_intents_present(self):
        values = {e.value for e in IntentType}
        assert values == {"data_question", "report_generation", "clarification", "unsupported"}


class TestIntentSpecValid:
    """IntentSpec 合法模型测试"""

    def test_minimal_data_question(self):
        spec = IntentSpec(
            intent=IntentType.DATA_QUESTION,
            confidence=0.95,
            normalized_question="本月销售额是多少？",
        )
        assert spec.intent == IntentType.DATA_QUESTION
        assert spec.confidence == 0.95
        assert spec.detected_measures == []
        assert spec.needs_clarification is False

    def test_full_data_question(self):
        spec = IntentSpec(
            intent=IntentType.DATA_QUESTION,
            confidence=0.92,
            normalized_question="华南区域本月销售额",
            detected_measures=["销售额"],
            detected_dimensions=["区域"],
            detected_filters=[{"field": "区域", "op": "eq", "value": "华南"}],
            detected_time_range="本月",
        )
        assert spec.detected_measures == ["销售额"]
        assert spec.detected_filters[0]["value"] == "华南"

    def test_clarification_intent(self):
        spec = IntentSpec(
            intent=IntentType.CLARIFICATION,
            confidence=0.60,
            normalized_question="帮我看看数据",
            needs_clarification=True,
            clarification_question="请问您想查看哪个指标？",
        )
        assert spec.intent == IntentType.CLARIFICATION
        assert spec.needs_clarification is True
        assert spec.clarification_question is not None

    def test_unsupported_intent(self):
        spec = IntentSpec(
            intent=IntentType.UNSUPPORTED,
            confidence=0.98,
            normalized_question="删除所有数据",
            unsupported_reason="该操作不在允许范围内",
        )
        assert spec.intent == IntentType.UNSUPPORTED
        assert spec.unsupported_reason == "该操作不在允许范围内"

    def test_report_generation_intent(self):
        spec = IntentSpec(
            intent=IntentType.REPORT_GENERATION,
            confidence=0.90,
            normalized_question="生成销售周报",
            detected_measures=["销售额"],
            requested_template="销售周报模板",
        )
        assert spec.intent == IntentType.REPORT_GENERATION
        assert spec.requested_template == "销售周报模板"

    def test_multi_round_inheritance(self):
        """多轮追问：继承已有指标和时间，只替换区域筛选"""
        spec = IntentSpec(
            intent=IntentType.DATA_QUESTION,
            confidence=0.93,
            normalized_question="只看华南",
            inherited_context="继承已提交记忆：指标=[销售额]，时间范围=本月",
            detected_measures=["销售额"],
            detected_filters=[{"field": "区域", "op": "eq", "value": "华南"}],
            detected_time_range="本月",
        )
        assert spec.inherited_context is not None
        assert "销售额" in spec.inherited_context


class TestIntentSpecInvalid:
    """IntentSpec 非法场景测试"""

    def test_confidence_below_zero(self):
        with pytest.raises(ValidationError):
            IntentSpec(
                intent=IntentType.DATA_QUESTION,
                confidence=-0.1,
                normalized_question="test",
            )

    def test_confidence_above_one(self):
        with pytest.raises(ValidationError):
            IntentSpec(
                intent=IntentType.DATA_QUESTION,
                confidence=1.5,
                normalized_question="test",
            )

    def test_empty_normalized_question(self):
        with pytest.raises(ValidationError):
            IntentSpec(
                intent=IntentType.DATA_QUESTION,
                confidence=0.5,
                normalized_question="",
            )

    def test_unsupported_without_reason(self):
        with pytest.raises(ValidationError):
            IntentSpec(
                intent=IntentType.UNSUPPORTED,
                confidence=0.9,
                normalized_question="bad request",
                unsupported_reason=None,
            )

    def test_unsupported_with_reason_is_valid(self):
        """验证 unsupported 带 reason 是合法的"""
        spec = IntentSpec(
            intent=IntentType.UNSUPPORTED,
            confidence=0.9,
            normalized_question="bad request",
            unsupported_reason="不支持该操作",
        )
        assert spec.intent == IntentType.UNSUPPORTED
