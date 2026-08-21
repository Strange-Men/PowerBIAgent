# 09 — 当前上下文交接

> **当前状态入口。** 从根目录 `AGENTS.md` 开始；本文件只回答"现在是什么、下一步做什么"。历史变更见 `CHANGELOG.md` 与 Git。
> **最后更新：** 2026-08-21

## 当前阶段

**M5.1 — React 前端实现与核心联调（已完成）。** M0–M4 后端保持封板与 FINAL PASS；M5.1 已创建前端并接入现有 Chat/Conversation/Report 契约。M5.2 NOT STARTED。

| 子版本 | 内容 | 状态 |
|--------|------|------|
| M4.2 series | 会话/报表恢复与 metadata authority 最终收口 | ✅ FINAL PASS |
| M4.3 | Conversation History / Search API | ✅ 完成 |
| **M4.4** | **Restart / Crash Acceptance & M4 Final Closure** | **✅ M4 FINAL PASS** |
| **M4.4.1** | **Memory corruption fail-closed + README/document closure** | **✅ FINAL PASS** |
| **M4.4.2** | **M0–M4 truth / persistence boundary final closure** | **✅ FINAL PASS** |
| **M5.0** | **前端设计与契约固化** | **✅ 已完成** |
| **M5.1** | **React 前端实现与核心联调** | **✅ 已完成** |

### M5.1 — React 前端实现与核心联调

- `frontend/` 已创建 React 19 + Vite 8 + TypeScript 6 工程，使用 hooks、普通 CSS、lucide-react、Vitest 与 Testing Library；无重型 Dashboard 框架、路由器或全局状态库。
- 已实现 AppShell、真实折叠 Sidebar、新聊天欢迎态、已有对话态、稳定底部 Composer、"+"数据模型/报表模板菜单与 DeepSeek-only 单选卡片。
- Chat adapter 发送 `conversation_id` / `request_id` / `semantic_model_key` / `report_template_key`，动态渲染 answer、clarification、unsupported、error、empty 与真实 ReportArtifact；不展示 trace/tool/audit/Memory/DAX/usage。
- recent/search/history/reports 已接现有 SQLite API。Conversation 请求显式 `runtime_mode`，report 请求显式 `source_mode`；History 只恢复 persisted structured result，并在 UI 明示不是逐字 transcript。
- 项目卡片与用户账户保持纯展示。没有新增 semantic model/template discovery endpoint；实际 key 只在 `src/config.ts` 集中配置，并在菜单注明本地配置。
- 报表查看/下载只使用与 `report_id` 严格一致的后端 canonical reference；无 report resource 时不显示附件。
- 最小契约缺口：Chat/History 不暴露 QueryResult `columns/rows`、独立 metrics 或 ChartSpec，`execution_audit` 也没有可消费 rows。M5.1 不修改 M4 Snapshot/Persistence，不从 answer/audit 推导事实，因此不渲染假表格/图表。
- Fresh gates：frontend typecheck/lint/build PASS，Vitest `13 passed`；Chrome 1600×1000 实际欢迎态检查 PASS；backend `1700 passed, 1 skipped`；Golden `11 passed, 1 manual-real skipped`；Architecture/Repository Safety/Error Ledger PASS。

### M5.0 — 前端设计与契约固化

- M5.0 已完成以下文档固化：
  - `frontend/README.md` — 从 M1.3.2 状态升级为 M5.0 文档，新增动态回答原则、左侧栏能力边界、"+"菜单映射原则、模型选择器 DeepSeek 唯一交互、后端能力到 UI 映射表、M5 路线三段、项目/账户仅展示
  - `docs/01_product_scope_and_frontend_skeleton.md` — 全面重构为 M5.0 骨架规范，AI 回答动态渲染原则代替固定内容序列，Composer 结构、模型选择器交互、"+"菜单映射、项目/账户仅展示，后端能力映射表
  - `docs/specs/10_frontend_visual_and_interaction_spec.md` — 更新动态渲染规范（8.4 节完全重写代替固定顺序）、模型选择器只显示 DeepSeek、后端能力到 UI 映射表、"+"菜单映射原则、禁止固定内容序列
  - `docs/specs/11_structured_answer_contract.md` — 重写为动态渲染框架，删除固定内容顺序，新增 frontend rendering flow concept、ChatResponse 映射表、场景-展示对应表、删除 M1.4/M3 历史边界（已由 ADR-009 supersede）
  - `docs/04_powerbi_mcp_and_api_contracts.md` — 同步 ChatResponse 已实现的 report 字段和前端组合回答状态
  - `docs/07_milestones_status_and_open_questions.md` — 补充 M5.0 状态行，待确认事项标记 M5 阶段
  - `docs/08_development_roadmap.md` — M5 拆分为 M5.0/M5.1/M5.2 三段路线
  - `docs/09_context_handoff.md` — 标记 M5.0 已完成，下一步为 M5.1
  - `README.md` — 同步 M5.0 状态
  - `CHANGELOG.md` — 新增 M5.0 条目

### M4.4.2 final boundary closure

- 根因：SQLite `_model_to_work_memory()` 在 `payload_json` 缺失时用 dedicated columns 构造 partial `StructuredWorkMemory`；columns 不含 filters/time/sort/top_n/last_query_plan 等完整 canonical state，可能把损坏 committed state 解释为更宽查询。
- 最终语义：modern committed WorkMemory 的完整 domain reconstruction authority 仅为 `payload_json`。NULL/empty、malformed JSON、字段不完整、domain validation failure 或 row/payload integrity mismatch 全部 fail closed；dedicated columns 仅为 query/index/integrity/support fields，不再替代 executable semantic state。无 legacy partial reconstruction contract。
- `MemoryRepository.get_latest_committed()` / `list_by_conversation()` 的 runtime namespace 在 ABC、InMemory、SQLite 与 production callers 中 mandatory；删除跨模式 aggregate 默认行为。InMemory exact conversation/request ID 跨 Mock/Real overwrite 已由 composite conversation-store key 修复。
- 最终 audit 发现并最小修复两个额外 P1：非 legacy committed time corruption 不再在 StateTransition 静默清空；terminal Snapshot row/payload request/conversation/fingerprint/terminal mismatch 不再通过 replay。未发现 P0；未做大重构或未来功能。
- M0—M4 semantic/DAX/fact/report/memory/snapshot/namespace/filesystem authority 保持封板模型；Real failure 不回退 Mock，history/persistence 不成为 factual authority，report HTML 继续只从 filesystem 恢复。

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

### M4.4.2 fresh acceptance

- Payload/namespace/audit targeted + adjacent suites：`607 passed`。
- Backend full regression：`1700 passed, 1 skipped`。
- Golden：`11 passed, 1 manual-real skipped`；Architecture `109`、Repository Safety `239`、Error Ledger `25`、Documentation Governance PASS。
- Alembic head 保持 `c8d4e6f2a109`；fresh DB → head 与 head → head 幂等 upgrade PASS，确认无新增 migration。
- `backend/app/config/settings.py`：version → M4.4.2。
- M4.4.2 FINAL PASS；M5 NOT STARTED；不新增 Tag。

## 下一步

后续轮次只有用户另行批准后才可开始：

1. **M5.2**: 视觉与交互收口（真实 DeepSeek + Local MCP 多轮对话测试、结构化表格/图表契约决策、响应式、accessibility、最终视觉验收）（NEXT；仅用户另行批准后开始）

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

## 本地启动（PowerShell 标准流程）

先执行一次 `conda init powershell`（首次使用），然后关闭并重新打开 PowerShell：

```powershell
conda activate PBIAgent
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

```powershell
cd frontend
npm install
npm run dev
```

验证 Python 路径：`python -c "import sys; print(sys.executable)"` 应输出 `D:\Conda\envs\PBIAgent\python.exe`。

常见问题见 `README.md` 的"常见启动问题"。

---

*最后更新：2026-08-21 | M5.1 — React 前端实现与核心联调（已完成）*
