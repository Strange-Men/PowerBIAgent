"""MockScenarioResolver — Mock 模式内部场景解析器

根据用户消息和 report_template_key 确定测试 Fixture 场景。
仅在 Mock 模式内部使用，不暴露给 API 客户端。

Golden Cases 和内部测试可以通过显式传入 MockScenarioSelection 跳过解析器。

M5.7：报表关键词只识别 intent，不再隐式填充任何模板。
"""

from typing import Optional

from pydantic import BaseModel

from backend.app.application.mock_turn_service import MockScenarioSelection


class MockScenarioResolution(BaseModel):
    """Mock 场景解析结果 — M1.0 新增

    同时返回场景选择和生效后的报表模板 Key，
    确保 Context、ReportSpec、RenderedReport、Memory 和 API 响应使用同一模板。
    """
    scenario: MockScenarioSelection
    effective_report_template_key: Optional[str] = None


class MockScenarioResolver:
    """根据用户消息和模板 Key 推断 Mock 场景

    匹配优先级（从高到低）：
    1. 破坏性操作关键词 → unsupported
    2. 提供 report_template_key → report_generation
    3. 包含报表/报告关键词 → report_generation
    4. 模糊/浏览类关键词 → clarification
    5. 默认 → data_question
    """

    # 破坏性操作关键词 → unsupported
    DESTRUCTIVE_KEYWORDS: tuple[str, ...] = (
        "删除", "删掉", "移除", "清空", "销毁",
        "修改", "更新", "变更",
        "drop", "delete", "remove", "truncate",
        "modify", "update", "alter",
    )

    # 报表/报告/图表关键词 → report_generation
    REPORT_KEYWORDS: tuple[str, ...] = (
        "报表", "报告", "周报", "月报", "日报", "年报",
        "生成", "导出", "制作",
        "report", "chart", "图表", "dashboard",
    )

    # 模糊/不明确关键词 → clarification
    VAGUE_KEYWORDS: tuple[str, ...] = (
        "看看", "看一下", "帮我看看", "看看数据",
        "浏览", "有什么", "有什么数据",
    )

    @classmethod
    def resolve(
        cls,
        message: str,
        report_template_key: Optional[str] = None,
    ) -> MockScenarioResolution:
        """根据用户消息和模板 Key 解析 Mock 场景

        Args:
            message: 用户自然语言消息
            report_template_key: 报表模板标识（可选）

        Returns:
            MockScenarioResolution — 场景选择 + 生效后的报表模板 Key
        """
        msg = message.strip()
        msg_lower = msg.lower()

        # 1. 破坏性操作 → unsupported
        for kw in cls.DESTRUCTIVE_KEYWORDS:
            if kw in msg_lower:
                return MockScenarioResolution(
                    scenario=MockScenarioSelection(
                        intent_key="unsupported",
                        query_plan_key="data_question",
                        dax_key="data_question",
                        powerbi_key="data_question",
                        response_key="data_question",
                    ),
                    effective_report_template_key=None,
                )

        # 2. 提供 report_template_key → report_generation（显式模板优先）
        if report_template_key:
            return MockScenarioResolution(
                scenario=MockScenarioSelection(
                    intent_key="report_generation",
                    query_plan_key="report_generation",
                    dax_key="report_generation",
                    powerbi_key="report_generation",
                    response_key="report_generation",
                ),
                effective_report_template_key=report_template_key,
            )

        # 3. 包含报表关键词 → report_generation；模板必须由请求显式提供。
        for kw in cls.REPORT_KEYWORDS:
            if kw in msg_lower:
                return MockScenarioResolution(
                    scenario=MockScenarioSelection(
                        intent_key="report_generation",
                        query_plan_key="report_generation",
                        dax_key="report_generation",
                        powerbi_key="report_generation",
                        response_key="report_generation",
                    ),
                    effective_report_template_key=None,
                )

        # 4. 模糊/不明确问题 → clarification
        for kw in cls.VAGUE_KEYWORDS:
            if kw in msg_lower:
                return MockScenarioResolution(
                    scenario=MockScenarioSelection(
                        intent_key="clarification",
                        query_plan_key="data_question",
                        dax_key="data_question",
                        powerbi_key="data_question",
                        response_key="data_question",
                    ),
                    effective_report_template_key=None,
                )

        # 5. 默认 → data_question
        return MockScenarioResolution(
            scenario=MockScenarioSelection(
                intent_key="data_question",
                query_plan_key="data_question",
                dax_key="data_question",
                powerbi_key="data_question",
                response_key="data_question",
            ),
            effective_report_template_key=None,
        )
