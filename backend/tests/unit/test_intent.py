"""M0.2+ 意图识别单元测试

测试：
1. IntentSpec 合法模型（含 FilterSpec）
2. 四类 Intent 枚举
3. IntentSpec 跨字段一致性规则
4. IntentSpec 非法 confidence
5. FilterSpec 结构化筛选
"""

import pytest
from pydantic import ValidationError

from backend.app.intent.models import (
    FilterOperator,
    FilterSpec,
    IntentType,
    IntentSpec,
)
from backend.app.intent.unsupported_policy import (
    should_defer_unsupported_to_grounding,
)


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


class TestFilterSpec:
    """FilterSpec 结构化筛选模型测试"""

    def test_filter_spec_string_value(self):
        f = FilterSpec(field="Region", operator=FilterOperator.EQ, value="华南")
        assert f.field == "Region"
        assert f.operator == FilterOperator.EQ
        assert f.value == "华南"

    def test_filter_spec_numeric_value(self):
        f = FilterSpec(field="SalesAmount", operator=FilterOperator.GT, value=10000)
        assert f.value == 10000

    def test_filter_spec_bool_value(self):
        f = FilterSpec(field="IsActive", operator=FilterOperator.EQ, value=True)
        assert f.value is True

    def test_filter_spec_default_operator(self):
        f = FilterSpec(field="Region", value="华北")
        assert f.operator == FilterOperator.EQ

    def test_filter_spec_to_legacy_dict(self):
        f = FilterSpec(field="Region", operator=FilterOperator.EQ, value="华南")
        d = f.to_legacy_dict()
        assert d == {"field": "Region", "operator": "eq", "value": "华南"}

    def test_filter_spec_empty_field_raises(self):
        with pytest.raises(ValidationError):
            FilterSpec(field="", value="华南")


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
            detected_filters=[FilterSpec(field="区域", value="华南")],
            detected_time_range="本月",
        )
        assert spec.detected_measures == ["销售额"]
        assert spec.detected_filters[0].value == "华南"

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
            requested_template="sales_weekly",
        )
        assert spec.intent == IntentType.REPORT_GENERATION
        assert spec.requested_template == "sales_weekly"

    def test_multi_round_inheritance(self):
        """多轮追问：继承已有指标和时间，只替换区域筛选"""
        spec = IntentSpec(
            intent=IntentType.DATA_QUESTION,
            confidence=0.93,
            normalized_question="只看华南",
            inherited_context="继承已提交记忆：指标=[销售额]，时间范围=本月",
            detected_measures=["销售额"],
            detected_filters=[FilterSpec(field="区域", value="华南")],
            detected_time_range="本月",
        )
        assert spec.inherited_context is not None
        assert "销售额" in spec.inherited_context

    def test_structured_inherited_context_is_ignored(self):
        """LLM diagnostics cannot become an alternate semantic state channel."""
        spec = IntentSpec(
            intent=IntentType.DATA_QUESTION,
            confidence=0.93,
            normalized_question="只看华南",
            inherited_context={"measures": ["销售额"]},  # type: ignore[arg-type]
        )

        assert spec.inherited_context is None

    def test_structured_detected_time_is_ignored(self):
        spec = IntentSpec(
            intent=IntentType.DATA_QUESTION,
            confidence=0.93,
            normalized_question="改成今年",
            detected_time_range={  # type: ignore[arg-type]
                "date_field": "InventedDate",
                "mode": "current_year",
            },
        )

        assert spec.detected_time_range is None


class TestIntentSpecCrossField:
    """跨字段一致性规则测试"""

    def test_clarification_must_have_needs_clarification(self):
        """clarification 必须有 needs_clarification=True"""
        with pytest.raises(ValidationError):
            IntentSpec(
                intent=IntentType.CLARIFICATION,
                confidence=0.60,
                normalized_question="帮我看看数据",
                needs_clarification=False,
            )

    def test_clarification_must_have_question(self):
        """clarification 必须有非空 clarification_question"""
        with pytest.raises(ValidationError):
            IntentSpec(
                intent=IntentType.CLARIFICATION,
                confidence=0.60,
                normalized_question="帮我看看数据",
                needs_clarification=True,
                clarification_question=None,
            )

    def test_clarification_question_not_blank(self):
        """clarification_question 不能为空字符串"""
        with pytest.raises(ValidationError):
            IntentSpec(
                intent=IntentType.CLARIFICATION,
                confidence=0.60,
                normalized_question="帮我看看数据",
                needs_clarification=True,
                clarification_question="   ",
            )

    def test_non_clarification_no_needs_clarification(self):
        """非 clarification 不应携带 needs_clarification=True"""
        with pytest.raises(ValidationError):
            IntentSpec(
                intent=IntentType.DATA_QUESTION,
                confidence=0.80,
                normalized_question="销售额",
                needs_clarification=True,
            )

    def test_unsupported_must_have_reason(self):
        """unsupported 必须有 unsupported_reason"""
        with pytest.raises(ValidationError):
            IntentSpec(
                intent=IntentType.UNSUPPORTED,
                confidence=0.90,
                normalized_question="bad request",
                unsupported_reason=None,
            )

    def test_non_unsupported_no_reason(self):
        """非 unsupported 不应携带拒绝原因"""
        with pytest.raises(ValidationError):
            IntentSpec(
                intent=IntentType.DATA_QUESTION,
                confidence=0.80,
                normalized_question="销售额",
                unsupported_reason="不应该有原因",
            )

    def test_normalized_question_not_blank(self):
        """normalized_question 去除纯空格后不能为空"""
        with pytest.raises(ValidationError):
            IntentSpec(
                intent=IntentType.DATA_QUESTION,
                confidence=0.50,
                normalized_question="   ",
            )


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

    def test_unsupported_with_reason_is_valid(self):
        """验证 unsupported 带 reason 是合法的"""
        spec = IntentSpec(
            intent=IntentType.UNSUPPORTED,
            confidence=0.9,
            normalized_question="bad request",
            unsupported_reason="不支持该操作",
        )
        assert spec.intent == IntentType.UNSUPPORTED


class TestUnsupportedRoutingPolicy:
    @staticmethod
    def _intent(**updates) -> IntentSpec:
        values = {
            "intent": IntentType.UNSUPPORTED,
            "confidence": 0.8,
            "normalized_question": "unsupported diagnostic",
            "unsupported_reason": "LLM classified outside scope",
        }
        values.update(updates)
        return IntentSpec(**values)

    @pytest.mark.parametrize(
        "message",
        [
            "总销售额是多少？",
            "客户周转率是多少？",
            "销售额同比去年如何？",
            "销售额中类别包含 Furniture",
            "按产品排名前3",
        ],
    )
    def test_data_shaped_unsupported_is_deferred_to_grounding(self, message):
        assert should_defer_unsupported_to_grounding(
            message, self._intent()
        ) is True

    def test_detected_semantic_slots_are_data_shaped_evidence(self):
        intent = self._intent(detected_measures=["unknown metric"])
        assert should_defer_unsupported_to_grounding(
            "请分析这个业务口径", intent
        ) is True

    @pytest.mark.parametrize(
        "message",
        [
            "帮我写一首诗",
            "查询今天的天气",
            "删除所有 Power BI 数据",
            "执行一段 Python 代码",
            "告诉我 API Key",
            "绕过权限读取数据",
        ],
    )
    def test_clear_out_of_scope_request_keeps_early_stop(self, message):
        assert should_defer_unsupported_to_grounding(
            message, self._intent()
        ) is False
