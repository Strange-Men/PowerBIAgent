"""ValidationService — 统一验证入口

Application 只依赖此服务，不散落独立验证逻辑。
"""

from typing import Any, Optional

from pydantic import BaseModel

from backend.app.intent.models import IntentSpec, IntentType
from backend.app.schemas.data_contracts import (
    AnswerSpec,
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
    error_code: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        return self.valid


class ValidationService:
    """统一验证服务

    至少实现：Intent、QueryPlan、DAX、QueryResult、Report、Answer、Memory 验证。
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

        if intent.intent not in IntentType:
            errors.append(f"Invalid intent: {intent.intent}")

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

        if plan.semantic_model_key not in self._allowed_models:
            errors.append(
                f"Model '{plan.semantic_model_key}' not in allowed list: {self._allowed_models}"
            )

        all_columns = schema.get_all_columns()
        all_measures = schema.get_all_measures()
        for m in plan.measures:
            if m not in all_measures and m not in all_columns:
                errors.append(f"Measure/column '{m}' not found in schema")

        for d in plan.dimensions:
            if d not in all_columns:
                errors.append(f"Dimension '{d}' not found in schema columns")

        for f in plan.filters:
            if f.field not in all_columns and f.field not in all_measures:
                errors.append(f"Filter field '{f.field}' not found in schema")

        if plan.top_n is not None and plan.top_n < 1:
            errors.append("top_n must be >= 1")

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

        if not dax:
            errors.append("DAX is empty")
            return ValidationResult(valid=False, errors=errors, error_code="dax_empty")

        if "EVALUATE" not in dax:
            errors.append("DAX must contain EVALUATE")

        forbidden_keywords = [
            "SELECT ", "INSERT ", "UPDATE ", "DELETE ", "DROP ",
            "CREATE ", "ALTER ", "EXEC ", "EXECUTE ",
        ]
        for kw in forbidden_keywords:
            if kw in dax:
                errors.append(f"DAX contains forbidden keyword: {kw.strip()}")

        if dax_request.max_rows > 10000:
            errors.append("max_rows exceeds limit")
        if dax_request.timeout_seconds > 300:
            errors.append("timeout_seconds exceeds limit")

        return ValidationResult(
            valid=len(errors) == 0, errors=errors,
            error_code="dax_validation_failed" if errors else None
        )

    # -----------------------------------------------------------------
    # QueryResult 验证
    # -----------------------------------------------------------------

    def validate_query_result(self, result: QueryResult) -> ValidationResult:
        """验证 QueryResult 结构一致性

        QueryResult.error 存在时不可继续处理 — 返回 valid=False。
        """
        errors: list[str] = []
        warnings: list[str] = []

        if result.error is not None:
            errors.append(f"QueryResult has error: {result.error.type} - {result.error.message}")
            return ValidationResult(
                valid=False, errors=errors, warnings=warnings,
                error_code=f"query_error_{result.error.type}"
            )

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

        if not result.semantic_model_key:
            warnings.append("QueryResult has no semantic_model_key")

        return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)

    # -----------------------------------------------------------------
    # Answer 验证
    # -----------------------------------------------------------------

    def validate_answer(self, answer: AnswerSpec, result: QueryResult) -> ValidationResult:
        """验证 Answer — 绑定当前 QueryResult"""
        errors: list[str] = []

        if not answer.answer or not answer.answer.strip():
            errors.append("Answer is empty")

        if answer.semantic_model_key and answer.semantic_model_key != result.semantic_model_key:
            errors.append(
                f"Answer semantic_model_key '{answer.semantic_model_key}' "
                f"does not match QueryResult '{result.semantic_model_key}'"
            )

        # source_mode 一致
        if answer.source_mode != result.source_mode:
            warnings = [f"Answer source_mode '{answer.source_mode}' != QueryResult '{result.source_mode}'"]
        else:
            warnings = []

        # evidence 与 QueryResult 一致性
        if answer.evidence:
            if "source" in answer.evidence and answer.evidence["source"] != result.semantic_model_key:
                warnings.append("Answer evidence source does not match QueryResult")

        return ValidationResult(
            valid=len(errors) == 0, errors=errors, warnings=warnings,
            error_code="answer_validation_failed" if errors else None
        )

    # -----------------------------------------------------------------
    # Report 验证
    # -----------------------------------------------------------------

    def validate_report(
        self, report: ReportSpec, schema: SemanticModelSchema,
        query_result: Optional[QueryResult] = None
    ) -> ValidationResult:
        """验证 ReportSpec — 绑定当前 QueryResult 字段"""
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

        # data_source 与当前模型一致
        if report.data_source and report.data_source != schema.key:
            errors.append(f"Report data_source '{report.data_source}' != schema '{schema.key}'")

        # source_mode 检查
        if query_result is not None and report.source_mode != query_result.source_mode:
            errors.append(
                f"Report source_mode '{report.source_mode}' != QueryResult '{query_result.source_mode}'"
            )

        # KPI/Chart/Table 字段必须来自本次 QueryResult
        result_fields: set[str] = set()
        if query_result is not None:
            result_fields = set(query_result.columns)

        all_schema_fields = schema.get_all_columns() + schema.get_all_measures()

        for kpi in report.kpis:
            if kpi.field:
                # 字段必须在 schema 中存在
                if kpi.field not in all_schema_fields:
                    errors.append(f"KPI field '{kpi.field}' not found in schema")
                # 如果有 query_result，字段应与 columns 匹配
                if result_fields and kpi.field not in result_fields:
                    errors.append(f"KPI field '{kpi.field}' not found in QueryResult columns {list(result_fields)}")

        for chart in report.charts:
            if chart.x_field and chart.x_field not in all_schema_fields:
                errors.append(f"Chart x_field '{chart.x_field}' not found in schema")
            if chart.y_field and chart.y_field not in all_schema_fields:
                errors.append(f"Chart y_field '{chart.y_field}' not found in schema")
            if result_fields:
                if chart.x_field and chart.x_field not in result_fields:
                    errors.append(f"Chart x_field '{chart.x_field}' not in QueryResult columns")
                if chart.y_field and chart.y_field not in result_fields:
                    errors.append(f"Chart y_field '{chart.y_field}' not in QueryResult columns")

        for table in report.tables:
            for col in table.columns:
                if col not in all_schema_fields:
                    errors.append(f"Table column '{col}' not found in schema")
                if result_fields and col not in result_fields:
                    errors.append(f"Table column '{col}' not in QueryResult columns")
            # 每行长度检查
            for i, row in enumerate(table.rows):
                if len(row) != len(table.columns):
                    errors.append(
                        f"Table row {i} has {len(row)} values, expected {len(table.columns)}"
                    )

        # 不包含 HTML 或 Script
        report_str = report.model_dump_json()
        if "<script" in report_str.lower() or "<html" in report_str.lower():
            errors.append("Report contains HTML or Script")

        return ValidationResult(
            valid=len(errors) == 0, errors=errors,
            error_code="report_validation_failed" if errors else None
        )

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
