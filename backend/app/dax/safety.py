"""DAX 只读安全验证器 — M1.3

独立于 LLM 的结构化 DAX 安全分析。
不依赖字符串匹配 EVALUATE 就判定安全。
验证结果结构化：is_valid, errors, warnings, referenced_objects。
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
    referenced_objects: list[str] = Field(default_factory=list, description="DAX 中引用的表/列/度量值名称")

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
# 安全验证器
# ---------------------------------------------------------------------------


class DAXSafetyValidator:
    """DAX 只读安全验证器

    不依赖简单的 EVALUATE 存在检查。
    多层验证：DML/语言检测 → 结构分析 → Schema 验证 → 复杂度限制。
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
            schema: 可选的 Schema（用于验证引用的对象存在性）

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

        # ── 2. 非 DAX 语言检测（在 EVALUATE 检查之前） ──
        for kw in FORBIDDEN_LANGUAGES:
            if kw.upper() in dax_upper:
                errors.append(f"DAX 包含禁止的非 DAX 语言标记: {kw.strip()}")

        # ── 3. DAX 写操作函数 ──
        for kw in FORBIDDEN_DAX_FUNCTIONS:
            if kw in dax_upper:
                errors.append(f"DAX 包含禁止的写操作函数: {kw}")

        # ── 4. 注释绕过检测 ──
        if re.search(r'--', dax_stripped):
            # DAX 行注释 -- 可用于绕过安全检查
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

        # ── 8. Schema 对象验证 ──
        referenced_objects = self._extract_referenced_objects(dax_stripped)
        if schema is not None:
            schema_errors = self._validate_schema_objects(referenced_objects, schema)
            errors.extend(schema_errors)

        # ── 9. 写操作关键词（最后的防线） ──
        # 这些关键词在正常 DAX 中不应出现
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

    # ── 内部方法 ──

    def _extract_referenced_objects(self, dax: str) -> list[str]:
        """从 DAX 中提取引用的表、列、度量值名称（不提取值）"""
        objects: list[str] = []

        # 匹配 'TableName' 格式
        table_refs = re.findall(r"'([^']+)'", dax)
        objects.extend(table_refs)

        # 匹配 [ColumnName] 或 [MeasureName] 格式
        bracket_refs = re.findall(r"\[([^\]]+)\]", dax)
        objects.extend(bracket_refs)

        # 去重并排序
        seen = set()
        result = []
        for obj in objects:
            if obj not in seen:
                seen.add(obj)
                result.append(obj)

        return result

    def _validate_schema_objects(
        self,
        referenced: list[str],
        schema: SemanticModelSchema,
    ) -> list[str]:
        """验证引用的对象在 Schema 中存在"""
        errors: list[str] = []

        all_columns = set(schema.get_all_columns())
        all_measures = set(schema.get_all_measures())
        all_tables = {t.name for t in schema.tables}
        all_valid = all_columns | all_measures | all_tables

        for obj in referenced:
            # 跳过明显不是 Schema 对象的引用（如字符串字面量）
            if obj.startswith('"') or obj.startswith("'") or obj.startswith("@"):
                continue
            if obj in all_valid:
                continue
            # 检查是否是 DAX 关键字/函数（不报错）
            if obj.upper() in _DAX_KEYWORDS:
                continue
            errors.append(f"引用了 Schema 中不存在的对象: '{obj}'")

        return errors


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
    "X", "Y",  # VAR 中常用变量名
}
