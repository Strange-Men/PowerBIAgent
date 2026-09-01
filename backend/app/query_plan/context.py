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
        if t.is_hidden or t.is_system_managed:
            continue
        columns = [
            {"name": c.name, "data_type": c.data_type,
             "description": c.description, "display_name": c.display_name}
            for c in t.columns
            if not c.is_hidden
        ]
        measures = [
            {"name": m.name, "description": m.description,
             "display_name": m.display_name, "format_string": m.format_string}
            for m in t.measures
            if not m.is_hidden
        ]
        hierarchies = [
            {"name": h.name, "levels": h.levels}
            for h in t.hierarchies
        ]
        tables.append({
            "name": t.name,
            "description": t.description,
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
    lines.append(f"语义模型名称：{schema_view['model_name']}")
    lines.append(
        "semantic_model_key（必须原样复制到 QueryPlan）："
        f"{schema_view['model_key']}"
    )
    lines.append("以下表、列和度量值名称必须按照 Schema 原样复制，包括空格和大小写。")
    lines.append("")

    for table in schema_view["tables"]:
        lines.append(f"表：{table['name']}")
        if table.get("description"):
            lines.append(f"  描述：{table['description']}")
        if table["columns"]:
            col_names = [c["name"] for c in table["columns"]]
            lines.append(f"  列：{', '.join(col_names)}")
        if table["measures"]:
            meas_names = [m["name"] for m in table["measures"]]
            lines.append(f"  度量值：{', '.join(meas_names)}")
        for obj in (*table["columns"], *table["measures"]):
            metadata = [str(obj[key]) for key in ("display_name", "description", "format_string") if obj.get(key)]
            if metadata:
                lines.append(f"  {obj['name']} metadata：{' | '.join(metadata)}")
        if table["hierarchies"]:
            for h in table["hierarchies"]:
                lines.append(f"  层次结构：{h['name']} ({' > '.join(h['levels'])})")
        lines.append("")

    return "\n".join(lines)
