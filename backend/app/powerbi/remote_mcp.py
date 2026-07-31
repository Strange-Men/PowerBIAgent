"""Remote MCP Power BI Adapter 骨架

M0.3 只提供接口签名和配置边界，所有真实调用标记 NotImplementedError。
M2 实现真实 MCP 连接、OAuth 认证和 DAX 查询。
"""

from pathlib import Path
from typing import Optional

from backend.app.powerbi.base import PowerBIAdapter, PowerBIAdapterError
from backend.app.schemas.data_contracts import (
    DAXRequest,
    PowerBIError,
    QueryResult,
    SemanticModelSchema,
)


class RemoteMCPPowerBIAdapter(PowerBIAdapter):
    """Remote MCP Power BI Adapter

    通过 Microsoft Remote MCP Server 连接 Power BI。
    使用 Entra ID OAuth + MSAL 认证。

    M0.3：仅骨架，NotImplementedError。
    M2：实现真实连接。
    """

    PROVIDER_NAME = "remote_mcp"

    def __init__(
        self,
        server_url: str = "https://api.fabric.microsoft.com/v1/mcp/powerbi",
        tenant_id: str = "",
        client_id: str = "",
        timeout: float = 60.0,
        max_retries: int = 2,
    ):
        self._server_url = server_url
        self._tenant_id = tenant_id
        self._client_id = client_id
        self._timeout = timeout
        self._max_retries = max_retries

    @property
    def provider_name(self) -> str:
        return self.PROVIDER_NAME

    @property
    def is_mock(self) -> bool:
        return False

    async def health_check(self) -> bool:
        """[M2] 检查 Remote MCP 连接"""
        raise NotImplementedError(
            "TODO: M2 — 实现 Remote MCP Server 健康检查。"
            "M0.3 阶段请使用 MockPowerBIAdapter。"
        )

    async def get_semantic_model_schema(self, semantic_model_key: str) -> SemanticModelSchema:
        """[M2] 获取真实语义模型结构"""
        raise NotImplementedError(
            "TODO: M2 — 通过 Remote MCP 获取语义模型结构。"
            "M0.3 阶段请使用 MockPowerBIAdapter。"
        )

    async def execute_dax(self, request: DAXRequest) -> QueryResult:
        """[M2] 执行真实 DAX 查询"""
        raise NotImplementedError(
            "TODO: M2 — 通过 Remote MCP 执行 DAX 查询。"
            "M0.3 阶段请使用 MockPowerBIAdapter。"
        )

    async def normalize_result(self, raw: object) -> QueryResult:
        """[M2] 标准化真实 Power BI 响应"""
        raise NotImplementedError(
            "TODO: M2 — 标准化 Microsoft 原始响应格式。"
        )

    async def normalize_error(self, raw: object) -> PowerBIError:
        """[M2] 标准化真实 Power BI 错误"""
        raise NotImplementedError(
            "TODO: M2 — 标准化 Microsoft 原始错误格式。"
        )
