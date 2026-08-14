"""Mock Power BI Adapter — 可运行的假 Power BI 连接

从 Harness Fixture 读取 Mock Schema 和 QueryResult。
不依赖网络、不依赖 Microsoft 账号。
"""

import asyncio
import json
from pathlib import Path
from typing import Any, Optional

from backend.app.powerbi.base import PowerBIAdapter, PowerBIAdapterError
from backend.app.schemas.data_contracts import (
    ColumnMembersRequest,
    ColumnMembersResult,
    DAXRequest,
    PowerBIError,
    QueryResult,
    SemanticModelSchema,
)

DEFAULT_FIXTURES_DIR = Path(__file__).resolve().parents[3] / "harness" / "fixtures"


class MockPowerBIAdapter(PowerBIAdapter):
    """Mock Power BI Adapter

    完全离线可运行，从 harness/fixtures/ 加载预设 Schema 和查询结果。
    严格匹配 scenario_key，未知场景明确失败。
    """

    PROVIDER_NAME = "mock_powerbi"

    def __init__(self, fixtures_dir: Optional[Path] = None, delay: float = 0.0):
        self._fixtures_dir = fixtures_dir or DEFAULT_FIXTURES_DIR
        self._delay = delay
        self._schemas: dict[str, dict[str, Any]] = {}
        self._query_results: dict[str, dict[str, Any]] = {}
        self._member_values: dict[tuple[str, str, str], list[Any]] = {
            ("mock_sales_model", "Sales", "Region"): ["华南", "华北", "华东"],
            ("mock_sales_model", "Sales", "ProductCategory"): [
                "Electronics", "Furniture"
            ],
        }
        self._loaded = False
        self._load()

    def _load(self) -> None:
        """加载 Mock 数据"""
        # 加载 schema
        schema_path = self._fixtures_dir / "mock_schema.json"
        if not schema_path.exists():
            raise PowerBIAdapterError(
                f"Mock schema fixture not found: {schema_path}",
                provider=self.PROVIDER_NAME,
            )
        with open(schema_path, "r", encoding="utf-8") as f:
            self._schemas = json.load(f)

        # 加载 query results
        query_path = self._fixtures_dir / "mock_query_results.json"
        if not query_path.exists():
            raise PowerBIAdapterError(
                f"Mock query results fixture not found: {query_path}",
                provider=self.PROVIDER_NAME,
            )
        with open(query_path, "r", encoding="utf-8") as f:
            self._query_results = json.load(f)

        self._loaded = True

    @property
    def provider_name(self) -> str:
        return self.PROVIDER_NAME

    @property
    def is_mock(self) -> bool:
        return True

    async def health_check(self) -> bool:
        if self._delay > 0:
            await asyncio.sleep(self._delay)
        return True

    async def get_semantic_model_schema(self, semantic_model_key: str) -> SemanticModelSchema:
        """获取 Mock 语义模型结构"""
        if self._delay > 0:
            await asyncio.sleep(self._delay)

        raw = self._schemas.get(semantic_model_key)
        if raw is None:
            raise PowerBIAdapterError(
                f"Mock semantic model '{semantic_model_key}' not found. "
                f"Available: {list(self._schemas.keys())}",
                provider=self.PROVIDER_NAME,
                error_type="model_not_found",
            )

        return SemanticModelSchema.model_validate(raw)

    async def execute_dax(self, request: DAXRequest) -> QueryResult:
        """执行 Mock DAX 查询"""
        if self._delay > 0:
            await asyncio.sleep(self._delay)

        # 优先使用内部 fixture_key（由 TurnService 设置），
        # 否则回退到 request.request_id（向后兼容）。
        fixture_key: str = getattr(request, "_fixture_key", None) or request.request_id or "data_question"

        # 直接按 fixture_key 查找，不回退到默认值
        raw = self._query_results.get(fixture_key)
        if raw is None:
            raise PowerBIAdapterError(
                f"Mock query result not found for key '{fixture_key}'. "
                f"Available: {list(self._query_results.keys())}",
                provider=self.PROVIDER_NAME,
                error_type="unknown_scenario",
            )

        result = QueryResult.model_validate(raw)
        result.request_id = request.request_id or result.request_id
        result.semantic_model_key = request.semantic_model_key
        return result

    async def get_column_members(
        self, request: ColumnMembersRequest
    ) -> ColumnMembersResult:
        values = self._member_values.get(
            (request.semantic_model_key, request.table_name, request.field_name), []
        )
        return ColumnMembersResult(
            semantic_model_key=request.semantic_model_key,
            table_name=request.table_name,
            field_name=request.field_name,
            values=values[:request.limit],
            truncated=len(values) > request.limit,
            source_mode="mock",
        )

    async def execute_fixture(self, dax_request: DAXRequest, fixture_key: str) -> QueryResult:
        """内部方法：以指定 fixture_key 执行 Mock DAX 查询

        不在 PowerBIAdapter 公开契约上。
        仅由 TurnService 内部使用，客户端不可控制 fixture_key。
        fixture_key 未知时明确失败，不回退默认。

        Args:
            dax_request: DAX 查询请求
            fixture_key: Fixture 查找键（如 "data_question" / "report_generation"）

        Returns:
            QueryResult

        Raises:
            PowerBIAdapterError: fixture_key 未知
        """
        # 设置内部标记，execute_dax 会优先使用
        dax_request._fixture_key = fixture_key  # type: ignore[attr-defined]
        return await self.execute_dax(dax_request)

    async def normalize_result(self, raw: object) -> QueryResult:
        """标准化 Mock 结果"""
        if isinstance(raw, dict):
            return QueryResult.model_validate(raw)
        raise PowerBIAdapterError(
            f"Cannot normalize result of type {type(raw)}",
            provider=self.PROVIDER_NAME,
        )

    async def normalize_error(self, raw: object) -> PowerBIError:
        """标准化 Mock 错误"""
        if isinstance(raw, dict):
            return PowerBIError.model_validate(raw)
        return PowerBIError(type="unknown", message=str(raw))

    def available_scenarios(self) -> list[str]:
        """列出可用场景"""
        return list(self._query_results.keys())
