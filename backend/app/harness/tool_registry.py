"""共享默认工具注册入口 — M1.6.2

集中注册四个白名单工具：get_semantic_model_schema、get_column_members、
execute_dax、render_report。
工具超时和重试次数从 HarnessConfig 读取，不再写死。
MockTurnService 和 DeepSeekTurnService 统一使用此入口。
"""

from typing import Any, Callable

from pydantic import BaseModel

from backend.app.harness.models import HarnessConfig
from backend.app.harness.runtime.tool_gateway import ToolGateway, ToolSpec
from backend.app.intent.models import IntentType
from backend.app.memory.models import RuntimeDataMode
from backend.app.report.base import ReportRenderer
from backend.app.report.resources import (
    InMemoryReportRepository,
    ReportArtifact,
    ReportRepository,
)
from backend.app.schemas.data_contracts import (
    ColumnMembersRequest,
    ColumnMembersResult,
    DAXRequest,
    QueryResult,
    ReportSpec,
    SemanticModelSchema,
)


class SchemaInput(BaseModel):
    """get_semantic_model_schema 工具输入"""
    semantic_model_key: str = "mock_sales_model"


# ── 四个白名单工具名称 ──
TOOL_NAME_SCHEMA = "get_semantic_model_schema"
TOOL_NAME_MEMBERS = "get_column_members"
TOOL_NAME_DAX = "execute_dax"
TOOL_NAME_RENDER = "render_report"

DEFAULT_TOOL_NAMES = [
    TOOL_NAME_SCHEMA,
    TOOL_NAME_MEMBERS,
    TOOL_NAME_DAX,
    TOOL_NAME_RENDER,
]


def register_default_tools(
    gateway: ToolGateway,
    powerbi_adapter: Any,
    report_renderer: ReportRenderer,
    config: HarnessConfig,
    report_repository: ReportRepository | None = None,
) -> None:
    """向 ToolGateway 注册四个标准白名单工具

    Args:
        gateway: 要注册工具的 ToolGateway 实例
        powerbi_adapter: 需提供 get_semantic_model_schema(key) 和 execute_dax(dax_req)
        report_renderer: 固定 Renderer，只提供 render(report_spec) → str (HTML)
        config: 从 Settings 构建的 HarnessConfig，驱动超时和重试
        report_repository: 管理 report_id 与 HTML artifact；默认仅内存兼容
    """

    # ── 1. get_semantic_model_schema ──
    register_schema_tool(gateway, powerbi_adapter, config)

    # ── 2. get_column_members ──
    get_members = powerbi_adapter.get_column_members

    async def _get_members(
        input_data: ColumnMembersRequest,
    ) -> ColumnMembersResult:
        return await get_members(input_data)

    gateway.register(ToolSpec(
        name=TOOL_NAME_MEMBERS,
        description="读取 Power BI 字段的有界成员值",
        input_model=ColumnMembersRequest,
        output_model=ColumnMembersResult,
        timeout_seconds=float(config.powerbi_query_timeout_seconds),
        max_retries=config.max_powerbi_retries,
        read_only=True,
        allowed_intents=[IntentType.DATA_QUESTION, IntentType.REPORT_GENERATION],
        supported_modes=[RuntimeDataMode.MOCK, RuntimeDataMode.REAL],
        handler=_get_members,
    ))

    # ── 3. execute_dax ──
    execute_dax_fn = powerbi_adapter.execute_dax

    async def _execute_dax(input_data: DAXRequest) -> QueryResult:
        return await execute_dax_fn(input_data)

    gateway.register(ToolSpec(
        name=TOOL_NAME_DAX,
        description="执行 DAX 查询",
        input_model=DAXRequest,
        output_model=QueryResult,
        timeout_seconds=float(config.powerbi_query_timeout_seconds),
        max_retries=config.max_powerbi_retries,
        read_only=True,
        allowed_intents=[IntentType.DATA_QUESTION, IntentType.REPORT_GENERATION],
        supported_modes=[RuntimeDataMode.MOCK, RuntimeDataMode.REAL],
        handler=_execute_dax,
    ))

    # ── 4. render_report ──
    render_fn = report_renderer.render
    repository = report_repository or InMemoryReportRepository()

    async def _render_report(input_data: ReportSpec) -> ReportArtifact:
        html = await render_fn(input_data)
        return await repository.store(
            input_data,
            html,
            conversation_id=input_data.conversation_id,
            request_id=input_data.request_id,
        )

    gateway.register(ToolSpec(
        name=TOOL_NAME_RENDER,
        description="渲染报表为 HTML",
        input_model=ReportSpec,
        output_model=ReportArtifact,
        timeout_seconds=float(config.request_timeout_seconds),
        max_retries=0,
        read_only=True,
        allowed_intents=[IntentType.REPORT_GENERATION],
        supported_modes=[RuntimeDataMode.MOCK, RuntimeDataMode.REAL],
        handler=_render_report,
    ))


def register_schema_tool(
    gateway: ToolGateway,
    powerbi_adapter: Any,
    config: HarnessConfig,
) -> None:
    """Register the canonical read-only schema boundary for focused callers."""
    get_schema = powerbi_adapter.get_semantic_model_schema

    async def _get_schema(input_data: SchemaInput) -> SemanticModelSchema:
        return await get_schema(input_data.semantic_model_key)

    gateway.register(ToolSpec(
        name=TOOL_NAME_SCHEMA,
        description="获取 Power BI 语义模型结构",
        input_model=SchemaInput,
        output_model=SemanticModelSchema,
        timeout_seconds=float(config.powerbi_query_timeout_seconds),
        max_retries=config.max_powerbi_retries,
        read_only=True,
        allowed_intents=[IntentType.DATA_QUESTION, IntentType.REPORT_GENERATION],
        supported_modes=[RuntimeDataMode.MOCK, RuntimeDataMode.REAL],
        handler=_get_schema,
    ))


def create_default_tool_gateway(
    powerbi_adapter: Any,
    report_renderer: ReportRenderer,
    config: HarnessConfig,
    report_repository: ReportRepository | None = None,
) -> ToolGateway:
    """创建并返回已注册四个白名单工具的 ToolGateway

    这是 MockTurnService 获取 ToolGateway 的首选方式。
    """
    gateway = ToolGateway()
    register_default_tools(
        gateway,
        powerbi_adapter,
        report_renderer,
        config,
        report_repository,
    )
    return gateway
