# 09 — 当前上下文交接

> **当前状态入口。** 从根目录 `AGENTS.md` 开始；本文件只回答"现在是什么、下一步做什么"。历史变更见 `CHANGELOG.md` 与 Git。
> **最后更新：** 2026-08-20

## 当前阶段

**M4.4.1 — Memory Corruption Fail-Closed、README 重构与文档状态同步已完成。**

M4 backend 在 M4.4 已 FINAL PASS。M4.4.1 只做 committed Memory corruption corrective hardening、README Landing Page 重构与正式状态同步；不改变 M0—M4 架构或 factual truth chain，不进入 M5。

| 子版本 | 内容 | 状态 |
|--------|------|------|
| M4.2 series | 会话/报表恢复与 metadata authority 最终收口 | ✅ FINAL PASS |
| M4.3 | Conversation History / Search API | ✅ 完成 |
| **M4.4** | **Restart / Crash Acceptance & M4 Final Closure** | **✅ M4 FINAL PASS** |
| **M4.4.1** | **Memory corruption fail-closed + README/document closure** | **✅ FINAL PASS** |

### M4.4.1 corruption boundary

- 根因：`StructuredWorkMemory.filters` 接受任意 `dict`，SQLite `model_validate()` 无法识别 semantic corruption；`StateTransitionService._previous_filters()` 又捕获 canonical parse failure 后 `continue`，导致损坏 filter 被解释为空并可能扩大下一轮查询范围。
- 修复：保持 `list[dict]` storage/legacy shape，但 domain validation 逐项调用 `StructuredFilter.model_validate()`；持久化损坏在 fresh repository load 时以 `committed_memory_filter_invalid:<index>` fail closed。StateTransition 对绕过初始 validation 的进程内损坏抛出 `CommittedMemoryCorruptionError`，禁止 skip/clear/default-empty。
- TurnPipeline 的 committed/pending load、context build 与 controller setup 现在复用 Owner abort-on-exception 语义；同一 request_id 在 corruption 后可重复得到确定性失败，不遗留永远等待的 process-local claim。
- 合法 committed filter 继续跨轮继承；已有 legacy time string contract 保持不变。无 persistence schema change、无 Alembic migration。
- 新真实临时 SQLite restart regression 使用 dispose + fresh engine/repository/service，参数化覆盖 Mock/Real。同 namespace 在 LLM、schema、DAX、Power BI 与下一 memory commit 前失败，version 保持 1；另一 namespace 的合法 filter 正常恢复。
- README 现固定为 value-first Landing Page；`AGENTS.md` 新增 README Maintenance Contract。正式 PRD 只同步实现状态，07/08/09 与 CHANGELOG 同步为 M4.4.1。

### M4.4 restart / crash authority

- terminal `result_snapshots` 是 request replay authority；durable Snapshot 已保存但 process-local tracker 尚未 complete 时，fresh runtime 直接 replay，不重复工具执行。
- process-local in-flight claim 不持久化；crash 后若无 Snapshot，不产生 fake completed。若同 request 已有 Memory 但缺 terminal Snapshot，表示结果/外部副作用无法安全确认，TurnPipeline 以 `IdempotencyCoordinationError` fail closed，不自动重执行，也不生成 terminal duplicate。
- committed Memory 按 `(runtime_mode, conversation_id)` 恢复并保持 version；Pending/Failed 不冒充 Committed。Mock/Real 同 conversation ID 持续隔离。
- SQLite/History/Snapshot 仍不是 business/result/report factual authority；M0—M3 truth chain 未改。

### Report recovery

- `report_artifacts` SQLite row/payload 继续只提供 strict metadata；HTML filesystem 是唯一内容 authority。
- 新 persistent `ReportResultSnapshot` 的 `html` 兼容字段为空；restart replay 通过 `ReportRepository.read_html()` 读取文件，并核对 report identity、template/contract/reference/content hash、conversation/request linkage 与 source mode。
- Adaptive Real report 路径现将实际带 `conversation_id/request_id` 的 `ReportSpec` 传给 ToolGateway；此前构造 context copy 后误传原对象的生产 bug 已由严格 replay 验收发现并修复。
- missing/tampered HTML、corrupt metadata 或 snapshot/artifact mismatch 均 fail closed。配置了 report repository 时，旧 snapshot 内可能存在的 HTML 也不参与重放 authority。

### History / Archive / Delete restart

- recent/history/search/reports 在 dispose + fresh engine/service 后与重启前一致；archive 状态保留，recent/search 默认隐藏，direct history/reports 继续遵守 M4.3 contract。
- Migration `c8d4e6f2a109` 新增 `conversation_delete_intents`：DB 删除 transaction 同时持久化 exact `(runtime_mode, conversation_id)` 的 report IDs/counts；HTML cleanup 成功后 service 才清除 intent。
- DB commit 后 unlink/finalize 失败或进程退出时，fresh service 的相同 delete 可从 intent 重试；pending intent 阻止 Memory/Snapshot/Report 在该 namespace 复活。成功 delete 后再 restart，DB state、intent 与关联 HTML 均已清理；另一 namespace 不受影响。
- 这是应用级 durable intent + idempotent cleanup，不声称 SQLite transaction 可原子覆盖 filesystem，也不声称硬件/文件系统违反自身 durability contract 时仍可恢复。
- Report create 仍是 atomic HTML write → metadata save，并在可观察的 metadata-save failure 上 best-effort unlink；M4.4 没有为进程恰在 HTML rename 后、metadata commit 前退出的窗口增加 durable create journal，因此不承诺自动回收该无引用文件。该窗口不会形成成功 metadata 或 terminal Snapshot，也不会被当作可恢复报表。

### Fresh acceptance

- 新增 7 个 restart/crash integration tests；每个 restart 路径都使用真实临时 DB/files、dispose、全新 engine/session/repository/service。
- 新增 1 个 M4.3 → M4.4 migration test；fresh DB → head 与 `f4c3a2b1907d` → head 均通过。
- Backend fresh regression：`1681 passed, 1 skipped`。
- Golden `11 passed, 1 manual-real skipped`；Architecture `109`、Repository Safety `239`、Error Ledger `25`、Documentation Governance PASS。
- `backend/app/config/settings.py`：version → M4.4。
- M4 FINAL PASS；不新增 Tag。

### M4.4.1 fresh acceptance

- Targeted corruption regression：5 passed（StateTransition 3；真实 SQLite restart 2）。
- 邻近 Memory/StateTransition/persistence/restart：190 passed；backend full regression：1686 passed、1 skipped。
- Golden：11 passed、1 manual-real skipped；Architecture `109`、Repository Safety `239`、Error Ledger `25`、Documentation Governance PASS。
- Alembic head 保持 `c8d4e6f2a109`；fresh DB → head 与 head → head 幂等 upgrade PASS，确认无新增 migration。
- `backend/app/config/settings.py`：version → M4.4.1。
- M4.4.1 无 migration；M5 NOT STARTED；不新增 Tag。

## 下一步

后续轮次只有用户另行批准后才可开始：

1. **M5**: React + Vite 前端（NOT STARTED）

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

*最后更新：2026-08-20 | M4.4.1 — Memory Corruption Fail-Closed、README 重构与文档状态同步*
