"""Bounded no-tool conversational generation on the selected LLM provider."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from backend.app.llm.base import LLMProvider, LLMRequest, LLMTask


class ConversationalAnswer(BaseModel):
    """Minimal structured envelope for a low-risk conversational reply."""

    answer: str = Field(..., min_length=1, max_length=2000)

    model_config = ConfigDict(extra="forbid", frozen=True)


class ConversationalAnswerService:
    """Use language capability without business context or tool authority."""

    _SYSTEM_PROMPT = """你是 PowerBIAgent 的低风险普通对话助手。
只回答当前用户消息中的问候、闲聊、创意写作或非实时普通概念问题。
你没有工具，也没有 Power BI 模型、业务记忆、查询结果或实时外部信息。
不得声称知道公司、当前模型或用户的业务事实；不得猜测天气、新闻、股价等实时事实。
请自然、简洁地回答。只输出 JSON 对象：{\"answer\": \"回答文本\"}。"""

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    async def generate(self, user_input: str) -> ConversationalAnswer:
        response = await self._provider.generate(
            LLMRequest(
                messages=[
                    {"role": "system", "content": self._SYSTEM_PROMPT},
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
