"""Power BI Adapter 抽象基类

所有 Power BI 接入方式（Mock、Remote MCP、Local MCP）必须实现此接口。
Agent、API、Memory、Report 和 Harness 不得直接依赖 Microsoft 原始工具名称或响应格式。
"""

from abc import ABC, abstractmethod
from typing import Optional

from backend.app.schemas.data_contracts import (
    ColumnMembersRequest,
    ColumnMembersResult,
    DAXRequest,
    PowerBIError,
    QueryResult,
    SemanticModelSchema,
)
from backend.app.powerbi.models import SemanticModelCatalog


class PowerBIAdapter(ABC):
    """Power BI 适配器抽象基类

    职责：
    - 获取语义模型结构
    - 执行只读 DAX 查询
    - 标准化返回结果和错误
    """

    @abstractmethod
    async def health_check(self) -> bool:
        """检查 Power BI 连接健康状态

        Returns:
            True 表示连接正常
        """
        ...

    @abstractmethod
    async def get_semantic_model_schema(
        self, semantic_model_key: str
    ) -> SemanticModelSchema:
        """获取指定语义模型的结构（表、字段、度量值、关系）

        Args:
            semantic_model_key: 语义模型唯一标识

        Returns:
            SemanticModelSchema: 标准化模型结构

        Raises:
            PowerBIAdapterError: 模型不存在、权限不足或连接失败
        """
        ...

    async def get_column_members(
        self, request: ColumnMembersRequest
    ) -> ColumnMembersResult:
        """读取一个已验证列的有界 distinct member values。"""
        raise PowerBIAdapterError(
            "Bounded member lookup is not implemented by this provider",
            provider=self.provider_name,
            error_type="member_lookup_not_supported",
        )

    async def discover_semantic_models(self) -> SemanticModelCatalog:
        """Return a safe catalog of models selectable by the frontend."""
        raise PowerBIAdapterError(
            "Semantic model discovery is not implemented by this provider",
            provider=self.provider_name,
            error_type="semantic_model_discovery_not_supported",
        )

    @abstractmethod
    async def execute_dax(self, request: DAXRequest) -> QueryResult:
        """执行 DAX 查询

        Args:
            request: DAX 查询请求（含 DAX、行数、超时等）

        Returns:
            QueryResult: 标准化查询结果

        Raises:
            PowerBIAdapterError: 查询失败、超时、权限不足等
        """
        ...

    @abstractmethod
    async def normalize_result(self, raw: object) -> QueryResult:
        """将原始 MCP/Power BI 响应标准化为 QueryResult

        隔离 Microsoft 原始响应格式。
        """
        ...

    @abstractmethod
    async def normalize_error(self, raw: object) -> PowerBIError:
        """将原始错误标准化为 PowerBIError

        隔离 Microsoft 原始错误格式。
        """
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider 名称"""
        ...

    @property
    @abstractmethod
    def is_mock(self) -> bool:
        """是否为 Mock Provider"""
        ...


class PowerBIAdapterError(Exception):
    """Power BI Adapter 通用异常"""

    def __init__(
        self,
        message: str,
        provider: str = "",
        retryable: bool = False,
        error_type: str = "unknown",
    ):
        super().__init__(message)
        self.provider = provider
        self.retryable = retryable
        self.error_type = error_type
