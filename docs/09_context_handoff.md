# 09 — 当前上下文交接

> **当前状态入口。** 从根目录 `AGENTS.md` 开始；本文件只回答“现在是什么、下一步做什么”。历史变更见 `CHANGELOG.md` 与 Git。
> **最后更新：** 2026-08-14

## 当前阶段

**M2.6.4 — M0—M2 ready for final seal**。offline/Real hardened acceptance、GPT 远程核心审计与长期文档 semantic truth cleanup 已通过；Final Tag 仍待用户明确授权。

M2.6.4 开发起点：`origin/main = ab9c6a6fba2e0cf9919c1366d37f8c6beb1f5e32`。交付源分支为 `dev/m2.6.4-final-hardening`；只有 fresh gates 全绿且仍可纯 fast-forward 时才按用户授权更新 `main`。Final Tag 仍为 none。

下一功能阶段是 M3 固定模板报表正式渲染，但必须等待本轮 main CI 绿色后由用户另行明确批准；M4/M5 与 Remote MCP 同样未获授权。

## 当前架构与 Truth Boundary

```text
Natural Language
→ FastAPI / TurnService / TurnPipeline
→ Intent
→ ToolGateway → PowerBIAdapter → runtime Schema
→ Semantic Grounding + deterministic StateTransition
→ Canonical QueryPlan
→ Deterministic DAX
→ Independent Layer 3
→ ToolGateway → PowerBIAdapter → Power BI
→ QueryResult
→ VerifiedFactSet
→ fact-bounded Answer / ReportSpec
→ Memory / Snapshot
```

- ADR-005：TurnPipeline 是唯一控制面；Mock/Real 共用执行骨架。
- ADR-006/007：当前 Real Provider 是 Local MCP + Power BI Desktop；Remote 生产化 Deferred，且只能替换 Adapter 后的 Provider。
- ADR-008：runtime schema、model-scoped glossary、runtime members 与固定时间规则拥有业务语义；Intent/QueryPlan LLM 仅是语言 weak signal。
- ADR-009：Real DAX 由普通代码确定性构造，LLM DAX authority/call count 为 0；Independent Layer 3 在执行前 fail closed。
- VerifiedFactSet 是数字、结果顺序、极值、筛选、时间与 provenance 的唯一事实 authority。TopN 只声称 `result_position`，不把 row position 写成严格 business rank。
- PendingClarificationContext 不是 committed Memory；歧义、未解析、unsupported capability、DAX/Tool/Fact failure 均不得提交或污染正式状态。

## 当前真实能力

- Mock + Mock、DeepSeek + Mock、DeepSeek + Local MCP Chat 共用正式 API/TurnPipeline。
- Local MCP 已真实验证 Desktop 发现、Schema、DAX、QueryResult、production Chat 与 actual committed Memory。
- Canonical QueryPlan 支持受限 Measure、Dimension、EQ Filter、resolved TimeRange、single-measure Sort/TopN；其他能力 fail closed。
- Bounded LLM selector 只能选择 Catalog-owned、metadata-backed shortlist ID；无唯一证据必须 AMBIGUOUS/UNRESOLVED。
- data/report-shaped 请求即使被 Intent LLM 误判 `UNSUPPORTED`，也必须进入 Grounding/capability check；明确破坏性、越权、任意代码和非数据请求仍 early-stop。
- Known-answer Oracle 支持 scalar/grouped/ordered、严格显式 tolerance 与 TopN boundary ties；正式多轮契约为 8 Case（2 holdout）、6 Conversation / 16 Turn。
- 幂等重放与 request fingerprint 冲突检测已实现；Health 只表示 configuration ready，不实时探测 Desktop。

## 当前限制与 Open Items

- Remote MCP 需要 Tenant setting、Entra App、委托权限与目标模型权限；仍 Deferred。
- M2 grammar 有意不支持 comparison、非 EQ Filter、自由 DAX、因果解释或通用排名推断。
- Local Modeling MCP 为 Preview，Desktop/npm 包变化后需重新人工 Smoke。
- Memory/Snapshot 当前仍是单进程实现；持久化会话属于 M4。
- 固定模板正式 Renderer、资源 ID、查看/下载契约属于 M3；React UI 属于 M5。
- 当前 PBIX 的 3 个 Real TopN case 未出现 boundary tie；ties 的 truth safety 由 deterministic no-ties/boundary-ties/multiple-equal/truncated/fact-bounded regression 覆盖。

## Fresh Acceptance 摘要

- Offline：backend `1397 passed`；Golden 11/11（Real 专用 1 skip）；Architecture 85、Repository Safety 189、Error Ledger 25、Documentation Governance 全部 PASS。
- Real Semantic：34/34；状态/Filter/Member/Time/TopN/歧义链通过，`a1→a2→a3` 5/5，fallback/pollution 均为 0。
- Real Production E2E：Known-answer 8/8、Holdout 2/2、6/16、`a1→a2→a3` 10/10、51 个成功真实查询、3/3 TopN。
- Truth counters：DAX LLM=0、Answer LLM=0、fallback=0、pollution=0；两项历史 DAX blocker 均为 0。

## 关键命令

```powershell
# 全量离线测试与 Golden
D:\Conda\envs\PBIAgent\python.exe -m pytest backend\tests -q
D:\Conda\envs\PBIAgent\python.exe -m backend.app.harness.cases

# 治理门禁
D:\Conda\envs\PBIAgent\python.exe scripts\check_architecture_gate.py
D:\Conda\envs\PBIAgent\python.exe scripts\check_repository_safety.py
D:\Conda\envs\PBIAgent\python.exe scripts\check_ai_error_ledger.py
D:\Conda\envs\PBIAgent\python.exe scripts\check_documentation_governance.py

# M2.6.1 offline regression
D:\Conda\envs\PBIAgent\python.exe scripts\manual_smoke\m2_known_answer_multiturn_smoke.py --mode offline

# Real Semantic 与 production E2E（需用户本地配置、已打开测试 PBIX）
D:\Conda\envs\PBIAgent\python.exe scripts\manual_smoke\m2_semantic_grounding_smoke.py --historical-repeats 5
D:\Conda\envs\PBIAgent\python.exe scripts\manual_smoke\m2_known_answer_multiturn_smoke.py --mode real --historical-repeats 10
```

## 固定基线与 Tag

| 项目 | 值 |
|---|---|
| M2.6.4 起点 / `origin/main` | `ab9c6a6fba2e0cf9919c1366d37f8c6beb1f5e32` |
| M0—M1 正式封板 | `m1.7.2-m0-m1正式封板` → `23d8ddb` |
| M2 Local Demo | `m2-local-powerbi-demo-release` → `c9af48a` |
| 本轮 Tag | **none；禁止创建** |

## 下一步

M2.6.4 main CI 绿色后停止开发。后续只等待用户明确决定是否创建 M0—M2 Final Tag，或另行批准进入 M3；不得自行打 Tag、开发 Remote MCP 或提前进入 M3/M4/M5。

---

*最后更新：2026-08-14 | M2.6.4 M0—M2 ready for final seal；Final Tag=none*
