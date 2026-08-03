"""ReportSpecContext — M1.4-C 安全报表规格上下文

从 QueryPlan、QueryResult、Schema 和模板信息中提取报表生成所需的字段白名单子集。
限制行数和单元格长度，禁止发送 DAX、完整 Schema、Memory、Trace 或 Secret。

截断阈值与 AnswerContext 保持一致。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# ── 截断阈值（与 AnswerContext 对齐） ──

MAX_ROWS_IN_CONTEXT = 20
MAX_CELL_LENGTH = 100


class ReportSpecContext(BaseModel):
    """报表规格生成的安全上下文快照"""

    user_input: str = Field(..., min_length=1, description="用户原始输入")
    result_id: str = Field(..., min_length=1, description="QueryResult.result_id")
    semantic_model_key: str = Field(..., min_length=1, description="语义模型 Key")
    template_key: str = Field(..., min_length=1, description="报表模板 Key")
    allowed_templates: list[str] = Field(default_factory=list, description="允许的模板白名单")
    columns: list[str] = Field(default_factory=list, description="查询结果列名")
    rows: list[list[Any]] = Field(default_factory=list, description="受限行数据")
    row_count: int = Field(default=0, description="实际行数")
    truncated: bool = Field(default=False, description="QueryResult 是否被截断")
    source_mode: str = Field(default="mock", description="数据来源")
    input_truncated: bool = Field(default=False, description="上下文是否被截断")

    # QueryPlan 安全摘要
    measures: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    filters_summary: str = Field(default="")
    time_range: str = Field(default="")

    model_config = {"extra": "forbid", "frozen": True}

    @classmethod
    def build(
        cls,
        user_input: str,
        *,
        result_id: str,
        semantic_model_key: str,
        template_key: str,
        allowed_templates: list[str] | None = None,
        columns: list[str] | None = None,
        rows: list[list[Any]] | None = None,
        row_count: int = 0,
        truncated: bool = False,
        source_mode: str = "mock",
        measures: list[str] | None = None,
        dimensions: list[str] | None = None,
        filters_summary: str = "",
        time_range: str = "",
    ) -> "ReportSpecContext":
        """构建安全上下文快照"""
        input_truncated = False
        cols = list(columns or [])
        safe_rows = list(rows or [])

        if len(safe_rows) > MAX_ROWS_IN_CONTEXT:
            safe_rows = safe_rows[:MAX_ROWS_IN_CONTEXT]
            input_truncated = True

        truncated_rows: list[list[Any]] = []
        for row in safe_rows:
            safe_row: list[Any] = []
            for cell in row:
                if isinstance(cell, str) and len(cell) > MAX_CELL_LENGTH:
                    safe_row.append(cell[:MAX_CELL_LENGTH] + "...")
                    input_truncated = True
                else:
                    safe_row.append(cell)
            truncated_rows.append(safe_row)

        return cls(
            user_input=user_input,
            result_id=result_id,
            semantic_model_key=semantic_model_key,
            template_key=template_key,
            allowed_templates=list(allowed_templates or []),
            columns=cols,
            rows=truncated_rows,
            row_count=row_count,
            truncated=truncated,
            source_mode=source_mode,
            input_truncated=input_truncated,
            measures=list(measures or []),
            dimensions=list(dimensions or []),
            filters_summary=filters_summary,
            time_range=time_range or "",
        )
