"""API 请求/响应 Pydantic 模型 — M1.5

M0.4.1 修复：
- ChatResponse 增加结构化 report 字段（真实 RenderedReport）
- HealthResponse 增加 ready/reasons 字段
- 不使用 dict[str, Any] 逃避校验

M1.0 新增：
- ChatResponse 增加 idempotent_replay / replayed_request_id 字段

M1.5 新增：
- ChatResponse 增加 llm_mode / powerbi_mode / source_mode / usage 字段
- usage 包含 call_count, repair_count, prompt_tokens, completion_tokens,
  total_tokens, duration_ms, estimated_cost_usd, pricing_configured
- is_mock 语义：Mock LLM 时为 True，DeepSeek LLM 时为 False
- 不新增 sidebar, workspace_layout, report_position, frontend_blocks, navigation_section
"""

from typing import Any, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """POST /api/v1/chat 请求"""

    message: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="用户自然语言消息",
    )
    conversation_id: Optional[str] = Field(
        default=None,
        description="会话 ID，未提供时服务端自动生成",
    )
    request_id: Optional[str] = Field(
        default=None,
        description="请求 ID，未提供时服务端自动生成，支持幂等",
    )
    semantic_model_key: str = Field(
        default="mock_sales_model",
        description="Power BI 语义模型标识",
    )
    report_template_key: Optional[str] = Field(
        default=None,
        description="报表模板标识，仅在报表生成请求时需要",
    )

    # 禁止客户端直接传 Mock Scenario Key
    model_config = {"extra": "forbid"}


class ReportResponse(BaseModel):
    """报表结构化响应 — M0.4.1 新增"""

    report_id: str = Field(description="报表唯一 ID，与 Memory.last_report_id 一致")
    template_key: str = Field(description="报表模板标识")
    html: str = Field(default="", description="渲染后的 HTML（Mock 模式返回）")


class ChatResponse(BaseModel):
    """POST /api/v1/chat 响应 — M1.5"""

    request_id: str
    conversation_id: str
    terminal_state: str
    intent: str
    response_type: str
    answer: Optional[str] = Field(
        default=None,
        description="数据问答场景的真实 AnswerSpec.answer，非查询摘要",
    )
    report: Optional[ReportResponse] = Field(
        default=None,
        description="报表场景的结构化报表数据",
    )
    clarification_question: Optional[str] = Field(
        default=None,
        description="clarification 场景的追问问题",
    )
    unsupported_reason: Optional[str] = Field(
        default=None,
        description="unsupported 场景的拒绝原因",
    )
    error_type: Optional[str] = None
    tool_sequence: list[str] = Field(default_factory=list)
    memory_commit: bool = False
    trace_id: str = ""
    is_mock: bool = Field(
        default=True,
        description="Mock LLM 时为 True，DeepSeek LLM 时为 False",
    )
    allowed_tools: list[str] = Field(default_factory=list)

    # M1.0: 幂等重放字段
    idempotent_replay: bool = Field(
        default=False,
        description="true 表示此响应来自幂等重放，未重新执行 LLM/工具/Memory",
    )
    replayed_request_id: Optional[str] = Field(
        default=None,
        description="幂等重放时指向原始 request_id；首次请求为 null",
    )

    # M1.5: 模式与使用统计字段
    llm_mode: str = Field(default="", description="LLM 模式：mock / deepseek")
    powerbi_mode: str = Field(default="", description="Power BI 模式：mock / remote_mcp")
    source_mode: str = Field(default="", description="数据来源：mock / real")
    usage: Optional[dict[str, Any]] = Field(
        default=None,
        description="LLM 使用统计：call_count, repair_count, prompt_tokens, "
                    "completion_tokens, total_tokens, duration_ms, "
                    "estimated_cost_usd, pricing_configured",
    )
    # 不新增：sidebar, workspace_layout, report_position, frontend_blocks, navigation_section


class HealthResponse(BaseModel):
    """GET /health 响应 — M0.4.1"""

    status: str
    ready: bool = Field(description="当前配置下系统是否完整可用")
    reasons: list[str] = Field(
        default_factory=list,
        description="不可用原因列表（ready=false 时填充）",
    )
    app_name: str
    app_env: str
    version: str
    llm_mode: str
    powerbi_mode: str
    harness_mode: str
    timestamp: str


class ErrorResponse(BaseModel):
    """统一错误响应"""

    detail: str
    error_type: Optional[str] = None
    request_id: Optional[str] = None
