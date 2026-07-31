"""M0.3 Power BI Adapter 单元测试"""

import pytest

from backend.app.powerbi.base import PowerBIAdapterError
from backend.app.powerbi.mock import MockPowerBIAdapter
from backend.app.schemas.data_contracts import DAXRequest, SemanticModelSchema


@pytest.fixture
def mock_adapter():
    return MockPowerBIAdapter()


class TestMockPowerBIAdapter:
    """Mock Power BI Adapter 测试"""

    @pytest.mark.asyncio
    async def test_health_check(self, mock_adapter):
        assert await mock_adapter.health_check() is True

    @pytest.mark.asyncio
    async def test_get_schema(self, mock_adapter):
        schema = await mock_adapter.get_semantic_model_schema("mock_sales_model")
        assert isinstance(schema, SemanticModelSchema)
        assert schema.key == "mock_sales_model"
        assert len(schema.tables) > 0

    @pytest.mark.asyncio
    async def test_get_schema_not_found(self, mock_adapter):
        with pytest.raises(PowerBIAdapterError, match="not found"):
            await mock_adapter.get_semantic_model_schema("nonexistent_model")

    @pytest.mark.asyncio
    async def test_execute_dax(self, mock_adapter):
        request = DAXRequest(
            semantic_model_key="mock_sales_model",
            dax="EVALUATE SUMMARIZECOLUMNS('Sales'[Region], \"Total\", SUM('Sales'[SalesAmount]))",
            request_id="data_question",
        )
        result = await mock_adapter.execute_dax(request)
        assert result.row_count == 1
        assert result.columns == ["TotalSales"]

    @pytest.mark.asyncio
    async def test_execute_dax_empty_data(self, mock_adapter):
        request = DAXRequest(
            semantic_model_key="mock_sales_model",
            dax="EVALUATE FILTER(...)",
            request_id="empty_data",
        )
        result = await mock_adapter.execute_dax(request)
        assert result.row_count == 0
        assert result.rows == []

    @pytest.mark.asyncio
    async def test_execute_dax_timeout(self, mock_adapter):
        request = DAXRequest(
            semantic_model_key="mock_sales_model",
            dax="EVALUATE ...",
            request_id="timeout",
        )
        result = await mock_adapter.execute_dax(request)
        assert result.error is not None
        assert result.error.type == "timeout"

    @pytest.mark.asyncio
    async def test_execute_dax_permission_denied(self, mock_adapter):
        request = DAXRequest(
            semantic_model_key="mock_sales_model",
            dax="EVALUATE ...",
            request_id="permission_denied",
        )
        result = await mock_adapter.execute_dax(request)
        assert result.error is not None
        assert result.error.type == "permission_denied"

    @pytest.mark.asyncio
    async def test_execute_dax_error(self, mock_adapter):
        request = DAXRequest(
            semantic_model_key="mock_sales_model",
            dax="EVALUATE BAD_DAX",
            request_id="dax_error",
        )
        result = await mock_adapter.execute_dax(request)
        assert result.error is not None
        assert result.error.type == "dax_error"

    @pytest.mark.asyncio
    async def test_execute_dax_oversized(self, mock_adapter):
        request = DAXRequest(
            semantic_model_key="mock_sales_model",
            dax="EVALUATE ...",
            request_id="oversized_result",
        )
        result = await mock_adapter.execute_dax(request)
        assert result.error is not None
        assert result.truncated is True

    @pytest.mark.asyncio
    async def test_unknown_scenario(self, mock_adapter):
        request = DAXRequest(
            semantic_model_key="mock_sales_model",
            dax="EVALUATE ...",
            request_id="nonexistent_xyz",
        )
        with pytest.raises(PowerBIAdapterError, match="not found"):
            await mock_adapter.execute_dax(request)

    @pytest.mark.asyncio
    async def test_is_mock(self, mock_adapter):
        assert mock_adapter.is_mock is True
        assert mock_adapter.provider_name == "mock_powerbi"

    @pytest.mark.asyncio
    async def test_available_scenarios(self, mock_adapter):
        scenarios = mock_adapter.available_scenarios()
        assert "data_question" in scenarios
        assert "timeout" in scenarios
