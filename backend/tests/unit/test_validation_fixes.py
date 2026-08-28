"""ValidationService M1.4.1 修复测试

离线测试覆盖：
- KPI 列顺序稳定（有序列映射替代 set 枚举）
- Answer semantic_model_key 强制非空
- Report data_source 强制非空
- KPI.value=None/bool 拒绝
- metric_provenance 结构化来源契约
- 模板冲突与空权限集合
- Table 类型严格比较
- 数值容差集中定义
"""

from __future__ import annotations

import pytest

from backend.app.harness.validators.validation_service import (
    ValidationService,
    _safe_repr,
    _compute_aggregation,
    _NUMERIC_TOLERANCE,
    _ALLOWED_AGGREGATIONS,
)
from backend.app.schemas.data_contracts import (
    AnswerSpec,
    ChartSpec,
    KPISpec,
    PowerBIError,
    QueryResult,
    ReportSpec,
    TableSpec,
)
from backend.app.intent.models import IntentSpec, IntentType


# ── Fixtures ──

_LEGACY_MOCK_TEMPLATES = {
    "sales_weekly", "satisfaction", "operating_overview"
}

@pytest.fixture
def validation() -> ValidationService:
    return ValidationService(allowed_templates=_LEGACY_MOCK_TEMPLATES)


@pytest.fixture
def sample_result() -> QueryResult:
    """3行×2列的标准 QueryResult"""
    return QueryResult(
        result_id="qr_test_001",
        semantic_model_key="mock_sales_model",
        columns=["Region", "SalesAmount"],
        rows=[["华南", 4560000], ["华东", 3890000], ["华北", 3120000]],
        row_count=3,
        source_mode="mock",
    )


@pytest.fixture
def sample_answer_spec() -> AnswerSpec:
    return AnswerSpec(
        answer="华南地区销售额最高，为456万元。",
        summary="华南领先",
        semantic_model_key="mock_sales_model",
        source_mode="mock",
        evidence={
            "result_id": "qr_test_001",
            "semantic_model_key": "mock_sales_model",
            "row_count": 3,
            "source_mode": "mock",
        },
    )


@pytest.fixture
def empty_result() -> QueryResult:
    return QueryResult(
        result_id="qr_empty",
        semantic_model_key="mock_sales_model",
        columns=["Region", "SalesAmount"],
        rows=[],
        row_count=0,
        source_mode="mock",
    )


# ══════════════════════════════════════════════════════════════════════
# KPI 列顺序稳定性
# ══════════════════════════════════════════════════════════════════════

class TestKpiColumnOrder:
    """KPI 验证使用有序列映射，不依赖 set 枚举顺序"""

    def test_kpi_with_original_column_order_passes(self, validation, sample_result):
        """columns=["Region", "SalesAmount"] 时合法 SalesAmount KPI 通过"""
        spec = ReportSpec(
            title="测试报表",
            template_key="sales_weekly",
            data_source="mock_sales_model",
            source_mode="mock",
            kpis=[KPISpec(name="总销售额", value=11570000, format="number", field="SalesAmount")],
        )
        result = validation.validate_report_strict(spec, sample_result)
        assert result.is_valid, f"应通过但失败: {result.errors}"

    def test_kpi_with_reversed_column_order_passes(self):
        """columns 顺序反转时仍正确验证"""
        result = QueryResult(
            result_id="qr_test",
            semantic_model_key="mock_sales_model",
            columns=["SalesAmount", "Region"],  # 反转顺序
            rows=[[4560000, "华南"], [3890000, "华东"], [3120000, "华北"]],
            row_count=3,
            source_mode="mock",
        )
        spec = ReportSpec(
            title="测试报表",
            template_key="sales_weekly",
            data_source="mock_sales_model",
            source_mode="mock",
            kpis=[KPISpec(name="总销售额", value=11570000, format="number", field="SalesAmount")],
        )
        validation = ValidationService(allowed_templates=_LEGACY_MOCK_TEMPLATES)
        result2 = validation.validate_report_strict(spec, result)
        assert result2.is_valid, f"列顺序反转后应通过: {result2.errors}"

    def test_region_string_not_mistaken_for_salesamount(self, validation, sample_result):
        """Region 字符串不被错误当成 SalesAmount"""
        spec = ReportSpec(
            title="测试报表",
            template_key="sales_weekly",
            data_source="mock_sales_model",
            source_mode="mock",
            kpis=[KPISpec(name="区域数", value=3, format="number", field="Region")],
        )
        result = validation.validate_report_strict(spec, sample_result)
        assert result.is_valid, f"Region count=3 应通过: {result.errors}"

    def test_kpi_sum_aggregation_passes(self, validation, sample_result):
        """sum 聚合通过"""
        spec = ReportSpec(
            title="测试报表",
            template_key="sales_weekly",
            data_source="mock_sales_model",
            source_mode="mock",
            kpis=[KPISpec(name="总销售额", value=11570000, format="number", field="SalesAmount")],
        )
        result = validation.validate_report_strict(spec, sample_result)
        assert result.is_valid

    def test_kpi_avg_aggregation_passes(self, validation, sample_result):
        """avg 聚合通过"""
        spec = ReportSpec(
            title="测试报表",
            template_key="sales_weekly",
            data_source="mock_sales_model",
            source_mode="mock",
            kpis=[
                KPISpec(name="平均销售额", value=11570000 / 3, format="number", field="SalesAmount"),
            ],
        )
        result = validation.validate_report_strict(spec, sample_result)
        assert result.is_valid, f"avg 应通过: {result.errors}"

    def test_kpi_count_aggregation_passes(self, validation, sample_result):
        """count 聚合通过"""
        spec = ReportSpec(
            title="测试报表",
            template_key="sales_weekly",
            data_source="mock_sales_model",
            source_mode="mock",
            kpis=[KPISpec(name="区域数", value=3, format="number", field="Region")],
        )
        result = validation.validate_report_strict(spec, sample_result)
        assert result.is_valid, f"count=3 应通过: {result.errors}"

    def test_unverifiable_value_rejected(self, validation, sample_result):
        """无法复现的值拒绝"""
        spec = ReportSpec(
            title="测试报表",
            template_key="sales_weekly",
            data_source="mock_sales_model",
            source_mode="mock",
            kpis=[KPISpec(name="虚构值", value=99999999, format="number", field="SalesAmount")],
        )
        result = validation.validate_report_strict(spec, sample_result)
        assert not result.is_valid
        assert any("unverifiable" in e for e in result.errors)

    def test_multiple_runs_stable(self, validation, sample_result):
        """多次运行结果稳定"""
        spec = ReportSpec(
            title="测试报表",
            template_key="sales_weekly",
            data_source="mock_sales_model",
            source_mode="mock",
            kpis=[KPISpec(name="总销售额", value=11570000, format="number", field="SalesAmount")],
        )
        results = [validation.validate_report_strict(spec, sample_result) for _ in range(20)]
        assert all(r.is_valid for r in results), "多次运行结果应稳定"


# ══════════════════════════════════════════════════════════════════════
# Answer semantic_model_key 强制非空
# ══════════════════════════════════════════════════════════════════════

class TestAnswerModelKeyBinding:
    """validate_answer_strict 强制 semantic_model_key 非空"""

    def test_empty_model_key_rejected(self, validation, sample_result):
        """空 semantic_model_key 拒绝"""
        answer = AnswerSpec(
            answer="华南销售额最高。",
            summary="华南领先",
            semantic_model_key="",  # 空
            source_mode="mock",
            evidence={
                "result_id": "qr_test_001",
                "semantic_model_key": "mock_sales_model",
                "row_count": 3,
                "source_mode": "mock",
            },
        )
        result = validation.validate_answer_strict(answer, sample_result)
        assert not result.is_valid
        assert any("empty" in e for e in result.errors)

    def test_correct_model_key_passes(self, validation, sample_result):
        """正确 Key 通过"""
        answer = AnswerSpec(
            answer="华南销售额最高。",
            summary="华南领先",
            semantic_model_key="mock_sales_model",
            source_mode="mock",
            evidence={
                "result_id": "qr_test_001",
                "semantic_model_key": "mock_sales_model",
                "row_count": 3,
                "source_mode": "mock",
            },
        )
        result = validation.validate_answer_strict(answer, sample_result)
        assert result.is_valid, f"应通过: {result.errors}"

    def test_mismatched_model_key_rejected(self, validation, sample_result):
        """不一致值拒绝"""
        answer = AnswerSpec(
            answer="华南销售额最高。",
            summary="华南领先",
            semantic_model_key="wrong_model",
            source_mode="mock",
            evidence={
                "result_id": "qr_test_001",
                "semantic_model_key": "mock_sales_model",
                "row_count": 3,
                "source_mode": "mock",
            },
        )
        result = validation.validate_answer_strict(answer, sample_result)
        assert not result.is_valid


# ══════════════════════════════════════════════════════════════════════
# Report data_source 强制非空
# ══════════════════════════════════════════════════════════════════════

class TestReportDataSourceBinding:
    """validate_report_strict 强制 data_source 非空"""

    def test_empty_data_source_rejected(self, validation, sample_result):
        """空 data_source 拒绝"""
        spec = ReportSpec(
            title="测试报表",
            template_key="sales_weekly",
            data_source="",  # 空
            source_mode="mock",
        )
        result = validation.validate_report_strict(spec, sample_result)
        assert not result.is_valid
        assert any("empty" in e for e in result.errors)

    def test_correct_data_source_passes(self, validation, sample_result):
        """正确 data_source 通过"""
        spec = ReportSpec(
            title="测试报表",
            template_key="sales_weekly",
            data_source="mock_sales_model",
            source_mode="mock",
        )
        result = validation.validate_report_strict(spec, sample_result)
        assert result.is_valid, f"应通过: {result.errors}"

    def test_mismatched_data_source_rejected(self, validation, sample_result):
        """不一致值拒绝"""
        spec = ReportSpec(
            title="测试报表",
            template_key="sales_weekly",
            data_source="wrong_model",
            source_mode="mock",
        )
        result = validation.validate_report_strict(spec, sample_result)
        assert not result.is_valid


# ══════════════════════════════════════════════════════════════════════
# KPI None/bool 拒绝
# ══════════════════════════════════════════════════════════════════════

class TestKpiValueValidation:
    """KPI.value 真实性验证"""

    def test_none_value_rejected(self, validation, sample_result):
        """None 拒绝"""
        spec = ReportSpec(
            title="测试报表",
            template_key="sales_weekly",
            data_source="mock_sales_model",
            source_mode="mock",
            kpis=[KPISpec(name="销售额", value=None, format="number", field="SalesAmount")],
        )
        result = validation.validate_report_strict(spec, sample_result)
        assert not result.is_valid
        assert any("none" in e for e in result.errors)

    def test_bool_value_rejected(self, validation, sample_result):
        """bool 拒绝"""
        spec = ReportSpec(
            title="测试报表",
            template_key="sales_weekly",
            data_source="mock_sales_model",
            source_mode="mock",
            kpis=[KPISpec(name="销售额", value=True, format="number", field="SalesAmount")],
        )
        result = validation.validate_report_strict(spec, sample_result)
        assert not result.is_valid
        assert any("bool" in e for e in result.errors)

    def test_int_value_passes(self, validation, sample_result):
        """int 值通过"""
        spec = ReportSpec(
            title="测试报表",
            template_key="sales_weekly",
            data_source="mock_sales_model",
            source_mode="mock",
            kpis=[KPISpec(name="区域数", value=3, format="number", field="Region")],
        )
        result = validation.validate_report_strict(spec, sample_result)
        assert result.is_valid

    def test_float_value_passes(self, validation, sample_result):
        """float 值通过"""
        spec = ReportSpec(
            title="测试报表",
            template_key="sales_weekly",
            data_source="mock_sales_model",
            source_mode="mock",
            kpis=[KPISpec(name="平均", value=3856666.67, format="number", field="SalesAmount")],
        )
        result = validation.validate_report_strict(spec, sample_result)
        assert result.is_valid

    def test_min_aggregation_passes(self, validation, sample_result):
        """min 聚合通过"""
        spec = ReportSpec(
            title="测试报表",
            template_key="sales_weekly",
            data_source="mock_sales_model",
            source_mode="mock",
            kpis=[KPISpec(name="最低销售额", value=3120000, format="number", field="SalesAmount")],
        )
        result = validation.validate_report_strict(spec, sample_result)
        assert result.is_valid

    def test_max_aggregation_passes(self, validation, sample_result):
        """max 聚合通过"""
        spec = ReportSpec(
            title="测试报表",
            template_key="sales_weekly",
            data_source="mock_sales_model",
            source_mode="mock",
            kpis=[KPISpec(name="最高销售额", value=4560000, format="number", field="SalesAmount")],
        )
        result = validation.validate_report_strict(spec, sample_result)
        assert result.is_valid

    def test_fabricated_value_rejected(self, validation, sample_result):
        """虚构值拒绝"""
        spec = ReportSpec(
            title="测试报表",
            template_key="sales_weekly",
            data_source="mock_sales_model",
            source_mode="mock",
            kpis=[KPISpec(name="虚构", value=777777, format="number", field="SalesAmount")],
        )
        result = validation.validate_report_strict(spec, sample_result)
        assert not result.is_valid


# ══════════════════════════════════════════════════════════════════════
# metric_provenance 结构化来源
# ══════════════════════════════════════════════════════════════════════

class TestMetricProvenance:
    """Answer metrics 必须提供结构化 metric_provenance"""

    def test_metrics_no_provenance_rejected(self, validation, sample_result):
        """metrics 存在但无 metric_provenance 拒绝"""
        answer = AnswerSpec(
            answer="华南销售额最高。",
            summary="华南领先",
            semantic_model_key="mock_sales_model",
            source_mode="mock",
            metrics={"TotalSales": 11570000},
            evidence={
                "result_id": "qr_test_001",
                "semantic_model_key": "mock_sales_model",
                "row_count": 3,
                "source_mode": "mock",
                # 缺少 metric_provenance
            },
        )
        result = validation.validate_answer_strict(answer, sample_result)
        assert not result.is_valid
        assert any("provenance" in e for e in result.errors)

    def test_missing_metric_entry_rejected(self, validation, sample_result):
        """缺少某个 metric 来源时拒绝"""
        answer = AnswerSpec(
            answer="华南销售额最高。",
            summary="华南领先",
            semantic_model_key="mock_sales_model",
            source_mode="mock",
            metrics={"TotalSales": 11570000, "AvgSales": 3856666},
            evidence={
                "result_id": "qr_test_001",
                "semantic_model_key": "mock_sales_model",
                "row_count": 3,
                "source_mode": "mock",
                "metric_provenance": {
                    "TotalSales": {"source_field": "SalesAmount", "aggregation": "sum"},
                    # AvgSales 缺失
                },
            },
        )
        result = validation.validate_answer_strict(answer, sample_result)
        assert not result.is_valid
        assert any("AvgSales" in e or "provenance" in e for e in result.errors)

    def test_source_field_not_found_rejected(self, validation, sample_result):
        """source_field 不存在时拒绝"""
        answer = AnswerSpec(
            answer="华南销售额最高。",
            summary="华南领先",
            semantic_model_key="mock_sales_model",
            source_mode="mock",
            metrics={"TotalRevenue": 11570000},
            evidence={
                "result_id": "qr_test_001",
                "semantic_model_key": "mock_sales_model",
                "row_count": 3,
                "source_mode": "mock",
                "metric_provenance": {
                    "TotalRevenue": {"source_field": "NonExistent", "aggregation": "sum"},
                },
            },
        )
        result = validation.validate_answer_strict(answer, sample_result)
        assert not result.is_valid
        assert any("field_not_found" in e or "NonExistent" in e for e in result.errors)

    def test_invalid_aggregation_rejected(self, validation, sample_result):
        """非法 aggregation 拒绝"""
        answer = AnswerSpec(
            answer="华南销售额最高。",
            summary="华南领先",
            semantic_model_key="mock_sales_model",
            source_mode="mock",
            metrics={"TotalSales": 11570000},
            evidence={
                "result_id": "qr_test_001",
                "semantic_model_key": "mock_sales_model",
                "row_count": 3,
                "source_mode": "mock",
                "metric_provenance": {
                    "TotalSales": {"source_field": "SalesAmount", "aggregation": "median"},
                },
            },
        )
        result = validation.validate_answer_strict(answer, sample_result)
        assert not result.is_valid
        assert any("aggregation" in e for e in result.errors)

    def test_value_mismatch_rejected(self, validation, sample_result):
        """计算结果不匹配时拒绝"""
        answer = AnswerSpec(
            answer="华南销售额最高。",
            summary="华南领先",
            semantic_model_key="mock_sales_model",
            source_mode="mock",
            metrics={"TotalSales": 99999999},
            evidence={
                "result_id": "qr_test_001",
                "semantic_model_key": "mock_sales_model",
                "row_count": 3,
                "source_mode": "mock",
                "metric_provenance": {
                    "TotalSales": {"source_field": "SalesAmount", "aggregation": "sum"},
                },
            },
        )
        result = validation.validate_answer_strict(answer, sample_result)
        assert not result.is_valid
        assert any("mismatch" in e for e in result.errors)

    def test_direct_aggregation_passes(self, validation, sample_result):
        """direct 聚合通过"""
        answer = AnswerSpec(
            answer="华南销售额为456万元。",
            summary="华南领先",
            semantic_model_key="mock_sales_model",
            source_mode="mock",
            metrics={"TopSales": 4560000},
            evidence={
                "result_id": "qr_test_001",
                "semantic_model_key": "mock_sales_model",
                "row_count": 3,
                "source_mode": "mock",
                "metric_provenance": {
                    "TopSales": {"source_field": "SalesAmount", "aggregation": "direct"},
                },
            },
        )
        result = validation.validate_answer_strict(answer, sample_result)
        assert result.is_valid, f"应通过: {result.errors}"

    def test_sum_aggregation_passes(self, validation, sample_result):
        """sum 聚合通过"""
        answer = AnswerSpec(
            answer="总销售额为1157万。",
            summary="总计1157万",
            semantic_model_key="mock_sales_model",
            source_mode="mock",
            metrics={"TotalSales": 11570000},
            evidence={
                "result_id": "qr_test_001",
                "semantic_model_key": "mock_sales_model",
                "row_count": 3,
                "source_mode": "mock",
                "metric_provenance": {
                    "TotalSales": {"source_field": "SalesAmount", "aggregation": "sum"},
                },
            },
        )
        result = validation.validate_answer_strict(answer, sample_result)
        assert result.is_valid, f"应通过: {result.errors}"

    def test_avg_aggregation_passes(self, validation, sample_result):
        """avg 聚合通过"""
        answer = AnswerSpec(
            answer="平均销售额约385.7万。",
            summary="平均385.7万",
            semantic_model_key="mock_sales_model",
            source_mode="mock",
            metrics={"AvgSales": 11570000 / 3},
            evidence={
                "result_id": "qr_test_001",
                "semantic_model_key": "mock_sales_model",
                "row_count": 3,
                "source_mode": "mock",
                "metric_provenance": {
                    "AvgSales": {"source_field": "SalesAmount", "aggregation": "avg"},
                },
            },
        )
        result = validation.validate_answer_strict(answer, sample_result)
        assert result.is_valid, f"应通过: {result.errors}"

    def test_count_aggregation_passes(self, validation, sample_result):
        """count 聚合通过"""
        answer = AnswerSpec(
            answer="共3个区域。",
            summary="3个区域",
            semantic_model_key="mock_sales_model",
            source_mode="mock",
            metrics={"RegionCount": 3},
            evidence={
                "result_id": "qr_test_001",
                "semantic_model_key": "mock_sales_model",
                "row_count": 3,
                "source_mode": "mock",
                "metric_provenance": {
                    "RegionCount": {"source_field": "Region", "aggregation": "count"},
                },
            },
        )
        result = validation.validate_answer_strict(answer, sample_result)
        assert result.is_valid, f"应通过: {result.errors}"

    def test_min_aggregation_passes(self, validation, sample_result):
        """min 聚合通过"""
        answer = AnswerSpec(
            answer="最低销售额312万。",
            summary="最低312万",
            semantic_model_key="mock_sales_model",
            source_mode="mock",
            metrics={"MinSales": 3120000},
            evidence={
                "result_id": "qr_test_001",
                "semantic_model_key": "mock_sales_model",
                "row_count": 3,
                "source_mode": "mock",
                "metric_provenance": {
                    "MinSales": {"source_field": "SalesAmount", "aggregation": "min"},
                },
            },
        )
        result = validation.validate_answer_strict(answer, sample_result)
        assert result.is_valid, f"应通过: {result.errors}"

    def test_max_aggregation_passes(self, validation, sample_result):
        """max 聚合通过"""
        answer = AnswerSpec(
            answer="最高销售额456万。",
            summary="最高456万",
            semantic_model_key="mock_sales_model",
            source_mode="mock",
            metrics={"MaxSales": 4560000},
            evidence={
                "result_id": "qr_test_001",
                "semantic_model_key": "mock_sales_model",
                "row_count": 3,
                "source_mode": "mock",
                "metric_provenance": {
                    "MaxSales": {"source_field": "SalesAmount", "aggregation": "max"},
                },
            },
        )
        result = validation.validate_answer_strict(answer, sample_result)
        assert result.is_valid, f"应通过: {result.errors}"

    def test_old_free_text_evidence_cannot_bypass(self, validation, sample_result):
        """旧自由文本 evidence 不能绕过验证"""
        answer = AnswerSpec(
            answer="华南销售额最高。",
            summary="华南领先",
            semantic_model_key="mock_sales_model",
            source_mode="mock",
            metrics={"TotalSales": 11570000},
            evidence={
                "result_id": "qr_test_001",
                "semantic_model_key": "mock_sales_model",
                "row_count": 3,
                "source_mode": "mock",
                "source_field": "SalesAmount",  # 旧格式，不能替代 metric_provenance
                "calculation_note": "求和得出",
            },
        )
        result = validation.validate_answer_strict(answer, sample_result)
        assert not result.is_valid
        assert any("provenance" in e for e in result.errors)

    def test_no_metrics_no_provenance_ok(self, validation, sample_result):
        """metrics 为空时不要求 metric_provenance"""
        answer = AnswerSpec(
            answer="暂无符合条件的数据。",
            summary="无数据",
            semantic_model_key="mock_sales_model",
            source_mode="mock",
            metrics={},
            evidence={
                "result_id": "qr_test_001",
                "semantic_model_key": "mock_sales_model",
                "row_count": 3,
                "source_mode": "mock",
            },
        )
        result = validation.validate_answer_strict(answer, sample_result)
        assert result.is_valid, f"metrics 为空应通过: {result.errors}"


# ══════════════════════════════════════════════════════════════════════
# Table 类型严格比较
# ══════════════════════════════════════════════════════════════════════

class TestTableTypeStrictComparison:
    """Table 行比较区分 bool/int/float/string/null"""

    def test_true_not_equal_one(self):
        """True != 1"""
        assert _safe_repr(True) != _safe_repr(1)

    def test_one_not_equal_one_point_zero(self):
        """1 != 1.0"""
        assert _safe_repr(1) != _safe_repr(1.0)

    def test_one_not_equal_string_one(self):
        """1 != "1" """
        assert _safe_repr(1) != _safe_repr("1")

    def test_none_not_equal_string_none(self):
        """None != "None" """
        assert _safe_repr(None) != _safe_repr("None")

    def test_false_not_equal_zero(self):
        """False != 0"""
        assert _safe_repr(False) != _safe_repr(0)

    def test_same_type_same_value_match(self):
        """相同类型相同值匹配"""
        assert _safe_repr(42) == _safe_repr(42)
        assert _safe_repr("hello") == _safe_repr("hello")
        assert _safe_repr(None) == _safe_repr(None)
        assert _safe_repr(True) == _safe_repr(True)
        assert _safe_repr(3.14) == _safe_repr(3.14)

    def test_table_type_mix_in_rows(self, validation):
        """混合类型的行数据能正确区分"""
        result = QueryResult(
            result_id="qr_type_mix",
            semantic_model_key="mock_sales_model",
            columns=["Name", "IsActive", "Score", "Ratio"],
            rows=[["Test", True, 100, 0.95]],
            row_count=1,
            source_mode="mock",
        )
        spec = ReportSpec(
            title="类型测试",
            template_key="sales_weekly",
            data_source="mock_sales_model",
            source_mode="mock",
            tables=[
                TableSpec(
                    title="结果",
                    columns=["Name", "IsActive", "Score", "Ratio"],
                    rows=[["Test", True, 100, 0.95]],
                )
            ],
        )
        vr = validation.validate_report_strict(spec, result)
        assert vr.is_valid, f"正确类型应通过: {vr.errors}"

    def test_bool_as_int_string_rejected(self, validation):
        """bool 列中传 int 或 string 被拒绝"""
        result = QueryResult(
            result_id="qr_bool",
            semantic_model_key="mock_sales_model",
            columns=["Name", "IsActive"],
            rows=[["Test", True]],
            row_count=1,
            source_mode="mock",
        )
        spec = ReportSpec(
            title="测试",
            template_key="sales_weekly",
            data_source="mock_sales_model",
            source_mode="mock",
            tables=[
                TableSpec(
                    title="结果",
                    columns=["Name", "IsActive"],
                    rows=[["Test", 1]],  # int 代替 bool
                )
            ],
        )
        vr = validation.validate_report_strict(spec, result)
        assert not vr.is_valid, f"类型不匹配应失败"

    def test_int_as_float_rejected(self, validation):
        """int 列中传 float 被拒绝"""
        result = QueryResult(
            result_id="qr_int",
            semantic_model_key="mock_sales_model",
            columns=["Region", "Count"],
            rows=[["华南", 100]],
            row_count=1,
            source_mode="mock",
        )
        spec = ReportSpec(
            title="测试",
            template_key="sales_weekly",
            data_source="mock_sales_model",
            source_mode="mock",
            tables=[
                TableSpec(
                    title="结果",
                    columns=["Region", "Count"],
                    rows=[["华南", 100.0]],  # float 代替 int
                )
            ],
        )
        vr = validation.validate_report_strict(spec, result)
        assert not vr.is_valid, f"类型不匹配应失败"

    def test_null_vs_none_string_distinction(self, validation):
        """null 与 "None" 字符串区分"""
        result = QueryResult(
            result_id="qr_null",
            semantic_model_key="mock_sales_model",
            columns=["Region", "Note"],
            rows=[["华南", None]],
            row_count=1,
            source_mode="mock",
        )
        spec = ReportSpec(
            title="测试",
            template_key="sales_weekly",
            data_source="mock_sales_model",
            source_mode="mock",
            tables=[
                TableSpec(
                    title="结果",
                    columns=["Region", "Note"],
                    rows=[["华南", "None"]],  # 字符串 "None" vs null
                )
            ],
        )
        vr = validation.validate_report_strict(spec, result)
        assert not vr.is_valid, f"null vs 'None' 字符串应失败"

    def test_legal_column_subset_projection(self, validation):
        """合法列子集投影通过"""
        result = QueryResult(
            result_id="qr_subset",
            semantic_model_key="mock_sales_model",
            columns=["Region", "SalesAmount", "Month"],
            rows=[["华南", 4560000, "7月"]],
            row_count=1,
            source_mode="mock",
        )
        spec = ReportSpec(
            title="子集投影",
            template_key="sales_weekly",
            data_source="mock_sales_model",
            source_mode="mock",
            tables=[
                TableSpec(
                    title="结果",
                    columns=["Region", "SalesAmount"],  # 子集
                    rows=[["华南", 4560000]],
                )
            ],
        )
        vr = validation.validate_report_strict(spec, result)
        assert vr.is_valid, f"列子集投影应通过: {vr.errors}"

    def test_column_reorder_passes(self, validation):
        """列顺序调整通过"""
        result = QueryResult(
            result_id="qr_reorder",
            semantic_model_key="mock_sales_model",
            columns=["Region", "SalesAmount"],
            rows=[["华南", 4560000]],
            row_count=1,
            source_mode="mock",
        )
        spec = ReportSpec(
            title="列顺序调整",
            template_key="sales_weekly",
            data_source="mock_sales_model",
            source_mode="mock",
            tables=[
                TableSpec(
                    title="结果",
                    columns=["SalesAmount", "Region"],  # 顺序不同
                    rows=[[4560000, "华南"]],
                )
            ],
        )
        vr = validation.validate_report_strict(spec, result)
        assert vr.is_valid, f"列顺序调整应通过: {vr.errors}"

    def test_cross_row_splice_rejected(self, validation):
        """跨行拼接拒绝"""
        result = QueryResult(
            result_id="qr_splice",
            semantic_model_key="mock_sales_model",
            columns=["Region", "SalesAmount"],
            rows=[["华南", 4560000], ["华东", 3890000]],
            row_count=2,
            source_mode="mock",
        )
        spec = ReportSpec(
            title="跨行拼接",
            template_key="sales_weekly",
            data_source="mock_sales_model",
            source_mode="mock",
            tables=[
                TableSpec(
                    title="结果",
                    columns=["Region", "SalesAmount"],
                    rows=[["华南", 3890000]],  # Region 来自行0，SalesAmount 来自行1
                )
            ],
        )
        vr = validation.validate_report_strict(spec, result)
        assert not vr.is_valid, f"跨行拼接应失败"

    def test_duplicate_row_count_limit(self, validation):
        """重复行数量限制保持有效"""
        result = QueryResult(
            result_id="qr_dup",
            semantic_model_key="mock_sales_model",
            columns=["Region", "SalesAmount"],
            rows=[["华南", 4560000]],  # 只有1行
            row_count=1,
            source_mode="mock",
        )
        spec = ReportSpec(
            title="重复超限",
            template_key="sales_weekly",
            data_source="mock_sales_model",
            source_mode="mock",
            tables=[
                TableSpec(
                    title="结果",
                    columns=["Region", "SalesAmount"],
                    rows=[["华南", 4560000], ["华南", 4560000]],  # 重复2次，来源只有1次
                )
            ],
        )
        vr = validation.validate_report_strict(spec, result)
        assert not vr.is_valid, f"重复超限应失败"


# ══════════════════════════════════════════════════════════════════════
# 模板权限边界
# ══════════════════════════════════════════════════════════════════════

class TestTemplatePermissions:
    """模板冲突和空权限集合"""

    def test_template_conflict_zero_calls(self):
        """两个模板冲突时零次调用 — 在 DeepSeekReportSpecService.generate() 入口拒绝"""
        from backend.app.report.deepseek_spec_service import (
            DeepSeekReportSpecService,
            ReportSpecGenerationError,
        )
        from backend.app.schemas.data_contracts import QueryPlan, StructuredFilter
        from backend.app.llm.base import LLMProvider

        class EmptyProvider(LLMProvider):
            provider_name = "empty"
            is_mock = False
            async def generate(self, request, output_type):
                raise RuntimeError("不应被调用")

        svc = DeepSeekReportSpecService(provider=EmptyProvider())
        intent = IntentSpec(
            intent=IntentType.REPORT_GENERATION,
            confidence=0.9,
            normalized_question="生成报表",
        )
        qp = QueryPlan(
            normalized_question="生成报表",
            semantic_model_key="mock_sales_model",
            measures=["TotalSales"],
            dimensions=["Region"],
            filters=[],
            requested_template="sales_weekly",
        )
        qr = QueryResult(
            result_id="qr_conflict",
            semantic_model_key="mock_sales_model",
            columns=["Region"],
            rows=[["华南"]],
            row_count=1,
            source_mode="mock",
        )
        from backend.app.schemas.data_contracts import SemanticModelSchema, TableSchema, ColumnSchema, MeasureSchema
        schema = SemanticModelSchema(
            name="Test", key="mock_sales_model",
            tables=[TableSchema(name="T", columns=[ColumnSchema(name="Region", data_type="string")], measures=[])],
        )

        import asyncio

        async def _run():
            with pytest.raises(ReportSpecGenerationError, match="冲突"):
                await svc.generate(
                    "生成报表", intent, qp, qr, schema,
                    template_key="operating_overview",  # 与 requested_template 不一致
                )

        asyncio.run(_run())

    def test_allowed_templates_none_uses_default(self):
        """allowed_templates=None 使用默认集合"""
        from backend.app.report.deepseek_spec_service import _DEFAULT_ALLOWED_TEMPLATES
        assert "sales_weekly" in _DEFAULT_ALLOWED_TEMPLATES
        assert "satisfaction" in _DEFAULT_ALLOWED_TEMPLATES
        assert "operating_overview" in _DEFAULT_ALLOWED_TEMPLATES

    def test_allowed_templates_empty_rejects_all(self):
        """allowed_templates=set() 拒绝所有模板"""
        from backend.app.report.deepseek_spec_service import (
            DeepSeekReportSpecService,
            ReportSpecGenerationError,
        )
        from backend.app.schemas.data_contracts import QueryPlan
        from backend.app.llm.base import LLMProvider

        class EmptyProvider(LLMProvider):
            provider_name = "empty"
            is_mock = False
            async def generate(self, request, output_type):
                raise RuntimeError("不应被调用")

        svc = DeepSeekReportSpecService(provider=EmptyProvider())
        intent = IntentSpec(
            intent=IntentType.REPORT_GENERATION,
            confidence=0.9,
            normalized_question="生成报表",
        )
        qp = QueryPlan(
            normalized_question="生成报表",
            semantic_model_key="mock_sales_model",
            measures=["TotalSales"],
            dimensions=["Region"],
            filters=[],
        )
        qr = QueryResult(
            result_id="qr_empty_perm",
            semantic_model_key="mock_sales_model",
            columns=["Region"],
            rows=[["华南"]],
            row_count=1,
            source_mode="mock",
        )
        from backend.app.schemas.data_contracts import SemanticModelSchema, TableSchema, ColumnSchema, MeasureSchema
        schema = SemanticModelSchema(
            name="Test", key="mock_sales_model",
            tables=[TableSchema(name="T", columns=[ColumnSchema(name="Region", data_type="string")], measures=[])],
        )

        import asyncio

        async def _run():
            with pytest.raises(ReportSpecGenerationError, match="不在允许白名单"):
                await svc.generate(
                    "生成报表", intent, qp, qr, schema,
                    allowed_templates=set(),  # 空集合 = 无权限
                )

        asyncio.run(_run())

    def test_custom_whitelist_allows_only_specified(self):
        """自定义白名单只允许指定模板"""
        from backend.app.report.deepseek_spec_service import (
            DeepSeekReportSpecService,
            ReportSpecGenerationError,
        )
        from backend.app.schemas.data_contracts import QueryPlan
        from backend.app.llm.base import LLMProvider

        class EmptyProvider(LLMProvider):
            provider_name = "empty"
            is_mock = False
            async def generate(self, request, output_type):
                raise RuntimeError("不应被调用")

        svc = DeepSeekReportSpecService(provider=EmptyProvider())
        intent = IntentSpec(
            intent=IntentType.REPORT_GENERATION,
            confidence=0.9,
            normalized_question="生成报表",
        )
        qp = QueryPlan(
            normalized_question="生成报表",
            semantic_model_key="mock_sales_model",
            measures=["TotalSales"],
            dimensions=["Region"],
            filters=[],
        )
        qr = QueryResult(
            result_id="qr_custom",
            semantic_model_key="mock_sales_model",
            columns=["Region"],
            rows=[["华南"]],
            row_count=1,
            source_mode="mock",
        )
        from backend.app.schemas.data_contracts import SemanticModelSchema, TableSchema, ColumnSchema, MeasureSchema
        schema = SemanticModelSchema(
            name="Test", key="mock_sales_model",
            tables=[TableSchema(name="T", columns=[ColumnSchema(name="Region", data_type="string")], measures=[])],
        )

        import asyncio

        async def _run_rejected():
            with pytest.raises(ReportSpecGenerationError, match="不在允许白名单"):
                await svc.generate(
                    "生成报表", intent, qp, qr, schema,
                    allowed_templates={"satisfaction"},  # sales_weekly 不在白名单
                    template_key="sales_weekly",
                )

        asyncio.run(_run_rejected())


# ══════════════════════════════════════════════════════════════════════
# 数值容差
# ══════════════════════════════════════════════════════════════════════

class TestNumericTolerance:
    """数值容差集中定义"""

    def test_tolerance_is_reasonable(self):
        """容差值合理"""
        assert _NUMERIC_TOLERANCE == 0.01
        assert 0.001 < _NUMERIC_TOLERANCE < 0.1

    def test_allowed_aggregations(self):
        """允许的聚合集合正确"""
        assert _ALLOWED_AGGREGATIONS == {"direct", "sum", "avg", "count", "min", "max"}


class TestComputeAggregation:
    """_compute_aggregation 辅助函数"""

    def test_direct_returns_values(self):
        result = _compute_aggregation([10.0, 20.0, 30.0], "direct")
        assert result == [10.0, 20.0, 30.0]

    def test_sum_returns_total(self):
        assert _compute_aggregation([10.0, 20.0, 30.0], "sum") == 60.0

    def test_avg_returns_mean(self):
        assert _compute_aggregation([10.0, 20.0, 30.0], "avg") == 20.0

    def test_count_returns_length(self):
        assert _compute_aggregation([10.0, 20.0, 30.0], "count") == 3.0

    def test_min_returns_minimum(self):
        assert _compute_aggregation([10.0, 20.0, 30.0], "min") == 10.0

    def test_max_returns_maximum(self):
        assert _compute_aggregation([10.0, 20.0, 30.0], "max") == 30.0

    def test_empty_values_count_returns_zero(self):
        assert _compute_aggregation([], "count") == 0.0

    def test_empty_values_other_returns_none(self):
        assert _compute_aggregation([], "sum") is None
        assert _compute_aggregation([], "avg") is None
        assert _compute_aggregation([], "direct") is None


# ══════════════════════════════════════════════════════════════════════
# Evidence 错误诊断脱敏
# ══════════════════════════════════════════════════════════════════════

class TestErrorDesensitization:
    """错误消息不泄露原始数据"""

    def test_kpi_error_no_full_row_data(self, validation, sample_result):
        """KPI 错误不输出完整数据行"""
        spec = ReportSpec(
            title="测试",
            template_key="sales_weekly",
            data_source="mock_sales_model",
            source_mode="mock",
            kpis=[KPISpec(name="虚构", value=999, format="number", field="SalesAmount")],
        )
        result = validation.validate_report_strict(spec, sample_result)
        assert not result.is_valid
        for err in result.errors:
            # 不应包含完整行数据
            assert "4560000" not in err, f"错误消息泄漏数值: {err}"

    def test_answer_error_no_secret_in_message(self, validation, sample_result):
        """Answer 错误不包含 Secret"""
        answer = AnswerSpec(
            answer="测试",
            summary="测试",
            semantic_model_key="",  # 触发错误
            source_mode="mock",
        )
        result = validation.validate_answer_strict(answer, sample_result)
        assert not result.is_valid
        for err in result.errors:
            assert "sk-" not in err.lower()
            assert "api_key" not in err.lower()


# ══════════════════════════════════════════════════════════════════════
# QueryPlan 模板 Key 契约
# ══════════════════════════════════════════════════════════════════════

_TEMPLATE_WHITELIST = {"sales_weekly", "satisfaction", "operating_overview"}


class TestQueryPlanTemplateValidation:
    """ValidationService.validate_query_plan 校验 requested_template"""

    def test_valid_template_sales_weekly_passes(self):
        """requested_template=sales_weekly 通过"""
        from backend.app.schemas.data_contracts import QueryPlan
        from backend.app.schemas.data_contracts import SemanticModelSchema, TableSchema, ColumnSchema, MeasureSchema

        validation = ValidationService(allowed_templates=sorted(_TEMPLATE_WHITELIST))
        plan = QueryPlan(
            normalized_question="本周销售情况",
            semantic_model_key="mock_sales_model",
            requested_template="sales_weekly",
        )
        schema = SemanticModelSchema(
            name="Test", key="mock_sales_model",
            tables=[TableSchema(name="T", columns=[ColumnSchema(name="Region", data_type="string")], measures=[])],
        )
        result = validation.validate_query_plan(plan, schema)
        assert result.is_valid, f"合法模板应通过: {result.errors}"

    def test_valid_template_satisfaction_passes(self):
        """requested_template=satisfaction 通过"""
        from backend.app.schemas.data_contracts import QueryPlan
        from backend.app.schemas.data_contracts import SemanticModelSchema, TableSchema, ColumnSchema, MeasureSchema

        validation = ValidationService(allowed_templates=sorted(_TEMPLATE_WHITELIST))
        plan = QueryPlan(
            normalized_question="满意度调查",
            semantic_model_key="mock_sales_model",
            requested_template="satisfaction",
        )
        schema = SemanticModelSchema(
            name="Test", key="mock_sales_model",
            tables=[TableSchema(name="T", columns=[ColumnSchema(name="Region", data_type="string")], measures=[])],
        )
        result = validation.validate_query_plan(plan, schema)
        assert result.is_valid, f"satisfaction 应通过: {result.errors}"

    def test_valid_template_operating_overview_passes(self):
        """requested_template=operating_overview 通过"""
        from backend.app.schemas.data_contracts import QueryPlan
        from backend.app.schemas.data_contracts import SemanticModelSchema, TableSchema, ColumnSchema, MeasureSchema

        validation = ValidationService(allowed_templates=sorted(_TEMPLATE_WHITELIST))
        plan = QueryPlan(
            normalized_question="经营概览",
            semantic_model_key="mock_sales_model",
            requested_template="operating_overview",
        )
        schema = SemanticModelSchema(
            name="Test", key="mock_sales_model",
            tables=[TableSchema(name="T", columns=[ColumnSchema(name="Region", data_type="string")], measures=[])],
        )
        result = validation.validate_query_plan(plan, schema)
        assert result.is_valid, f"operating_overview 应通过: {result.errors}"

    def test_null_template_passes(self):
        """requested_template=null 通过"""
        from backend.app.schemas.data_contracts import QueryPlan
        from backend.app.schemas.data_contracts import SemanticModelSchema, TableSchema, ColumnSchema, MeasureSchema

        validation = ValidationService()
        plan = QueryPlan(
            normalized_question="销售额查询",
            semantic_model_key="mock_sales_model",
            requested_template=None,
        )
        schema = SemanticModelSchema(
            name="Test", key="mock_sales_model",
            tables=[TableSchema(name="T", columns=[ColumnSchema(name="Region", data_type="string")], measures=[])],
        )
        result = validation.validate_query_plan(plan, schema)
        assert result.is_valid, f"null 应通过: {result.errors}"

    def test_chinese_template_name_rejected(self):
        """中文模板名称拒绝"""
        from backend.app.schemas.data_contracts import QueryPlan
        from backend.app.schemas.data_contracts import SemanticModelSchema, TableSchema, ColumnSchema, MeasureSchema

        validation = ValidationService()
        plan = QueryPlan(
            normalized_question="销售经营周报",
            semantic_model_key="mock_sales_model",
            requested_template="销售经营周报",
        )
        schema = SemanticModelSchema(
            name="Test", key="mock_sales_model",
            tables=[TableSchema(name="T", columns=[ColumnSchema(name="Region", data_type="string")], measures=[])],
        )
        result = validation.validate_query_plan(plan, schema)
        assert not result.is_valid
        assert any("template_not_allowed" in e for e in result.errors)

    def test_invalid_template_key_rejected(self):
        """不在白名单的 Key 拒绝"""
        from backend.app.schemas.data_contracts import QueryPlan
        from backend.app.schemas.data_contracts import SemanticModelSchema, TableSchema, ColumnSchema, MeasureSchema

        validation = ValidationService()
        plan = QueryPlan(
            normalized_question="测试",
            semantic_model_key="mock_sales_model",
            requested_template="weekly_summary",
        )
        schema = SemanticModelSchema(
            name="Test", key="mock_sales_model",
            tables=[TableSchema(name="T", columns=[ColumnSchema(name="Region", data_type="string")], measures=[])],
        )
        result = validation.validate_query_plan(plan, schema)
        assert not result.is_valid
        assert any("template_not_allowed" in e for e in result.errors)

    def test_error_does_not_echo_full_template_text(self):
        """错误不回显完整不可信模板文本"""
        from backend.app.schemas.data_contracts import QueryPlan
        from backend.app.schemas.data_contracts import SemanticModelSchema, TableSchema, ColumnSchema, MeasureSchema

        validation = ValidationService()
        plan = QueryPlan(
            normalized_question="测试",
            semantic_model_key="mock_sales_model",
            requested_template="恶意输入<script>alert(1)</script>",
        )
        schema = SemanticModelSchema(
            name="Test", key="mock_sales_model",
            tables=[TableSchema(name="T", columns=[ColumnSchema(name="Region", data_type="string")], measures=[])],
        )
        result = validation.validate_query_plan(plan, schema)
        assert not result.is_valid
        for err in result.errors:
            assert "<script>" not in err, f"错误消息不应包含不可信输入: {err}"


class TestQueryPlanServiceTemplateRepair:
    """DeepSeekQueryPlanService 模板修复"""

    @pytest.mark.asyncio
    async def test_chinese_template_triggers_repair_then_succeeds(self):
        """首次中文模板名称触发修复，修复后合法 Key 通过"""
        from backend.app.query_plan.deepseek_service import DeepSeekQueryPlanService
        from backend.app.llm.base import LLMProvider, LLMResponse, LLMRequest
        from backend.app.schemas.data_contracts import QueryPlan as QP

        class RepairProvider(LLMProvider):
            provider_name = "repair"
            is_mock = False
            def __init__(self):
                self.calls: list[LLMRequest] = []
            async def generate(self, request: LLMRequest, output_type):
                self.calls.append(request)
                if len(self.calls) == 1:
                    plan = QP(
                        normalized_question="销售经营周报",
                        semantic_model_key="mock_sales_model",
                        measures=["TotalSales"],
                        dimensions=["Region"],
                        requested_template="销售经营周报",
                    )
                    return LLMResponse(
                        content="{}", structured=plan, model="test",
                        usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                    )
                else:
                    plan = QP(
                        normalized_question="销售经营周报",
                        semantic_model_key="mock_sales_model",
                        measures=["TotalSales"],
                        dimensions=["Region"],
                        requested_template="sales_report",
                    )
                    return LLMResponse(
                        content="{}", structured=plan, model="test",
                        usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                    )

        from backend.app.schemas.data_contracts import SemanticModelSchema, TableSchema, ColumnSchema, MeasureSchema
        schema = SemanticModelSchema(
            name="Test", key="mock_sales_model",
            tables=[
                TableSchema(name="Sales", columns=[
                    ColumnSchema(name="Region", data_type="string"),
                    ColumnSchema(name="SalesAmount", data_type="decimal"),
                ], measures=[
                    MeasureSchema(name="TotalSales", data_type="decimal"),
                ]),
            ],
        )
        intent = IntentSpec(
            intent=IntentType.REPORT_GENERATION,
            confidence=0.9,
            normalized_question="销售经营周报",
        )

        provider = RepairProvider()
        svc = DeepSeekQueryPlanService(provider=provider, max_format_repairs=1)
        plan = await svc.generate("销售经营周报", intent, schema, semantic_model_key="mock_sales_model")
        assert plan.requested_template == "sales_report"
        assert len(provider.calls) == 2, f"应为2次调用，实际{len(provider.calls)}"

    @pytest.mark.asyncio
    async def test_invalid_template_fails_after_2_attempts(self):
        """两次仍非法模板则失败"""
        from backend.app.query_plan.deepseek_service import DeepSeekQueryPlanService, QueryPlanError
        from backend.app.llm.base import LLMProvider, LLMResponse, LLMRequest
        from backend.app.schemas.data_contracts import QueryPlan as QP

        class StubbornProvider(LLMProvider):
            provider_name = "stubborn"
            is_mock = False
            def __init__(self):
                self.calls: list[LLMRequest] = []
            async def generate(self, request: LLMRequest, output_type):
                self.calls.append(request)
                plan = QP(
                    normalized_question="测试",
                    semantic_model_key="mock_sales_model",
                    measures=["TotalSales"],
                    dimensions=["Region"],
                    requested_template="bad_template",
                )
                return LLMResponse(
                    content="{}", structured=plan, model="test",
                    usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                )

        from backend.app.schemas.data_contracts import SemanticModelSchema, TableSchema, ColumnSchema, MeasureSchema
        schema = SemanticModelSchema(
            name="Test", key="mock_sales_model",
            tables=[
                TableSchema(name="Sales", columns=[
                    ColumnSchema(name="Region", data_type="string"),
                    ColumnSchema(name="SalesAmount", data_type="decimal"),
                ], measures=[
                    MeasureSchema(name="TotalSales", data_type="decimal"),
                ]),
            ],
        )
        intent = IntentSpec(
            intent=IntentType.REPORT_GENERATION,
            confidence=0.9,
            normalized_question="测试",
        )

        provider = StubbornProvider()
        svc = DeepSeekQueryPlanService(provider=provider, max_format_repairs=1)
        with pytest.raises(QueryPlanError, match="template"):
            await svc.generate("测试", intent, schema, semantic_model_key="mock_sales_model")
        assert len(provider.calls) == 2

    @pytest.mark.asyncio
    async def test_valid_template_no_repair(self):
        """合法模板一次通过，无需修复"""
        from backend.app.query_plan.deepseek_service import DeepSeekQueryPlanService
        from backend.app.llm.base import LLMProvider, LLMResponse, LLMRequest
        from backend.app.schemas.data_contracts import QueryPlan as QP

        class OneCallProvider(LLMProvider):
            provider_name = "onecall"
            is_mock = False
            def __init__(self):
                self.calls: list[LLMRequest] = []
            async def generate(self, request: LLMRequest, output_type):
                self.calls.append(request)
                plan = QP(
                    normalized_question="测试",
                    semantic_model_key="mock_sales_model",
                    measures=["TotalSales"],
                    dimensions=["Region"],
                    requested_template="sales_report",
                )
                return LLMResponse(
                    content="{}", structured=plan, model="test",
                    usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                )

        from backend.app.schemas.data_contracts import SemanticModelSchema, TableSchema, ColumnSchema, MeasureSchema
        schema = SemanticModelSchema(
            name="Test", key="mock_sales_model",
            tables=[
                TableSchema(name="Sales", columns=[
                    ColumnSchema(name="Region", data_type="string"),
                    ColumnSchema(name="SalesAmount", data_type="decimal"),
                ], measures=[
                    MeasureSchema(name="TotalSales", data_type="decimal"),
                ]),
            ],
        )
        intent = IntentSpec(
            intent=IntentType.REPORT_GENERATION,
            confidence=0.9,
            normalized_question="测试",
        )

        provider = OneCallProvider()
        svc = DeepSeekQueryPlanService(provider=provider, max_format_repairs=1)
        plan = await svc.generate("测试", intent, schema, semantic_model_key="mock_sales_model")
        assert plan.requested_template == "sales_report"
        assert len(provider.calls) == 1

    @pytest.mark.asyncio
    async def test_provider_calls_max_2(self):
        """Provider 最多调用2次"""
        from backend.app.query_plan.deepseek_service import DeepSeekQueryPlanService, QueryPlanError
        from backend.app.llm.base import LLMProvider, LLMResponse, LLMRequest
        from backend.app.schemas.data_contracts import QueryPlan as QP

        class MaxCallProvider(LLMProvider):
            provider_name = "maxcall"
            is_mock = False
            def __init__(self):
                self.calls: list[LLMRequest] = []
            async def generate(self, request: LLMRequest, output_type):
                self.calls.append(request)
                if len(self.calls) > 2:
                    raise RuntimeError("超过最大调用次数")
                plan = QP(
                    normalized_question="测试",
                    semantic_model_key="mock_sales_model",
                    measures=["TotalSales"],
                    dimensions=["Region"],
                    requested_template="销售经营周报",
                )
                return LLMResponse(
                    content="{}", structured=plan, model="test",
                    usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                )

        from backend.app.schemas.data_contracts import SemanticModelSchema, TableSchema, ColumnSchema, MeasureSchema
        schema = SemanticModelSchema(
            name="Test", key="mock_sales_model",
            tables=[
                TableSchema(name="Sales", columns=[
                    ColumnSchema(name="Region", data_type="string"),
                    ColumnSchema(name="SalesAmount", data_type="decimal"),
                ], measures=[
                    MeasureSchema(name="TotalSales", data_type="decimal"),
                ]),
            ],
        )
        intent = IntentSpec(
            intent=IntentType.REPORT_GENERATION,
            confidence=0.9,
            normalized_question="测试",
        )

        provider = MaxCallProvider()
        svc = DeepSeekQueryPlanService(provider=provider, max_format_repairs=1)
        with pytest.raises(QueryPlanError):
            await svc.generate("测试", intent, schema, semantic_model_key="mock_sales_model")
        assert len(provider.calls) == 2, f"应为2次，实际{len(provider.calls)}"


# ══════════════════════════════════════════════════════════════════
# M2.4 Layer 2 / Layer 3 真实 Schema 语义验证
# ══════════════════════════════════════════════════════════════════


def _m24_semantic_schema():
    from backend.app.schemas.data_contracts import (
        ColumnSchema,
        MeasureSchema,
        RelationshipSchema,
        SemanticModelSchema,
        TableSchema,
    )

    return SemanticModelSchema(
        name="Local Desktop Model",
        key="local_desktop_model",
        tables=[
            TableSchema(
                name="Sales",
                columns=[
                    ColumnSchema(name="ProductId", data_type="int64"),
                    ColumnSchema(name="Quantity", data_type="int64"),
                    ColumnSchema(name="UnitPrice", data_type="decimal"),
                    ColumnSchema(name="InternalKey", data_type="int64", is_hidden=True),
                ],
                measures=[
                    MeasureSchema(name="Total Sales", data_type="decimal"),
                    MeasureSchema(name="Total Quantity", data_type="int64"),
                    MeasureSchema(name="Hidden KPI", is_hidden=True),
                ],
            ),
            TableSchema(
                name="Product",
                columns=[
                    ColumnSchema(name="ProductId", data_type="int64"),
                    ColumnSchema(name="Category", data_type="string"),
                ],
            ),
            TableSchema(
                name="Geography",
                columns=[ColumnSchema(name="Country", data_type="string")],
            ),
        ],
        relationships=[
            RelationshipSchema(
                from_table="Sales",
                from_column="ProductId",
                to_table="Product",
                to_column="ProductId",
            )
        ],
    )


def _m24_plan(**updates):
    from backend.app.schemas.data_contracts import QueryPlan, StructuredFilter

    values = {
        "normalized_question": "Electronics 类别的销售额",
        "semantic_model_key": "local_desktop_model",
        "measures": ["Total Sales"],
        "dimensions": ["Category"],
        "filters": [StructuredFilter(field="Category", value="Electronics")],
    }
    values.update(updates)
    return QueryPlan(**values)


class TestM24QueryPlanSemanticGrounding:
    def _validate(self, plan):
        return ValidationService(
            allowed_semantic_models=["local_desktop_model"]
        ).validate_query_plan(
            plan,
            _m24_semantic_schema(),
            enforce_semantic_grounding=True,
        )

    def test_real_measure_dimension_and_filter_pass(self):
        assert self._validate(_m24_plan()).is_valid

    def test_unverified_filter_operator_is_rejected_only_on_real_path(self):
        from backend.app.schemas.data_contracts import FilterOperator, StructuredFilter

        plan = _m24_plan(filters=[StructuredFilter(
            field="Category", operator=FilterOperator.NE, value="Electronics"
        )])
        real_result = self._validate(plan)
        mock_result = ValidationService(
            allowed_semantic_models=["local_desktop_model"]
        ).validate_query_plan(plan, _m24_semantic_schema())

        assert not real_result.is_valid
        assert real_result.error_code == "filter_operator_not_verified"
        assert mock_result.is_valid

    def test_filter_capability_matrix_does_not_overclaim(self):
        from backend.app.schemas.data_contracts import (
            FILTER_OPERATOR_CAPABILITIES,
            FilterCapabilityStatus,
            FilterOperator,
        )

        assert FILTER_OPERATOR_CAPABILITIES[FilterOperator.EQ] == (
            FilterCapabilityStatus.SUPPORTED
        )
        assert FILTER_OPERATOR_CAPABILITIES[FilterOperator.IN_SET] == (
            FilterCapabilityStatus.SUPPORTED
        )
        assert all(
            status == FilterCapabilityStatus.NOT_VERIFIED
            for operator, status in FILTER_OPERATOR_CAPABILITIES.items()
            if operator not in {FilterOperator.EQ, FilterOperator.IN_SET}
        )

    def test_numeric_column_cannot_be_used_as_measure(self):
        result = self._validate(_m24_plan(measures=["UnitPrice"]))
        assert not result.is_valid
        assert any("Column, not a Measure" in error for error in result.errors)

    def test_nonexistent_measure_is_rejected(self):
        result = self._validate(_m24_plan(measures=["Imaginary KPI"]))
        assert not result.is_valid
        assert any("measure_not_found" in error for error in result.errors)

    def test_measure_cannot_be_used_as_dimension(self):
        result = self._validate(_m24_plan(dimensions=["Total Sales"]))
        assert not result.is_valid
        assert any("dimension_measure_confusion" in error for error in result.errors)

    def test_measure_cannot_be_used_as_filter_field(self):
        from backend.app.schemas.data_contracts import StructuredFilter

        result = self._validate(_m24_plan(
            filters=[StructuredFilter(field="Total Sales", value=1)]
        ))
        assert not result.is_valid
        assert any("filter_measure_confusion" in error for error in result.errors)

    @pytest.mark.parametrize("hidden_name", ["Hidden KPI", "InternalKey"])
    def test_hidden_objects_are_rejected(self, hidden_name):
        if hidden_name == "Hidden KPI":
            plan = _m24_plan(measures=[hidden_name])
        else:
            plan = _m24_plan(dimensions=[hidden_name])
        result = self._validate(plan)
        assert not result.is_valid
        assert any("hidden" in error for error in result.errors)

    def test_unrelated_dimension_table_is_rejected(self):
        result = self._validate(_m24_plan(dimensions=["Country"], filters=[]))
        assert not result.is_valid
        assert any("table_unrelated" in error for error in result.errors)

    def test_hidden_system_relationship_does_not_reject_measure_only_plan(self):
        """与当前计划无关的自动日期/系统关系不是 QueryPlan 语义错误。"""
        from backend.app.schemas.data_contracts import RelationshipSchema, TableSchema

        schema = _m24_semantic_schema()
        schema.tables.append(TableSchema(
            name="LocalDateTable_hidden",
            is_hidden=True,
            is_system_managed=True,
        ))
        schema.relationships.append(RelationshipSchema(
            from_table="Sales",
            from_column="ProductId",
            to_table="LocalDateTable_hidden",
            to_column="Date",
        ))
        result = ValidationService(
            allowed_semantic_models=["local_desktop_model"]
        ).validate_query_plan(
            _m24_plan(dimensions=[], filters=[]),
            schema,
            enforce_semantic_grounding=True,
        )
        assert result.is_valid


class TestM24DAXQueryPlanConsistency:
    def _validate(self, dax: str, plan=None, model_key="local_desktop_model"):
        from backend.app.schemas.data_contracts import DAXRequest

        return ValidationService(
            allowed_semantic_models=["local_desktop_model"]
        ).validate_dax_query_plan_consistency(
            DAXRequest(semantic_model_key=model_key, dax=dax),
            plan or _m24_plan(),
            _m24_semantic_schema(),
        )

    def test_matching_measure_dimension_and_filter_pass(self):
        dax = (
            "EVALUATE SUMMARIZECOLUMNS("
            "'Product'[Category], "
            "TREATAS({\"Electronics\"}, 'Product'[Category]), "
            "\"Total Sales\", [Total Sales])"
        )
        assert self._validate(dax).is_valid

    def test_filter_value_mismatch_is_rejected(self):
        dax = (
            "EVALUATE SUMMARIZECOLUMNS("
            "'Product'[Category], "
            "TREATAS({\"Furniture\"}, 'Product'[Category]), "
            "\"Total Sales\", [Total Sales])"
        )
        result = self._validate(dax)
        assert not result.is_valid
        assert "dax_filter_operator_or_value_mismatch" in result.errors

    def test_filter_operator_mismatch_is_rejected(self):
        dax = (
            "EVALUATE SUMMARIZECOLUMNS("
            "'Product'[Category], "
            "FILTER('Product', 'Product'[Category] <> \"Electronics\"), "
            "\"Total Sales\", [Total Sales])"
        )
        result = self._validate(dax)
        assert not result.is_valid
        assert "dax_filter_structure_not_verifiable" in result.errors

    def test_extra_business_filter_is_rejected(self):
        dax = (
            "EVALUATE SUMMARIZECOLUMNS("
            "'Product'[Category], "
            "TREATAS({\"Electronics\"}, 'Product'[Category]), "
            "TREATAS({\"Furniture\"}, 'Product'[Category]), "
            "\"Total Sales\", [Total Sales])"
        )
        result = self._validate(dax)
        assert not result.is_valid
        assert "dax_filter_extra_or_changed" in result.errors

    def test_filter_field_is_not_an_implicit_group_by_dimension(self):
        dax = (
            "EVALUATE SUMMARIZECOLUMNS("
            "'Product'[Category], "
            "TREATAS({\"Electronics\"}, 'Product'[Category]), "
            "\"Total Sales\", [Total Sales])"
        )
        result = self._validate(dax, plan=_m24_plan(dimensions=[]))

        assert not result.is_valid
        assert any("unplanned_group_by_dimension" in error for error in result.errors)

    def test_declared_dimension_is_allowed_as_group_by(self):
        dax = (
            "EVALUATE SUMMARIZECOLUMNS("
            "'Product'[Category], "
            "TREATAS({\"Electronics\"}, 'Product'[Category]), "
            "\"Total Sales\", [Total Sales])"
        )

        assert self._validate(dax, plan=_m24_plan(dimensions=["Category"])).is_valid

    def test_filter_only_column_passes_without_group_by(self):
        dax = (
            "EVALUATE SUMMARIZECOLUMNS("
            "TREATAS({\"Electronics\"}, 'Product'[Category]), "
            "\"Total Sales\", [Total Sales])"
        )

        assert self._validate(dax, plan=_m24_plan(dimensions=[])).is_valid

    def test_legal_filter_before_name_expression_pair_passes(self):
        dax = (
            "EVALUATE SUMMARIZECOLUMNS("
            "TREATAS({\"Electronics\"}, 'Product'[Category]), "
            "\"Total Sales\", [Total Sales])"
        )

        assert self._validate(dax, plan=_m24_plan(dimensions=[])).is_valid

    def test_filter_after_name_expression_pair_is_rejected(self):
        dax = (
            "EVALUATE SUMMARIZECOLUMNS("
            "\"Total Sales\", [Total Sales], "
            "TREATAS({\"Electronics\"}, 'Product'[Category]))"
        )
        result = self._validate(dax, plan=_m24_plan(dimensions=[]))

        assert not result.is_valid
        assert "dax_summarizecolumns_filter_after_name_expression" in result.errors

    def test_name_expression_pair_must_be_complete(self):
        dax = (
            "EVALUATE SUMMARIZECOLUMNS("
            "TREATAS({\"Electronics\"}, 'Product'[Category]), "
            "\"Total Sales\")"
        )
        result = self._validate(dax, plan=_m24_plan(dimensions=[]))

        assert not result.is_valid
        assert "dax_summarizecolumns_name_expression_unpaired" in result.errors

    def test_measure_expression_remains_required(self):
        dax = (
            "EVALUATE SUMMARIZECOLUMNS("
            "TREATAS({\"Electronics\"}, 'Product'[Category]), "
            "\"Quantity\", [Total Quantity])"
        )
        result = self._validate(dax, plan=_m24_plan(dimensions=[]))

        assert not result.is_valid
        assert any("missing_query_plan_measure" in error for error in result.errors)

    def test_missing_query_plan_measure_is_rejected(self):
        dax = (
            "EVALUATE SUMMARIZECOLUMNS("
            "'Product'[Category], "
            "TREATAS({\"Electronics\"}, 'Product'[Category]), "
            "\"Value\", SUM('Sales'[UnitPrice]))"
        )
        result = self._validate(dax)
        assert not result.is_valid
        assert "dax_measure_expression_not_allowed" in result.errors

    def test_nonexistent_dax_object_is_rejected(self):
        dax = (
            "EVALUATE SUMMARIZECOLUMNS("
            "'Product'[Category], "
            "TREATAS({\"Electronics\"}, 'Product'[Category]), "
            "\"Total Sales\", [Total Sales], \"Ghost\", [Ghost KPI])"
        )
        result = self._validate(dax)
        assert not result.is_valid
        assert any("unknown_measure" in error for error in result.errors)

    def test_cross_model_dax_is_rejected(self):
        dax = (
            "EVALUATE SUMMARIZECOLUMNS("
            "'Product'[Category], "
            "TREATAS({\"Electronics\"}, 'Product'[Category]), "
            "\"Total Sales\", [Total Sales])"
        )
        result = self._validate(dax, model_key="other_model")
        assert not result.is_valid
        assert "dax_query_plan_model_mismatch" in result.errors

    def test_top_n_selection_and_presentation_ordering_match(self):
        plan = _m24_plan(filters=[], top_n=3, sort="desc")
        dax = (
            "EVALUATE TOPN(3, SUMMARIZECOLUMNS("
            "'Product'[Category], \"Total Sales\", [Total Sales]), "
            "[Total Sales], DESC) ORDER BY [Total Sales] DESC"
        )
        assert self._validate(dax, plan=plan).is_valid

    def test_top_n_value_mismatch_is_rejected(self):
        plan = _m24_plan(filters=[], top_n=3, sort="desc")
        dax = (
            "EVALUATE TOPN(5, SUMMARIZECOLUMNS("
            "'Product'[Category], \"Total Sales\", [Total Sales]), "
            "[Total Sales], DESC) ORDER BY [Total Sales] DESC"
        )
        result = self._validate(dax, plan=plan)
        assert "dax_top_n_value_mismatch" in result.errors

    def test_top_n_sort_direction_mismatch_is_rejected(self):
        plan = _m24_plan(filters=[], top_n=3, sort="desc")
        dax = (
            "EVALUATE TOPN(3, SUMMARIZECOLUMNS("
            "'Product'[Category], \"Total Sales\", [Total Sales]), "
            "[Total Sales], ASC) ORDER BY [Total Sales] DESC"
        )
        result = self._validate(dax, plan=plan)
        assert "dax_top_n_sort_direction_mismatch" in result.errors

    def test_top_n_sort_measure_mismatch_is_rejected(self):
        plan = _m24_plan(filters=[], top_n=3, sort="desc")
        dax = (
            "EVALUATE TOPN(3, SUMMARIZECOLUMNS("
            "'Product'[Category], \"Total Sales\", [Total Sales], "
            "\"Total Quantity\", [Total Quantity]), "
            "[Total Quantity], DESC) ORDER BY [Total Sales] DESC"
        )
        result = self._validate(dax, plan=plan)
        assert "dax_top_n_sort_measure_mismatch" in result.errors

    def test_explicit_sort_requires_presentation_ordering(self):
        plan = _m24_plan(filters=[], top_n=3, sort="desc")
        dax = (
            "EVALUATE TOPN(3, SUMMARIZECOLUMNS("
            "'Product'[Category], \"Total Sales\", [Total Sales]), "
            "[Total Sales], DESC)"
        )
        result = self._validate(dax, plan=plan)
        assert "dax_presentation_ordering_missing" in result.errors

    def test_ties_may_return_more_rows_than_top_n(self):
        from backend.app.schemas.data_contracts import QueryResult

        result = QueryResult(
            semantic_model_key="local_desktop_model",
            columns=["Category", "Total Sales"],
            rows=[["A", 10], ["B", 9], ["C", 8], ["D", 8]],
            row_count=4,
            source_mode="real",
        )
        assert ValidationService().validate_query_result(result).is_valid
