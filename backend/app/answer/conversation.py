"""Bounded no-tool conversational generation on the selected LLM provider."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.llm.base import LLMProvider, LLMRequest, LLMTask


class ConversationalAnswer(BaseModel):
    """Open-language branch decision with a no-business-facts safety valve."""

    answer: str = Field(default="", max_length=2000)
    requires_business_grounding: bool = False

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_branch(self) -> "ConversationalAnswer":
        if self.requires_business_grounding:
            if self.answer.strip():
                raise ValueError("business_escalation_must_not_include_answer")
        elif not self.answer.strip():
            raise ValueError("general_answer_required")
        return self


class ConversationalAnswerService:
    """Use language capability without business context or tool authority."""

    _SYSTEM_PROMPT = """你是 PowerBIAgent 的开放语言语义解释器。你没有工具，也没有
Power BI 模型、业务记忆、查询结果或实时外部信息。

按一个标准二选一：完整回答是否必须读取当前组织或 Power BI 中的具体事实？
- 否：普通对话。能力、工作方式、概念、教学和通用报表阅读方法都属于这里；即使出现
  “报表”“数据”“分析”等领域词，只要不查看实际内容也能完整回答，就直接回答。
  “不改动数据”只是操作限制，不代表用户要求读取当前数据。不要假设用户暗含一张当前报表。
- 是：业务事实请求。用户要求当前/这张/我们/企业模型中的具体指标值、成员、排名、趋势、
  变化或原因时，必须升级；带问候或感谢的混合事实请求也必须整体升级。

普通对话输出 {\"answer\":\"自然简洁的回答\",\"requires_business_grounding\":false}。
业务事实请求输出 {\"answer\":\"\",\"requires_business_grounding\":true}，不得猜测事实。
不得声称知道公司或当前模型事实，不得猜测天气、新闻、股价等实时事实。只输出 JSON。"""

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    async def generate(self, user_input: str) -> ConversationalAnswer:
        response = await self._provider.generate(
            LLMRequest(
                messages=[
                    {"role": "system", "content": self._SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": "你通常怎样帮助我理解一张报表？",
                    },
                    {
                        "role": "assistant",
                        "content": (
                            '{"answer":"我可以帮你梳理指标含义、筛选范围、趋势、'
                            '分组和需要核验的问题。","requires_business_grounding":false}'
                        ),
                    },
                    {"role": "user", "content": "请看一下本月销售额。"},
                    {
                        "role": "assistant",
                        "content": (
                            '{"answer":"","requires_business_grounding":true}'
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            "在不改动数据的前提下，你通常怎样帮助我理解一张报表？"
                        ),
                    },
                    {
                        "role": "assistant",
                        "content": (
                            '{"answer":"我会先澄清目的，再梳理指标、筛选范围、'
                            '比较基准和需要核验的异常。",'
                            '"requires_business_grounding":false}'
                        ),
                    },
                    {"role": "user", "content": user_input},
                ],
                task=LLMTask.CONVERSATION,
                scenario_key="conversation",
            ),
            ConversationalAnswer,
        )
        if not isinstance(response.structured, ConversationalAnswer):
            raise TypeError("conversation_response_missing")
        return response.structured
