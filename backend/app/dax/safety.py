"""DAX 只读安全验证器 — M1.3.1

独立于 LLM 的结构化 DAX 安全分析。
- 表—列/度量值归属关系严格验证（不依赖全局名称集合）
- 带表限定引用与未限定引用分离处理
- 字符串别名与临时名称不被误判为 Schema 对象
- 验证结果结构化：is_valid、errors、warnings、referenced_objects
"""

from __future__ import annotations

import re
from typing import Any, Optional

from pydantic import BaseModel, Field

from backend.app.schemas.data_contracts import SemanticModelSchema

# ---------------------------------------------------------------------------
# 安全验证结果
# ---------------------------------------------------------------------------


class DAXSafetyResult(BaseModel):
    """DAX 只读安全验证结构"""
    is_valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    referenced_objects: list[str] = Field(
        default_factory=list,
        description="DAX 中引用的表/列/度量值名称（含限定信息）"
    )

    model_config = {"extra": "forbid"}


# ---------------------------------------------------------------------------
# 禁止的关键词/模式
# ---------------------------------------------------------------------------

# 写入/修改操作 — DAX 中不应出现
FORBIDDEN_DML_KEYWORDS = [
    "INSERT ", "UPDATE ", "DELETE ", "DROP ", "CREATE ",
    "ALTER ", "TRUNCATE", "REFRESH", "MERGE ", "GRANT ",
    "REVOKE ", "RENAME ", "DETACH", "ATTACH", "BACKUP",
    "RESTORE", "PROCESS", "SET ", "EVALUATE ",
]

# 非 DAX 语言标记
FORBIDDEN_LANGUAGES = [
    "SELECT ", "FROM ", "WHERE ", "JOIN ", "GROUP BY ",  # SQL
    "#!/bin/sh", "#!/bin/bash", "cmd.exe", "powershell",  # Shell
    "import os", "import sys", "exec(", "eval(",  # Python
    "function(", "require(", "process.exit",  # JavaScript
    "System.", "Runtime.", "System.Diagnostics",  # .NET
    "subprocess", "__import__", "compile(",  # Python 进阶
]

# DAX 写操作函数
FORBIDDEN_DAX_FUNCTIONS = [
    "REFRESH", "PROCESSADD", "PROCESSCLEAR", "PROCESSCLEARINDEX",
    "PROCESSDATA", "PROCESSDEFRAG", "PROCESSFULL",
    "PROCESSINDEXES", "PROCESSRECALC", "PROCESSUPDATE",
]

# 安全限制
MAX_DAX_LENGTH = 4096
MAX_EVALUATE_COUNT = 1
MAX_PAREN_DEPTH = 50


# ---------------------------------------------------------------------------
# DAX 关键字白名单（不应检查的关键字）
# ---------------------------------------------------------------------------

_DAX_KEYWORDS: set[str] = {
    "EVALUATE", "DEFINE", "MEASURE", "VAR", "RETURN",
    "SUMMARIZE", "SUMMARIZECOLUMNS", "FILTER", "TOPN",
    "ORDER", "BY", "ASC", "DESC",
    "ADDCOLUMNS", "SELECTCOLUMNS", "CALCULATETABLE", "CALCULATE",
    "GROUPBY", "CROSSJOIN", "NATURALINNERJOIN", "NATURALLEFTOUTERJOIN",
    "UNION", "EXCEPT", "INTERSECT", "GENERATE", "GENERATEALL",
    "ROW", "DATATABLE", "ALL", "ALLCROSSFILTERED", "ALLEXCEPT",
    "ALLNOBLANKROW", "ALLSELECTED", "VALUES", "DISTINCT",
    "SUM", "SUMX", "AVERAGE", "AVERAGEX", "COUNT", "COUNTA",
    "COUNTROWS", "COUNTX", "COUNTAX", "MIN", "MINX", "MAX", "MAXX",
    "DISTINCTCOUNT", "DISTINCTCOUNTNOBLANK", "DIVIDE",
    "TOTALYTD", "TOTALQTD", "TOTALMTD",
    "SAMEPERIODLASTYEAR", "DATEADD", "DATESYTD", "DATESQTD",
    "DATESMTD", "PREVIOUSMONTH", "PREVIOUSQUARTER", "PREVIOUSYEAR",
    "DATESBETWEEN", "DATESINPERIOD", "ENDOFMONTH", "ENDOFQUARTER",
    "ENDOFYEAR", "STARTOFMONTH", "STARTOFQUARTER", "STARTOFYEAR",
    "FORMAT", "IF", "IFERROR", "SWITCH", "TRUE", "FALSE",
    "BLANK", "AND", "OR", "NOT", "IN", "CONTAINS", "CONTAINSROW",
    "CONTAINSSTRING", "SEARCH", "FIND", "LEFT", "RIGHT", "MID",
    "LEN", "TRIM", "UPPER", "LOWER", "SUBSTITUTE", "REPLACE",
    "ISBLANK", "ISERROR", "ISNUMBER", "ISTEXT", "ISNONTEXT",
    "ISLOGICAL", "ISFILTERED", "ISCROSSFILTERED", "ISINSCOPE",
    "ISEMPTY", "INT", "ROUND", "ROUNDUP", "ROUNDDOWN", "ABS",
    "SQRT", "POWER", "MOD", "RELATED", "RELATEDTABLE",
    "LOOKUPVALUE", "USERELATIONSHIP", "CROSSFILTER",
    "KEEPFILTERS", "REMOVEFILTERS", "HASONEFILTER", "HASONEVALUE",
    "SELECTEDVALUE", "RANKX", "RANK", "PATH", "PATHITEM",
    "PATHLENGTH", "PATHCONTAINS", "FIRSTDATE", "LASTDATE",
    "FIRSTNONBLANK", "LASTNONBLANK", "NEXTDAY", "PREVIOUSDAY",
    "X", "Y",
}


# ---------------------------------------------------------------------------
# Schema 表—对象归属索引
# ---------------------------------------------------------------------------

class _SchemaIndex:
    """从 SemanticModelSchema 构建的表—对象归属索引

    维护：
    - 每个表拥有的列集合和度量值集合
    - 每个度量值名对应的表集合（用于歧义检测）
    - 每个列名对应的表集合
    """

    def __init__(self, schema: SemanticModelSchema):
        self._table_columns: dict[str, set[str]] = {}
        self._table_measures: dict[str, set[str]] = {}
        self._measure_tables: dict[str, set[str]] = {}
        self._column_tables: dict[str, set[str]] = {}
        self._all_table_names: set[str] = set()

        for t in schema.tables:
            self._all_table_names.add(t.name)
            cols = {c.name for c in t.columns if not c.is_hidden}
            meas = {m.name for m in t.measures}
            self._table_columns[t.name] = cols
            self._table_measures[t.name] = meas
            for cn in cols:
                self._column_tables.setdefault(cn, set()).add(t.name)
            for mn in meas:
                self._measure_tables.setdefault(mn, set()).add(t.name)

    @property
    def table_names(self) -> set[str]:
        return self._all_table_names

    def table_exists(self, name: str) -> bool:
        return name in self._all_table_names

    def get_columns(self, table: str) -> set[str]:
        return self._table_columns.get(table, set())

    def get_measures(self, table: str) -> set[str]:
        return self._table_measures.get(table, set())

    def get_column_tables(self, col: str) -> set[str]:
        return self._column_tables.get(col, set())

    def get_measure_tables(self, meas: str) -> set[str]:
        return self._measure_tables.get(meas, set())

    def is_column(self, name: str) -> bool:
        return name in self._column_tables

    def is_measure(self, name: str) -> bool:
        return name in self._measure_tables

    def object_belongs_to_table(self, table: str, obj: str) -> bool:
        """检查对象是否属于指定表（列或度量值）"""
        return obj in self._table_columns.get(table, set()) or \
               obj in self._table_measures.get(table, set())


# ---------------------------------------------------------------------------
# 安全验证器
# ---------------------------------------------------------------------------


class DAXSafetyValidator:
    """DAX 只读安全验证器

    多层验证：DML/语言检测 → 结构分析 → 表—对象归属验证 → 复杂度限制。
    """

    def __init__(self, max_dax_length: int = MAX_DAX_LENGTH):
        self._max_dax_length = max_dax_length

    def validate(
        self,
        dax: str,
        schema: Optional[SemanticModelSchema] = None,
    ) -> DAXSafetyResult:
        """验证 DAX 查询的只读安全性

        Args:
            dax: DAX 查询字符串
            schema: 可选的 Schema（用于表—对象归属验证）

        Returns:
            DAXSafetyResult: 结构化验证结果
        """
        errors: list[str] = []
        warnings: list[str] = []

        if not dax or not dax.strip():
            return DAXSafetyResult(
                is_valid=False,
                errors=["DAX 为空"],
            )

        dax_stripped = dax.strip()
        dax_upper = dax_stripped.upper()

        # ── 1. 长度限制 ──
        if len(dax_stripped) > self._max_dax_length:
            errors.append(f"DAX 长度 {len(dax_stripped)} 超过限制 {self._max_dax_length}")

        # ── 2. 非 DAX 语言检测 ──
        for kw in FORBIDDEN_LANGUAGES:
            if kw.upper() in dax_upper:
                errors.append(f"DAX 包含禁止的非 DAX 语言标记: {kw.strip()}")

        # ── 3. DAX 写操作函数 ──
        for kw in FORBIDDEN_DAX_FUNCTIONS:
            if kw in dax_upper:
                errors.append(f"DAX 包含禁止的写操作函数: {kw}")

        # ── 4. 注释绕过检测 ──
        if re.search(r'--', dax_stripped):
            errors.append("DAX 包含行注释 (--)，禁止注释绕过")
        if re.search(r'/\*|\*/', dax_stripped):
            errors.append("DAX 包含块注释 (/* */)，禁止注释绕过")
        if re.search(r'//', dax_stripped):
            errors.append("DAX 包含 JavaScript 风格注释 (//)")

        # ── 5. 多语句注入检测 ──
        if ';' in dax_stripped:
            errors.append("DAX 包含分号，可能存在多语句注入")

        # ── 6. EVALUATE 检查 ──
        eval_count = dax_upper.count("EVALUATE")
        if eval_count == 0:
            errors.append("DAX 必须以 EVALUATE 开头")
        elif eval_count > MAX_EVALUATE_COUNT:
            errors.append(f"DAX 包含 {eval_count} 个 EVALUATE（最多允许 {MAX_EVALUATE_COUNT} 个）")
        elif not dax_upper.lstrip().startswith("EVALUATE") and not dax_upper.lstrip().startswith("DEFINE"):
            errors.append("DAX 必须以 EVALUATE 或 DEFINE 开头")

        # ── 7. 括号深度检查 ──
        depth = 0
        max_depth = 0
        for ch in dax_stripped:
            if ch == '(':
                depth += 1
                max_depth = max(max_depth, depth)
            elif ch == ')':
                depth -= 1
                if depth < 0:
                    errors.append("DAX 括号不匹配")
                    break
        if depth != 0:
            errors.append("DAX 括号不匹配")
        if max_depth > MAX_PAREN_DEPTH:
            errors.append(f"DAX 括号嵌套深度 {max_depth} 超过限制 {MAX_PAREN_DEPTH}")

        # ── 8. Schema 对象验证（表—归属关系） ──
        referenced_objects: list[str] = []
        if schema is not None:
            schema_index = _SchemaIndex(schema)
            refs, schema_errors = self._validate_table_object_ownership(
                dax_stripped, schema_index,
            )
            referenced_objects = refs
            errors.extend(schema_errors)
        else:
            # 无 Schema 时仍提取引用对象
            referenced_objects = self._extract_referenced_objects_legacy(dax_stripped)

        # ── 9. 写操作关键词（最后防线） ──
        for kw in ["INSERT ", "UPDATE ", "DELETE ", "DROP ", "CREATE ", "ALTER ",
                    "EXEC ", "EXECUTE ", "TRUNCATE", "REFRESH"]:
            if kw in dax_upper:
                if kw not in [e.split(":")[0] for e in errors]:
                    errors.append(f"DAX 包含禁止的写操作关键词: {kw.strip()}")

        return DAXSafetyResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            referenced_objects=referenced_objects,
        )

    # ── 引用提取 ──

    def _extract_referenced_objects_legacy(self, dax: str) -> list[str]:
        """旧版引用提取（无 Schema 时使用）"""
        objects: list[str] = []
        table_refs = re.findall(r"'([^']+)'", dax)
        objects.extend(table_refs)
        bracket_refs = re.findall(r"\[([^\]]+)\]", dax)
        objects.extend(bracket_refs)
        seen = set()
        result = []
        for obj in objects:
            if obj not in seen:
                seen.add(obj)
                result.append(obj)
        return result

    def _validate_table_object_ownership(
        self, dax: str, idx: _SchemaIndex,
    ) -> tuple[list[str], list[str]]:
        """验证 DAX 中所有引用的表—对象归属关系

        Returns:
            (referenced_objects, errors)
        """
        errors: list[str] = []
        refs: list[str] = []

        # ── 步骤 0：剥离双引号字符串字面量（避免别名被当作对象） ──
        # 用空格替换，保持字符位置（虽然我们不依赖位置）
        dax_no_strings = re.sub(r'"[^"]*"', ' ', dax)

        # ── 步骤 1：提取 'Table'[Object] 形式的完整限定引用 ──
        quoted_qualified_pattern = r"'([^']+)'\[([^\]]+)\]"
        consumed_positions: list[tuple[int, int]] = []
        qualified_refs: list[tuple[str, str, str]] = []  # (table, object, raw)

        for m in re.finditer(quoted_qualified_pattern, dax_no_strings):
            table = m.group(1)
            obj = m.group(2)
            raw = m.group(0)
            consumed_positions.append((m.start(), m.end()))
            qualified_refs.append((table, obj, raw))
            refs.append(f"'{table}'[{obj}]")

        # ── 步骤 2：在未消耗区域中提取 Table[Object] 形式 ──
        # 构建未消耗区域
        unquoted_qualified_pattern = r'\b([A-Za-z_]\w*)\[([^\]]+)\]'

        for m in re.finditer(unquoted_qualified_pattern, dax_no_strings):
            # 检查是否在已消耗区域
            if any(start <= m.start() < end for start, end in consumed_positions):
                continue
            table = m.group(1)
            obj = m.group(2)
            raw = m.group(0)
            # 跳过 DAX 关键字
            if table.upper() in _DAX_KEYWORDS:
                continue
            consumed_positions.append((m.start(), m.end()))
            qualified_refs.append((table, obj, raw))
            refs.append(f"{table}[{obj}]")

        # ── 步骤 3：在未消耗区域中提取 [Object] 未限定引用 ──
        unqualified_refs: list[str] = []
        for m in re.finditer(r'\[([^\]]+)\]', dax_no_strings):
            if any(start <= m.start() < end for start, end in consumed_positions):
                continue
            obj = m.group(1)
            # 跳过 DAX 关键字和纯数字
            if obj.upper() in _DAX_KEYWORDS:
                continue
            if obj.isdigit():
                continue
            consumed_positions.append((m.start(), m.end()))
            unqualified_refs.append(obj)
            refs.append(f"[{obj}]")

        # ── 步骤 4：在未消耗区域中提取 'Table' 引用 ──
        standalone_tables: list[str] = []
        for m in re.finditer(r"'([^']+)'", dax_no_strings):
            if any(start <= m.start() < end for start, end in consumed_positions):
                continue
            table = m.group(1)
            consumed_positions.append((m.start(), m.end()))
            refs.append(f"'{table}'")
            standalone_tables.append(table)

        # ── 验证 ──

        # 4a. 验证独立表引用（FILTER('Sales', ...) / COUNTROWS('Sales') / ALL('Sales') / VALUES('Sales') 等）
        for table in standalone_tables:
            if table.upper() in _DAX_KEYWORDS:
                continue
            if not idx.table_exists(table):
                errors.append(f"unknown_table: 表 '{table}' 不存在于 Schema 中")

        # 4c. 验证带表限定的引用
        for table, obj, raw in qualified_refs:
            if table.upper() in _DAX_KEYWORDS:
                continue
            if not idx.table_exists(table):
                errors.append(f"unknown_table: 表 '{table}' 不存在于 Schema 中")
                continue
            if not idx.object_belongs_to_table(table, obj):
                # 提供具体信息：该对象实际属于哪个表
                col_tables = idx.get_column_tables(obj)
                meas_tables = idx.get_measure_tables(obj)
                actual = col_tables | meas_tables
                if actual:
                    actual_str = ", ".join(sorted(actual))
                    errors.append(
                        f"object_not_in_table: '{obj}' 不属于表 '{table}'"
                        f"（实际属于: {actual_str}）"
                    )
                else:
                    errors.append(
                        f"object_not_in_table: '{obj}' 不属于表 '{table}'"
                        f"（且在任何表中均不存在）"
                    )

        # 4d. 验证未限定引用 [Object]
        for obj in unqualified_refs:
            is_m = idx.is_measure(obj)
            is_c = idx.is_column(obj)

            if is_m and not is_c:
                # 作为度量值：检查唯一性
                tables = idx.get_measure_tables(obj)
                if len(tables) > 1:
                    errors.append(
                        f"ambiguous_measure: [{obj}] 在多个表中存在同名度量值"
                        f"（表: {', '.join(sorted(tables))}），必须带表限定"
                    )
                # 唯一度量值 → 合法
            elif is_c and not is_m:
                # 列必须带表限定
                errors.append(
                    f"unqualified_column_reference: [{obj}] 是列而非度量值，"
                    f"列引用必须带表名"
                )
            elif is_m and is_c:
                # 同名为列和度量值，作为度量值引用（唯一性仍需检查）
                tables = idx.get_measure_tables(obj)
                if len(tables) > 1:
                    errors.append(
                        f"ambiguous_measure: [{obj}] 在多个表中存在同名度量值"
                        f"（表: {', '.join(sorted(tables))}），必须带表限定"
                    )
            else:
                # 不存在
                errors.append(f"unknown_measure: [{obj}] 不是 Schema 中的度量值或列")

        return refs, errors
