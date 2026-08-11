"""核心数据契约 — Pydantic 模型

包含：QueryPlan、DAXRequest、QueryResult、AnswerSpec、ReportSpec、
UserContext、SemanticModelSchema、PowerBIError 等。
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator


# =============================================================================
# 筛选
# =============================================================================

class FilterOperator(str, Enum):
    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    IN_SET = "in"
    NOT_IN = "not_in"
    CONTAINS = "contains"


class StructuredFilter(BaseModel):
    """结构化筛选条件 — 不依赖任意 dict"""
    field: str = Field(..., min_length=1)
    operator: FilterOperator = Field(default=FilterOperator.EQ)
    value: Any = Field(...)  # 允许数字、布尔、日期字符串和文本


# =============================================================================
# Semantic Model Schema
# =============================================================================

class ColumnSchema(BaseModel):
    name: str
    data_type: str
    is_hidden: bool = False
    description: Optional[str] = None


class MeasureSchema(BaseModel):
    name: str
    expression: str = ""
    data_type: str = "decimal"
    is_hidden: bool = False
    description: Optional[str] = None


class HierarchySchema(BaseModel):
    name: str
    levels: list[str] = Field(default_factory=list)


class TableSchema(BaseModel):
    name: str
    columns: list[ColumnSchema] = Field(default_factory=list)
    measures: list[MeasureSchema] = Field(default_factory=list)
    hierarchies: list[HierarchySchema] = Field(default_factory=list)
    is_hidden: bool = False
    is_system_managed: bool = False
    description: Optional[str] = None


class RelationshipSchema(BaseModel):
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    is_active: bool = True
    from_cardinality: Optional[str] = None
    to_cardinality: Optional[str] = None


class SemanticModelSchema(BaseModel):
    """Power BI 语义模型结构"""
    name: str
    key: str
    tables: list[TableSchema] = Field(default_factory=list)
    relationships: list[RelationshipSchema] = Field(default_factory=list)

    def get_all_columns(self) -> list[str]:
        """获取所有列名"""
        names: list[str] = []
        for t in self.tables:
            for c in t.columns:
                if not c.is_hidden:
                    names.append(c.name)
        return names

    def get_all_measures(self) -> list[str]:
        """获取所有度量值名称"""
        names: list[str] = []
        for t in self.tables:
            for m in t.measures:
                names.append(m.name)
        return names


# =============================================================================
# QueryPlan
# =============================================================================

class QueryPlan(BaseModel):
    """查询计划 — 从意图到结构化查询的描述"""
    normalized_question: str = Field(..., min_length=1)
    semantic_model_key: str = Field(..., min_length=1)
    measures: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    filters: list[StructuredFilter] = Field(default_factory=list)
    time_range: Optional[str] = None
    sort: Optional[str] = None
    top_n: Optional[int] = Field(default=None, ge=1)
    comparison_mode: Optional[str] = None
    requested_template: Optional[str] = None
    inherited_context: Optional[str] = None
    is_mock: bool = False


# =============================================================================
# DAXRequest
# =============================================================================

class DAXRequest(BaseModel):
    """DAX 查询请求"""
    semantic_model_key: str = Field(..., min_length=1)
    dax: str = Field(..., min_length=1)
    max_rows: int = Field(default=1000, ge=1)
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    request_id: str = ""
    is_mock: bool = False


# =============================================================================
# QueryResult
# =============================================================================

class PowerBIError(BaseModel):
    """标准化 Power BI 错误"""
    type: str = "unknown"  # timeout, permission_denied, dax_error, connection_error, oversized
    message: str = ""
    retryable: bool = False


class QueryResult(BaseModel):
    """标准化 DAX 查询结果"""
    result_id: str = Field(default_factory=lambda: str(__import__("uuid").uuid4()))
    semantic_model_key: str
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    row_count: int = 0
    execution_time_ms: Optional[int] = None
    source_mode: str = "mock"  # mock | real
    request_id: Optional[str] = None
    error: Optional[PowerBIError] = None
    truncated: bool = False

    @model_validator(mode="after")
    def validate_consistency(self) -> "QueryResult":
        """校验 row_count 与 rows 一致，每行字段与 columns 匹配"""
        if self.error is not None:
            return self

        # row_count 一致性
        actual_count = len(self.rows)
        if self.row_count != actual_count:
            raise ValueError(
                f"row_count ({self.row_count}) does not match actual rows length ({actual_count})"
            )

        # 每行字段与 columns 匹配
        col_count = len(self.columns)
        for i, row in enumerate(self.rows):
            if len(row) != col_count:
                raise ValueError(
                    f"Row {i} has {len(row)} values but {col_count} columns expected"
                )

        return self


# =============================================================================
# AnswerSpec
# =============================================================================

class AnswerSpec(BaseModel):
    """数据问答回答规格"""
    answer: str = Field(..., min_length=1)
    summary: str = ""
    metrics: dict[str, Any] = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)
    filters: list[StructuredFilter] = Field(default_factory=list)
    semantic_model_key: str = ""
    source_mode: str = "mock"
    generated_at: Optional[datetime] = None


# =============================================================================
# ReportSpec
# =============================================================================

class KPISpec(BaseModel):
    """KPI 规格"""
    name: str = Field(..., min_length=1)
    value: Any = None
    format: str = "number"  # number, currency, percentage, rating
    field: str = ""


class ChartSpec(BaseModel):
    """图表规格"""
    type: str = Field(..., min_length=1)  # bar, line, pie, scatter
    title: str = ""
    x_field: str = ""
    y_field: str = ""


class TableSpec(BaseModel):
    """表格规格"""
    title: str = ""
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)


class ReportSpec(BaseModel):
    """报表规格 — 禁止任意 HTML/JS/外部脚本"""
    title: str = Field(..., min_length=1)
    template_key: str = Field(..., min_length=1)
    summary: str = ""
    kpis: list[KPISpec] = Field(default_factory=list)
    charts: list[ChartSpec] = Field(default_factory=list)
    tables: list[TableSpec] = Field(default_factory=list)
    insights: list[str] = Field(default_factory=list)
    data_source: str = ""
    filters: list[StructuredFilter] = Field(default_factory=list)
    generated_at: Optional[datetime] = None
    source_mode: str = "mock"


# =============================================================================
# RenderedReport
# =============================================================================

class RenderedReport(BaseModel):
    """结构化渲染结果"""
    report_id: str = Field(default_factory=lambda: str(__import__("uuid").uuid4()))
    template_key: str = ""
    html: str = ""
    source_mode: str = "mock"
    generated_at: datetime = Field(default_factory=datetime.utcnow)


# =============================================================================
# UserContext
# =============================================================================

class UserContext(BaseModel):
    """用户上下文 — MVP 内部测试用户"""
    user_id: str = "test_user"
    roles: list[str] = Field(default_factory=lambda: ["viewer"])
    allowed_semantic_models: list[str] = Field(default_factory=lambda: ["mock_sales_model"])
    allowed_templates: list[str] = Field(
        default_factory=lambda: ["sales_weekly", "satisfaction", "operating_overview"]
    )
    allowed_tools: list[str] = Field(
        default_factory=lambda: ["get_semantic_model_schema", "execute_dax", "render_report"]
    )
