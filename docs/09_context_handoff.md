# 09 — 当前上下文交接

> **当前状态入口。** 从根目录 `AGENTS.md` 开始；本文件只回答"现在是什么、下一步做什么"。历史变更见 `CHANGELOG.md` 与 Git。
> **最后更新：** 2026-08-19

## 当前阶段

**M4.2 series FINAL PASS。**

M4.2.2 — 路径与元数据一致性最终加固已完成。

### M4.2 series FINAL PASS

M4.2.1 已正式完成（commit `80eea6a313b65`）。
M4.2.2 已正式完成（路径 containment 修复 + 元数据 coherence 验证 + 文档一致性完成）。

| 子版本 | 内容 | 状态 |
|--------|------|------|
| M4.2 | 会话与报表元数据恢复 | ✅ 完成 |
| M4.2.1 | 报表元数据权威边界与会话关联收口 | ✅ 完成 |
| **M4.2.2** | **路径与元数据一致性最终加固** | **✅ 本轮完成** |

### M4.2.2 变更内容

#### A — 路径 containment 加固（FIX 1）

- `_validate_path()` 替换 `str(target).startswith(str(root))` 为严格 `parent` 比较
- 新增规则：relative_path 必须是单层 filename（拒绝 nested directory）
- 新增规则：sibling-prefix escape 检测（`/x/reports_evil/` vs `/x/reports/`）
- 新增规则：symlink escape 检测（platform 允许时）
- `_target()` 已正确使用 `parent` 比较，不做修改
- 参考 Python 官方 [pathlib.Path.resolve](https://docs.python.org/3/library/pathlib.html#pathlib.Path.resolve) 文档确认跨平台行为

#### B — 元数据 coherence 验证（FIX 2）

- 新增 `_validate_coherence()`：reconstruct 前验证 DB column 与 payload_json 一致性
- 验证字段：report_id, template_key, semantic_model_key, schema_fingerprint, source_mode, content_hash, relative_path, conversation_id, request_id
- DB column 与 payload 同时有值时必须严格一致
- 任一关键字段冲突 → `ReportStorageError`，fail closed
- 新增 `_coerce_bool_nullable()` 辅助处理空字符串与 None 对比

### 架构影响

- `backend/app/report/resources.py`：`_validate_path()` 严格 Path containment、单层 filename、symlink 检测
- `backend/app/persistence/repositories/report_artifact.py`：新增 `_validate_coherence()` / `_coerce_bool_nullable()`，`_model_to_artifact()` 恢复前执行一致性验证
- `backend/app/persistence/models.py`：修正 comment 为当前真实 contract
- `backend/app/config/settings.py`：version → M4.2.2
- 不新增 Alembic migration（入侵式测试可修改 DB 验证 fail-closed，不依赖 schema change）
- 不新增 tag

## M4.3 下一步

后续轮次：

1. **M4.3**: 最近对话 API / 聊天搜索 API / 删除会话 API（NOT STARTED）
2. **M4.4**: Restart/crash acceptance（E2E 验证重启后状态恢复）
3. **M5**: React + Vite 前端

## 关键命令

```powershell
# Full test suite
D:\Conda\envs\PBIAgent\python.exe -m pytest backend\tests -q --asyncio-mode=auto

# Persistence-focused
D:\Conda\envs\PBIAgent\python.exe -m pytest backend\tests\unit\persistence -v --asyncio-mode=auto

# Golden
D:\Conda\envs\PBIAgent\python.exe -m backend.app.harness.cases

# Alembic smoke（从空 DB）
D:\Conda\envs\PBIAgent\python.exe -m alembic upgrade head

# Gates
D:\Conda\envs\PBIAgent\python.exe scripts\check_architecture_gate.py
D:\Conda\envs\PBIAgent\python.exe scripts\check_repository_safety.py
D:\Conda\envs\PBIAgent\python.exe scripts\check_ai_error_ledger.py
D:\Conda\envs\PBIAgent\python.exe scripts\check_documentation_governance.py
```

---

*最后更新：2026-08-19 | M4.2.2 — 路径与元数据一致性最终加固*