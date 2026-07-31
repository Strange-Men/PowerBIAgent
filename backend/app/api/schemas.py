"""API 请求/响应 Pydantic 模型 — M0.4"""

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


class ChatResponse(BaseModel):
    """POST /api/v1/chat 响应"""

    request_id: str
    conversation_id: str
    terminal_state: str
    intent: str
    response_type: str
    answer: Optional[str] = Field(default=None)
    error_type: Optional[str] = None
    tool_sequence: list[str] = Field(default_factory=list)
    memory_commit: bool = False
    trace_id: str = ""
    is_mock: bool = True
    allowed_tools: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    """GET /health 响应"""

    status: str
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
