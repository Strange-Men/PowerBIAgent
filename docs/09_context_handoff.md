# 09 — 当前上下文交接

> **当前状态入口。** 从根目录 `AGENTS.md` 开始；本文件只回答"现在是什么、下一步做什么"。历史变更见 `CHANGELOG.md` 与 Git。
> **最后更新：** 2026-08-20

## 当前阶段

**M4.2 series FINAL PASS。**

M4.2.3 — 持久化资源身份与元数据权威最终收口已完成。

### M4.2 series FINAL PASS

M4.2.1 已正式完成（commit `80eea6a313b65`）。
M4.2.2 已正式完成（commit `8a2ae441de70`；路径 containment + row/payload coherence）。
M4.2.3 已完成 required metadata、immutable identity 与 Mock/Real report namespace 最终收口。

| 子版本 | 内容 | 状态 |
|--------|------|------|
| M4.2 | 会话与报表元数据恢复 | ✅ 完成 |
| M4.2.1 | 报表元数据权威边界与会话关联收口 | ✅ 完成 |
| M4.2.2 | 路径与元数据一致性最终加固 | ✅ 完成 |
| **M4.2.3** | **持久化资源身份与元数据权威最终收口** | **✅ 本轮 FINAL PASS** |

### M4.2.3 变更内容

#### A — metadata authority / missing fields

- `payload_json` 是 modern metadata reconstruction authority，DB dedicated columns 是 immutable integrity witness；缺少 payload 本身即 fail closed。
- `report_id`、`template_key`、`semantic_model_key`、`schema_fingerprint`、`source_mode`、`content_hash`、`relative_path` 必须在 payload 显式存在，并与 DB columns 严格一致。
- `conversation_id` / `request_id` nullable；DB 有值时 payload 不得缺失或冲突。
- 不再用 `""`、`"mock"`、`None`、created_at fallback 或 derived relative path 继续恢复；统一进入 `ReportStorageError`。

#### B — ReportArtifact immutable identity

- `report_id` 是 immutable resource identity。
- SQLite / InMemory 都只允许完整 metadata 相同的幂等 no-op。
- 任一 metadata、linkage 或 provenance 改变均返回 `report_artifact_identity_collision`，禁止 overwrite。

#### C — M4.3 report namespace contract

- `source_mode` 仅允许 `mock | real`。
- future conversation → reports 查询必须使用 `(source_mode, conversation_id)`，不得只按 conversation_id 查询；Mock/Real 不能互相进入 history。
- 现有 `report_artifacts.source_mode` + `conversation_id` 足够表达该 invariant，不新增 schema/migration；未实现 M4.3 API、search、delete、FTS5。

### 架构影响

- `backend/app/report/resources.py`：metadata required fields 与 `source_mode` domain validation。
- `backend/app/persistence/repositories/report_artifact.py`：strict reconstruction contract + immutable save；SQLite/InMemory 同义。
- `backend/tests/unit/persistence/test_report_artifact_invariants.py`：30 个真实 corruption、identity、namespace tests。
- `backend/app/config/settings.py`：version → M4.2.3。
- 不新增 Alembic migration；fresh DB upgrade head 必须继续通过。
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

*最后更新：2026-08-20 | M4.2.3 — 持久化资源身份与元数据权威最终收口*
