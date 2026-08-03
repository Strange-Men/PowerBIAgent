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
        """验证 Answer — 绑定当前 QueryResult（向后兼容，供 Mock 管线使用）"""
        errors: list[str] = []
        warnings: list[str] = []

        if not answer.answer or not answer.answer.strip():
            errors.append("Answer is empty")

        if answer.semantic_model_key and answer.semantic_model_key != result.semantic_model_key:
            errors.append(
                f"Answer semantic_model_key '{answer.semantic_model_key}' "
                f"does not match QueryResult '{result.semantic_model_key}'"
            )

        if answer.source_mode != result.source_mode:
            errors.append(
                f"Answer source_mode '{answer.source_mode}' "
                f"does not match QueryResult source_mode '{result.source_mode}'"
            )

        # evidence.source 与 QueryResult 一致性（旧格式兼容）
        if answer.evidence:
            if "source" in answer.evidence and answer.evidence["source"] != result.semantic_model_key:
                errors.append(
                    f"Answer evidence source '{answer.evidence['source']}' "
                    f"does not match QueryResult semantic_model_key '{result.semantic_model_key}'"
                )

        return ValidationResult(
            valid=len(errors) == 0, errors=errors, warnings=warnings,
            error_code="answer_validation_failed" if errors else None
        )

    def validate_answer_strict(
        self, answer: AnswerSpec, result: QueryResult,
        *, input_truncated: bool = False,
    ) -> ValidationResult:
        """验证 Answer — M1.4-B 严格模式（DeepSeekAnswerService 使用）

        P0 验证：
        - answer 非空
        - semantic_model_key 一致
        - source_mode 一致
        - evidence 强制绑定（result_id/semantic_model_key/row_count/source_mode）
        - metrics 可追溯（MVP 最小规则）
        - 空结果不得虚构 metrics
        - truncated 强制披露（warning → error）
        - 不包含 HTML/Script/事件属性
        """
        errors: list[str] = []
        warnings: list[str] = []

        # 1. answer 非空
        if not answer.answer or not answer.answer.strip():
            errors.append("answer_empty: answer 字段为空")

        # 2. semantic_model_key 一致
        if answer.semantic_model_key and answer.semantic_model_key != result.semantic_model_key:
            errors.append(
                f"answer_model_key_mismatch: Answer semantic_model_key "
                f"'{answer.semantic_model_key}' != QueryResult '{result.semantic_model_key}'"
            )

        # 3. source_mode 一致
        if answer.source_mode != result.source_mode:
            errors.append(
                f"answer_source_mode_mismatch: Answer source_mode "
                f"'{answer.source_mode}' != QueryResult '{result.source_mode}'"
            )

        # 4. evidence 强制绑定验证
        evidence_errors = self._validate_answer_evidence_strict(answer, result)
        errors.extend(evidence_errors)

        # 5. metrics 可追溯
        metrics_errors = self._validate_answer_metrics_strict(answer, result)
        errors.extend(metrics_errors)

        # 6. 空结果规则
        if result.row_count == 0 or not result.rows:
            if answer.metrics and len(answer.metrics) > 0:
                errors.append(
                    "answer_empty_has_metrics: 空结果不得虚构 metrics"
                )
            if "无数据" not in answer.answer and "暂无" not in answer.answer:
                warnings.append(
                    "answer_empty_no_disclosure: 空结果建议明确说明无数据"
                )

        # 7. truncated 强制披露（error，非 warning）
        truncated = result.truncated or input_truncated
        if truncated:
            if not self._detect_truncation_disclosure(answer.answer):
                errors.append(
                    "answer_truncated_not_disclosed: truncated=true 或 "
                    "input_truncated=true 但 answer 未披露结果可能不完整"
                )

        # 8. HTML/Script/事件属性检测
        dangerous = ["<script", "<html", "onclick=", "onload=", "onerror=",
                     "javascript:", "<iframe", "<img ", "<a href"]
        answer_lower = answer.answer.lower()
        for d in dangerous:
            if d in answer_lower:
                errors.append(f"answer_contains_dangerous_content: '{d}'")
                break

        return ValidationResult(
            valid=len(errors) == 0, errors=errors, warnings=warnings,
            error_code="answer_validation_failed" if errors else None
        )

    @staticmethod
    def _detect_truncation_disclosure(answer_text: str) -> bool:
        """检测 answer 是否披露了数据截断/不完整

        使用关键词规则，不依赖单一固定句子。
        """
        import re
        patterns = [
            r"截断",           # 结果被截断
            r"不完整",          # 结果不完整
            r"部分数据",        # 仅基于部分数据
            r"部分结果",        # 部分结果
            r"仅供参考",        # 结果仅供参考
            r"不代表全",        # 不代表全部数据
            r"可能不完整",      # 可能不完整
            r"显示前\d",        # 显示前N条
            r"共\d+条.*仅",     # 共X条，仅显示前Y条
        ]
        for pat in patterns:
            if re.search(pat, answer_text):
                return True
        return False

    # ── Evidence 严格验证 ──

    @staticmethod
    def _validate_answer_evidence_strict(answer: AnswerSpec, result: QueryResult) -> list[str]:
        """验证 evidence 与 QueryResult 的一致性（强制绑定模式）

        evidence 必须包含并正确绑定四个核心字段：
        - result_id
        - semantic_model_key
        - row_count
        - source_mode

        旧格式 evidence.source 兼容读取，但不能代替核心字段。
        """
        errors: list[str] = []
        ev = answer.evidence or {}

        # evidence 不能为空
        if not ev:
            errors.append("answer_evidence_empty: evidence 不能为空")
            return errors

        # result_id — 强制存在且匹配
        if not ev.get("result_id"):
            errors.append("answer_evidence_missing_result_id: evidence 缺少 result_id")
        elif ev["result_id"] != result.result_id:
            errors.append(
                f"answer_evidence_result_id_mismatch: evidence.result_id "
                f"'{ev['result_id']}' != QueryResult '{result.result_id}'"
            )

        # semantic_model_key — 强制存在且匹配
        if not ev.get("semantic_model_key"):
            errors.append(
                "answer_evidence_missing_semantic_model_key: "
                "evidence 缺少 semantic_model_key"
            )
        elif ev["semantic_model_key"] != result.semantic_model_key:
            errors.append(
                f"answer_evidence_model_key_mismatch: evidence.semantic_model_key "
                f"'{ev['semantic_model_key']}' != QueryResult '{result.semantic_model_key}'"
            )

        # row_count — 强制存在且匹配
        if "row_count" not in ev:
            errors.append("answer_evidence_missing_row_count: evidence 缺少 row_count")
        elif not isinstance(ev["row_count"], int) or ev["row_count"] != result.row_count:
            errors.append(
                f"answer_evidence_row_count_mismatch: evidence.row_count "
                f"{ev.get('row_count')} != QueryResult {result.row_count}"
            )

        # source_mode — 强制存在且匹配
        if not ev.get("source_mode"):
            errors.append(
                "answer_evidence_missing_source_mode: evidence 缺少 source_mode"
            )
        elif ev["source_mode"] != result.source_mode:
            errors.append(
                f"answer_evidence_source_mode_mismatch: evidence.source_mode "
                f"'{ev['source_mode']}' != QueryResult '{result.source_mode}'"
            )

        return errors

    # ── Metrics 可追溯验证（MVP 最小规则） ──

    @staticmethod
    def _validate_answer_metrics_strict(answer: AnswerSpec, result: QueryResult) -> list[str]:
        """验证 metrics 可追溯到 QueryResult（严格模式）

        MVP 最小规则：
        1. 直接来源于 QueryResult（列名匹配）；或
        2. 能由确定性后台计算复现（简单聚合：sum/count/avg）
        3. evidence 中记录了来源字段或计算规则
        4. 无法证明来源的指标拒绝
        """
        errors: list[str] = []
        if not answer.metrics:
            return errors

        # 从 QueryResult 提取所有可用数值
        result_values: dict[str, list[float]] = {}
        col_indices: dict[str, int] = {}
        for i, col in enumerate(result.columns):
            col_indices[col] = i
            col_values: list[float] = []
            for row in result.rows:
                if i < len(row):
                    try:
                        col_values.append(float(row[i]))
                    except (ValueError, TypeError):
                        pass
            if col_values:
                result_values[col] = col_values

        for metric_name, metric_value in answer.metrics.items():
            if not isinstance(metric_value, (int, float)):
                errors.append(
                    f"answer_metric_non_numeric: metrics['{metric_name}'] "
                    f"不是数值类型"
                )
                continue

            # 规则 1：直接来源于 QueryResult 列
            if metric_name in result_values:
                vals = result_values[metric_name]
                if abs(metric_value - sum(vals)) < 0.01:
                    continue  # sum 匹配
                if len(vals) > 0 and abs(metric_value - (sum(vals) / len(vals))) < 0.01:
                    continue  # avg 匹配
                if abs(metric_value - len(vals)) < 0.01:
                    continue  # count 匹配

            # 规则 2：检查 evidence 是否记录了来源字段或计算规则
            ev = answer.evidence or {}
            source_field = ev.get("source_field") or ev.get("calculation_note") or ev.get("derived_from")
            if source_field:
                continue  # evidence 中注明了来源

            # 规则 3：检查所有 QueryResult 列的聚合值
            found = False
            for col_name, vals in result_values.items():
                if abs(metric_value - sum(vals)) < 0.01:
                    found = True
                    break
                if len(vals) > 0 and abs(metric_value - (sum(vals) / len(vals))) < 0.01:
                    found = True
                    break
                if abs(metric_value - len(vals)) < 0.01:
                    found = True
                    break
            if found:
                continue

            # 无法追溯
            errors.append(
                f"answer_metric_untraceable: metrics['{metric_name}']={metric_value} "
                f"无法追溯到 QueryResult 列 {list(result_values.keys())}"
            )

        return errors

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
    # ReportSpec 严格验证 — M1.4-C
    # -----------------------------------------------------------------

    def validate_report_strict(
        self, report: ReportSpec, query_result: QueryResult,
        *, input_truncated: bool = False,
    ) -> ValidationResult:
        """验证 ReportSpec — 严格模式（DeepSeekReportSpecService 使用）"""
        errors: list[str] = []
        warnings: list[str] = []

        # 1. 基础绑定
        if not report.title or not report.title.strip():
            errors.append("report_title_empty: title 为空")
        if report.template_key not in self._allowed_templates:
            errors.append(
                f"report_template_not_allowed: template_key '{report.template_key}' "
                f"不在白名单 {self._allowed_templates}"
            )
        if report.data_source and report.data_source != query_result.semantic_model_key:
            errors.append(
                f"report_data_source_mismatch: data_source '{report.data_source}' "
                f"!= QueryResult '{query_result.semantic_model_key}'"
            )
        if report.source_mode != query_result.source_mode:
            errors.append(
                f"report_source_mode_mismatch: source_mode "
                f"'{report.source_mode}' != '{query_result.source_mode}'"
            )

        result_columns_set = set(query_result.columns)
        result_columns_list = list(query_result.columns)
        result_rows = query_result.rows
        is_empty = query_result.row_count == 0 or not result_rows

        # 2. KPI 验证
        kpi_errors = self._validate_kpis_strict(report.kpis, result_columns_set, result_rows, is_empty)
        errors.extend(kpi_errors)

        # 3. Chart 验证
        chart_errors = self._validate_charts_strict(report.charts, result_columns_set, is_empty)
        errors.extend(chart_errors)

        # 4. Table 验证（整行投影）
        table_errors = self._validate_tables_strict(report.tables, result_columns_list, result_rows, is_empty)
        errors.extend(table_errors)

        # 5. 截断披露
        truncated = query_result.truncated or input_truncated
        if truncated:
            disclosed = any(
                self._detect_truncation_disclosure(s)
                for s in report.insights
            )
            if not disclosed:
                errors.append(
                    "report_truncated_not_disclosed: truncated=true 但 insights 未披露"
                )

        # 6. HTML/Script/URL 检测
        report_str = report.model_dump_json()
        dangerous = ["<script", "<html", "onclick=", "javascript:", "http://", "https://"]
        for d in dangerous:
            if d in report_str.lower():
                errors.append(f"report_dangerous_content: '{d}'")
                break

        return ValidationResult(
            valid=len(errors) == 0, errors=errors, warnings=warnings,
            error_code="report_validation_failed" if errors else None
        )

    @staticmethod
    def _validate_kpis_strict(
        kpis: list, result_columns: set[str], result_rows: list[list], is_empty: bool,
    ) -> list[str]:
        errors: list[str] = []
        if not kpis:
            return errors
        if is_empty:
            errors.append("report_empty_has_kpis: 空结果不得返回 KPI")
            return errors

        # 提取可用数值索引
        col_values: dict[str, list[float]] = {}
        for row in result_rows:
            for j, col_name in enumerate(result_columns):
                if j < len(row):
                    try:
                        v = float(row[j])
                    except (ValueError, TypeError):
                        continue
                    col_values.setdefault(col_name, []).append(v)

        for kpi in kpis:
            field = getattr(kpi, "field", "")
            name = getattr(kpi, "name", "?")
            value = getattr(kpi, "value", None)

            if not field:
                errors.append(f"report_kpi_field_empty: KPI '{name}' field 为空")
                continue
            if field not in result_columns:
                errors.append(
                    f"report_kpi_field_not_found: KPI '{name}' field "
                    f"'{field}' 不在 QueryResult.columns 中"
                )
                continue

            # 值真实性验证
            if value is None:
                continue
            if not isinstance(value, (int, float)):
                errors.append(
                    f"report_kpi_value_non_numeric: KPI '{name}' value 不是数值"
                )
                continue

            vals = col_values.get(field, [])
            if not vals:
                errors.append(
                    f"report_kpi_value_unverifiable: KPI '{name}' field "
                    f"'{field}' 在 QueryResult 中无数值数据"
                )
                continue

            # 直接匹配或聚合匹配
            matched = False
            if any(abs(value - v) < 0.01 for v in vals):
                matched = True
            elif abs(value - sum(vals)) < 0.01:
                matched = True
            elif len(vals) > 0 and abs(value - (sum(vals) / len(vals))) < 0.01:
                matched = True
            elif abs(value - len(vals)) < 0.01:
                matched = True

            if not matched:
                errors.append(
                    f"report_kpi_value_unverifiable: KPI '{name}' value={value} "
                    f"无法由 field '{field}' 的数据复现"
                )

        return errors

    @staticmethod
    def _validate_charts_strict(
        charts: list, result_columns: set[str], is_empty: bool,
    ) -> list[str]:
        errors: list[str] = []
        if not charts:
            return errors
        if is_empty:
            errors.append("report_empty_has_charts: 空结果不得返回图表")
            return errors

        allowed_types = {"bar", "line", "pie", "scatter"}
        for chart in charts:
            ctype = getattr(chart, "type", "")
            if ctype not in allowed_types:
                errors.append(
                    f"report_chart_type_invalid: type '{ctype}' 不在允许列表 {allowed_types}"
                )
            for fname, flabel in [("x_field", "x_field"), ("y_field", "y_field")]:
                fval = getattr(chart, flabel, "")
                if not fval:
                    errors.append(f"report_chart_{fname}_empty: Chart '{getattr(chart, 'title', '?')}' {fname} 为空")
                elif fval not in result_columns:
                    errors.append(
                        f"report_chart_{fname}_not_found: Chart '{getattr(chart, 'title', '?')}' "
                        f"{fname} '{fval}' 不在 QueryResult.columns 中"
                    )

        return errors

    @staticmethod
    def _validate_tables_strict(
        tables: list, result_columns: list[str], result_rows: list[list], is_empty: bool,
    ) -> list[str]:
        """整行投影验证 TableSpec

        规则：
        1. TableSpec.columns 必须是 QueryResult.columns 的子集
        2. 根据 columns 确定在 QueryResult.columns 中的索引
        3. 将每条 QueryResult 原始行按这些索引投影
        4. TableSpec 每一行必须与某条完整投影行一致
        5. 禁止跨行拼接（不同原始行的单元格不能组合成新行）
        6. 支持列顺序调整
        7. 重复行不超过来源数量
        8. 类型严格比较（1 ≠ "1"，null ≠ "None"）
        """
        errors: list[str] = []
        if not tables:
            return errors
        if is_empty:
            errors.append("report_empty_has_tables: 空结果不得返回表格")
            return errors

        # 构建列名→索引映射
        col_index: dict[str, int] = {c: i for i, c in enumerate(result_columns)}

        for table in tables:
            # 1. columns 必须是 QueryResult.columns 的子集
            for col in table.columns:
                if col not in col_index:
                    errors.append(
                        f"report_table_column_not_found: Table '{table.title}' "
                        f"column '{col}' 不在 QueryResult.columns 中"
                    )
            if any(col not in col_index for col in table.columns):
                continue  # 列名错误时跳过行验证

            # 2. 确定投影索引
            proj_indices = [col_index[c] for c in table.columns]

            # 3. 将 QueryResult 原始行投影为元组
            def _project(row: list) -> tuple:
                return tuple(_safe_repr(row[i]) if i < len(row) else _NULL_SENTINEL for i in proj_indices)

            source_rows: list[tuple] = [_project(r) for r in result_rows]

            # 4. 验证 TableSpec 中每一行
            source_counts: dict[tuple, int] = {}
            for t in source_rows:
                source_counts[t] = source_counts.get(t, 0) + 1

            consumed: dict[tuple, int] = {}
            for i, row in enumerate(table.rows):
                if len(row) != len(table.columns):
                    errors.append(
                        f"report_table_row_length_mismatch: Table '{table.title}' "
                        f"row {i} 长度 {len(row)} != columns {len(table.columns)}"
                    )
                    continue

                target = tuple(_safe_repr(cell) for cell in row)
                if target not in source_counts:
                    errors.append(
                        f"report_table_row_not_from_result: Table '{table.title}' "
                        f"row {i} 不在 QueryResult 投影行中（可能跨行拼接或虚构）"
                    )
                else:
                    consumed[target] = consumed.get(target, 0) + 1
                    if consumed[target] > source_counts[target]:
                        errors.append(
                            f"report_table_row_duplicate_exceeded: Table '{table.title}' "
                            f"row {i} 重复次数超过 QueryResult 来源数量"
                        )

        return errors

    @staticmethod
    def _detect_truncation_disclosure(text: str) -> bool:
        import re
        patterns = [
            r"截断", r"不完整", r"部分数据", r"部分结果",
            r"仅供参考", r"不代表全", r"可能不完整",
            r"显示前\d", r"共\d+条.*仅",
        ]
        for pat in patterns:
            if re.search(pat, text):
                return True
        return False

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


# ── 模块级辅助（Table 行投影验证） ──

_NULL_SENTINEL = object()


def _safe_repr(value: object) -> object:
    """类型安全的规范化表示：保留 int/float/bool/None 类型。

    规则：
    - None → _NULL_SENTINEL（避免与字符串 "None" 混淆）
    - int/float/bool → 保持原类型（避免与字符串 "1"/"True" 混淆）
    - 其他 → str(value)
    """
    if value is None:
        return _NULL_SENTINEL
    if isinstance(value, (int, float, bool)):
        return value
    return str(value)
