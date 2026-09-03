"""AnswerContext — M1.4-B 安全回答上下文

从 QueryPlan、QueryResult 和 Schema 中提取回答所需的字段白名单子集。
限制行数和单元格长度，禁止发送 DAX、完整 Schema、Memory、Trace 或 Secret。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# ── 截断阈值（集中常量管理） ──

MAX_ROWS_IN_CONTEXT = 20
MAX_CELL_LENGTH = 100


class AnswerContext(BaseModel):
    """回答生成的安全上下文快照

    只包含允许发送给 LLM 的字段白名单子集。
    禁止发送 DAX、完整 Schema、Memory、Trace 或 Secret。
    """

    user_input: str = Field(..., min_length=1, description="用户原始输入")
    result_id: str = Field(..., min_length=1, description="QueryResult.result_id")
    semantic_model_key: str = Field(..., min_length=1, description="语义模型 Key")
    columns: list[str] = Field(default_factory=list, description="查询结果列名")
    rows: list[list[Any]] = Field(default_factory=list, description="受限行数据")
    row_count: int = Field(default=0, description="实际行数（可能大于 rows 长度）")
    truncated: bool = Field(default=False, description="QueryResult 是否被截断")
    source_mode: str = Field(default="mock", description="数据来源：mock / real")
    input_truncated: bool = Field(
        default=False, description="上下文是否因超限而被截断"
    )

    # ── QueryPlan 安全摘要（不包含 DAX 或完整 Schema） ──
    measures: list[str] = Field(default_factory=list, description="查询指标")
    dimensions: list[str] = Field(default_factory=list, description="查询维度")
    filters_summary: str = Field(default="", description="筛选条件摘要")
    time_range: str = Field(default="", description="时间范围")
    query_shape: str = Field(default="", description="确定性查询形状")
    sort: str = Field(default="", description="Canonical 排序方向")
    top_n: int | None = Field(default=None, ge=1, description="Canonical TopN")
    effective_scope: str = Field(default="", description="确定性有效查询范围")

    model_config = {"extra": "forbid", "frozen": True}

    @classmethod
    def build(
        cls,
        user_input: str,
        *,
        result_id: str,
        semantic_model_key: str,
        columns: list[str],
        rows: list[list[Any]],
        row_count: int,
        truncated: bool,
        source_mode: str,
        measures: list[str] | None = None,
        dimensions: list[str] | None = None,
        filters_summary: str = "",
        time_range: str = "",
        query_shape: str = "",
        sort: str = "",
        top_n: int | None = None,
        effective_scope: str = "",
    ) -> "AnswerContext":
        """构建安全上下文快照

        自动执行行数截断和单元格文本长度截断。
        用户输入和数据单元格均视为不可信数据。
        """
        input_truncated = False

        # 行数截断
        safe_rows = rows
        if len(safe_rows) > MAX_ROWS_IN_CONTEXT:
            safe_rows = safe_rows[:MAX_ROWS_IN_CONTEXT]
            input_truncated = True

        # 单元格截断（每行每列）
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
            columns=list(columns),
            rows=truncated_rows,
            row_count=row_count,
            truncated=truncated,
            source_mode=source_mode,
            input_truncated=input_truncated,
            measures=list(measures or []),
            dimensions=list(dimensions or []),
            filters_summary=filters_summary,
            time_range=time_range or "",
            query_shape=query_shape,
            sort=sort,
            top_n=top_n,
            effective_scope=effective_scope,
        )
