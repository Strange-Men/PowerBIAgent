"""QueryPlan 上下文 — Schema 安全精简视图

从 SemanticModelSchema 提取允许发送给 LLM 的字段子集。
不包含完整表达式、隐藏列、关系等内部细节。
"""

from __future__ import annotations

from typing import Any

from backend.app.schemas.data_contracts import SemanticModelSchema


def build_schema_view(schema: SemanticModelSchema) -> dict[str, Any]:
    """构建 Schema 的安全精简视图

    只包含 LLM 生成 QueryPlan 所需的信息：
    - 表名、列名（不含隐藏列）、度量值名称、层次结构

    不包含：
    - DAX 表达式
    - 关系
    - 内部 Key
    - 列数据类型（可选的，但保留用于区分度量值和列）
    """
    tables: list[dict[str, Any]] = []
    for t in schema.tables:
        columns = [
            {"name": c.name, "data_type": c.data_type}
            for c in t.columns
            if not c.is_hidden
        ]
        measures = [
            {"name": m.name}
            for m in t.measures
        ]
        hierarchies = [
            {"name": h.name, "levels": h.levels}
            for h in t.hierarchies
        ]
        tables.append({
            "name": t.name,
            "columns": columns,
            "measures": measures,
            "hierarchies": hierarchies,
        })

    return {
        "model_name": schema.name,
        "model_key": schema.key,
        "tables": tables,
    }


def render_schema_text(schema_view: dict[str, Any]) -> str:
    """将 Schema 视图渲染为纯文本（供 Prompt 使用）"""
    lines: list[str] = []
    lines.append(f"语义模型：{schema_view['model_name']} ({schema_view['model_key']})")
    lines.append("")

    for table in schema_view["tables"]:
        lines.append(f"表：{table['name']}")
        if table["columns"]:
            col_names = [c["name"] for c in table["columns"]]
            lines.append(f"  列：{', '.join(col_names)}")
        if table["measures"]:
            meas_names = [m["name"] for m in table["measures"]]
            lines.append(f"  度量值：{', '.join(meas_names)}")
        if table["hierarchies"]:
            for h in table["hierarchies"]:
                lines.append(f"  层次结构：{h['name']} ({' > '.join(h['levels'])})")
        lines.append("")

    return "\n".join(lines)
