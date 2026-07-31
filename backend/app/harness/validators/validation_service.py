"""ValidationService — 统一验证入口

Application 只依赖此服务，不散落独立验证逻辑。
"""

from typing import Any, Optional

from pydantic import BaseModel

from backend.app.intent.models import IntentSpec, IntentType
from backend.app.schemas.data_contracts import (
    DAXRequest,
    QueryPlan,
    QueryResult,
    ReportSpec,
    SemanticModelSchema,
    StructuredFilter,
    UserContext,
)
from backend.app.memory.models import MemoryCommitEvidence, StructuredWorkMemory


class ValidationResult(BaseModel):
    """结构化验证结果"""
    valid: bool
    errors: list[str] = []
    warnings: list[str] = []

    @property
    def is_valid(self) -> bool:
        return self.valid


class ValidationService:
    """统一验证服务

    至少实现：Intent、QueryPlan、DAX、QueryResult、Report、Memory 验证。
    所有验证返回结构化 ValidationResult。
    """

    def __init__(
        self,
        allowed_semantic_models: Optional[list[str]] = None,
        allowed_templates: Optional[list[str]] = None,
    ):
        self._allowed_models = allowed_semantic_models or ["mock_sales_model"]
        self._allowed_templates = allowed_templates or [
            "sales_weekly", "satisfaction", "operating_overview"
        ]
        self._allowed_chart_types = {"bar", "line", "pie", "scatter", "table"}

    # -----------------------------------------------------------------
    # Intent 验证
    # -----------------------------------------------------------------

    def validate_intent(self, intent: IntentSpec) -> ValidationResult:
        """验证 IntentSpec 合法性"""
        errors: list[str] = []

        # 合法 Intent 枚举
        if intent.intent not in IntentType:
            errors.append(f"Invalid intent: {intent.intent}")

        # 跨字段一致性由 IntentSpec 自身的 model_validator 保证
        # 此处做额外业务级检查
        if intent.intent == IntentType.UNSUPPORTED and not intent.unsupported_reason:
            errors.append("unsupported intent must have unsupported_reason")

        if intent.intent == IntentType.CLARIFICATION and not intent.clarification_question:
            errors.append("clarification intent must have clarification_question")

        return ValidationResult(valid=len(errors) == 0, errors=errors)

    # -----------------------------------------------------------------
    # QueryPlan 验证
    # -----------------------------------------------------------------

    def validate_query_plan(
        self, plan: QueryPlan, schema: SemanticModelSchema
    ) -> ValidationResult:
        """验证 QueryPlan"""
        errors: list[str] = []

        # semantic_model_key 已登记
        if plan.semantic_model_key not in self._allowed_models:
            errors.append(
                f"Model '{plan.semantic_model_key}' not in allowed list: {self._allowed_models}"
            )

        # 指标和维度来自 Schema
        all_columns = schema.get_all_columns()
        all_measures = schema.get_all_measures()
        for m in plan.measures:
            if m not in all_measures and m not in all_columns:
                errors.append(f"Measure/column '{m}' not found in schema")

        for d in plan.dimensions:
            if d not in all_columns:
                errors.append(f"Dimension '{d}' not found in schema columns")

        # filter 字段存在
        for f in plan.filters:
            if f.field not in all_columns and f.field not in all_measures:
                errors.append(f"Filter field '{f.field}' not found in schema")

        # top_n 有效
        if plan.top_n is not None and plan.top_n < 1:
            errors.append("top_n must be >= 1")

        # 不允许跨模型
        if plan.semantic_model_key not in self._allowed_models:
            errors.append(f"Model '{plan.semantic_model_key}' not allowed")

        return ValidationResult(valid=len(errors) == 0, errors=errors)

    # -----------------------------------------------------------------
    # DAX 验证
    # -----------------------------------------------------------------

    def validate_dax(self, dax_request: DAXRequest) -> ValidationResult:
        """验证 DAX 请求 — 基础静态规则"""
        errors: list[str] = []
        dax = dax_request.dax.strip().upper() if dax_request.dax else ""

        # 非空
        if not dax:
            errors.append("DAX is empty")
            return ValidationResult(valid=False, errors=errors)

        # 包含合法查询结构
        if "EVALUATE" not in dax:
            errors.append("DAX must contain EVALUATE")

        # 禁止 SQL
        forbidden_keywords = [
            "SELECT ", "INSERT ", "UPDATE ", "DELETE ", "DROP ",
            "CREATE ", "ALTER ", "EXEC ", "EXECUTE ",
        ]
        for kw in forbidden_keywords:
            if kw in dax:
                errors.append(f"DAX contains forbidden keyword: {kw}")

        # 行数和超时限制
        if dax_request.max_rows > 10000:
            errors.append("max_rows exceeds limit")

        if dax_request.timeout_seconds > 300:
            errors.append("timeout_seconds exceeds limit")

        return ValidationResult(valid=len(errors) == 0, errors=errors)

    # -----------------------------------------------------------------
    # QueryResult 验证
    # -----------------------------------------------------------------

    def validate_query_result(self, result: QueryResult) -> ValidationResult:
        """验证 QueryResult 结构一致性"""
        errors: list[str] = []

        if result.error is not None:
            # 有错误的结果本身不是验证失败，而是查询失败
            return ValidationResult(valid=True, warnings=[f"Query had error: {result.error.type}"])

        if result.row_count != len(result.rows):
            errors.append(
                f"row_count ({result.row_count}) != len(rows) ({len(result.rows)})"
            )

        col_count = len(result.columns)
        for i, row in enumerate(result.rows):
            if len(row) != col_count:
                errors.append(
                    f"Row {i} has {len(row)} values, expected {col_count}"
                )

        return ValidationResult(valid=len(errors) == 0, errors=errors)

    # -----------------------------------------------------------------
    # Report 验证
    # -----------------------------------------------------------------

    def validate_report(
        self, report: ReportSpec, schema: SemanticModelSchema
    ) -> ValidationResult:
        """验证 ReportSpec"""
        errors: list[str] = []

        # template_key 白名单
        if report.template_key not in self._allowed_templates:
            errors.append(
                f"Template '{report.template_key}' not in allowed: {self._allowed_templates}"
            )

        # chart_type 白名单
        for chart in report.charts:
            if chart.type not in self._allowed_chart_types:
                errors.append(f"Chart type '{chart.type}' not allowed: {self._allowed_chart_types}")

        # KPI field 存在
        all_fields = schema.get_all_columns() + schema.get_all_measures()
        for kpi in report.kpis:
            if kpi.field and kpi.field not in all_fields:
                errors.append(f"KPI field '{kpi.field}' not found in schema")

        # Chart field 存在
        for chart in report.charts:
            if chart.x_field and chart.x_field not in all_fields:
                errors.append(f"Chart x_field '{chart.x_field}' not found in schema")
            if chart.y_field and chart.y_field not in all_fields:
                errors.append(f"Chart y_field '{chart.y_field}' not found in schema")

        # Table field 存在
        for table in report.tables:
            for col in table.columns:
                if col not in all_fields:
                    errors.append(f"Table column '{col}' not found in schema")

        # 不包含 HTML 或 Script
        report_str = report.model_dump_json()
        if "<script" in report_str.lower() or "<html" in report_str.lower():
            errors.append("Report contains HTML or Script")

        return ValidationResult(valid=len(errors) == 0, errors=errors)

    # -----------------------------------------------------------------
    # Memory 验证
    # -----------------------------------------------------------------

    def validate_memory_commit(
        self,
        evidence: MemoryCommitEvidence,
        expected_version: int,
        current_version: int,
    ) -> ValidationResult:
        """验证 Memory 提交证据"""
        errors: list[str] = []

        if not evidence.all_satisfied:
            errors.append(f"Evidence not complete: {evidence.failure_reason or 'unknown'}")

        if expected_version != current_version:
            errors.append(
                f"Version conflict: expected {expected_version}, current {current_version}"
            )

        return ValidationResult(valid=len(errors) == 0, errors=errors)
