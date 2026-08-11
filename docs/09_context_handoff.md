# 09 — 跨对话上下文交接

> **当前状态交接入口；Claude / Codex / 其他代码 Agent 必须先从仓库根目录 `AGENTS.md` 进入。**
> **每轮结束时覆盖更新，不追加失效信息。**
> **最后更新：2026-08-11 | M2.4 现有 TurnPipeline 接入真实 Power BI 完成候选**

---

## 当前项目目标

开发供公司内部少量人员使用的 Power BI 数据分析 Agent MVP。用户通过自然语言查询 Power BI 语义模型数据，以固定模板生成静态 HTML 报表。前端为 GPT 式极简对话网页（M5 React 开发）。

## 当前阶段

**M2.4 现有 TurnPipeline 接入真实 Power BI** — ✅ 已完成候选；M2 尚未正式封板。

> 当前 Demo 已复用既有 DeepSeekTurnService、TurnPipeline 与 ToolGateway，真实跑通自然语言 → DeepSeek → Intent → SemanticModelSchema → QueryPlan → DAX → Local MCP → Power BI Desktop → QueryResult → Answer。三个受控业务 Case 均成功；`source_mode=real` 已传播至 Snapshot/Replay，幂等 Replay 不重复调用 LLM/PBI。Remote 生产化继续 Deferred。

## 上一轮

**M2.3** — 真实 DAX 执行与 QueryResult 标准化（Commit `20c2b3ec01273f6a207947addc635993e99431b3`，远程 CI Run #31468672485 success）。

## 固定封板 Tag

`m1.7.2-m0-m1正式封板` — 已真实存在，指向 `23d8ddb94a166d51fa7ba0d14620320b3e8d6b75`。

## 下一动作

进入 **M2.5 真实业务 Golden / Bad Case / 回归验收与 M2 封板候选**。不再新增主架构，不实现 Remote/M3/M4/M5；只扩展真实业务验收并复核当前 Layer 2/3、QueryResult、Answer、Replay、Trace 与 Mock/CI 回归。Issue #124 仍为 Open，当前实机未复现不代表官方已修复。

以后 Claude / Codex / 其他代码 Agent 均以根目录 `AGENTS.md` 为仓库级入口。

## 当前真实能力

- **LLM:** DeepSeek（真实 API）+ Mock（确定性测试）
- **Power BI:** Mock 完整可用；Local MCP + Power BI Desktop 的 Schema、DAX、QueryResult 与 DeepSeek Chat 已真实接入；Remote MCP 未实现并因管理员条件 Deferred
- **管线:** 确定性 TurnPipeline（ADR-005），Mock/DeepSeek 共享执行骨架
- **能力:** 真实 Schema Grounding → QueryPlan Layer 2 → DAX Layer 3 → Answer/ReportSpec，幂等重放，请求指纹冲突检测
- **API:** Health 200/503、Chat 可用/不可用，Mock/DeepSeek 模式切换
- **源模式:** Local QueryResult、Turn、Answer/Report、Snapshot、Replay 均传播 `source_mode=real`

## 当前技术边界

- ADR-005 负责 TurnPipeline 总体架构；ADR-006 负责 Remote 生产化；ADR-007 负责当前 Local Demo 路径，三者均 accepted
- Adapter 内部使用 `connection_operations`、五类 Schema 工具的 `List` / `Get` 与 `dax_query_operations Execute`；业务层仍只有 Schema 与 DAX Execute 两类抽象能力
- 任何 Local / Remote MCP SDK 只能位于 PowerBIAdapter 边界之后；Service/API/LLM 不得直接调用 MCP；Real 失败不得回退 Mock
- M2.4 只替换 Provider 并接入现有 TurnPipeline；会话持久化属 M4，报表正式渲染属 M3，React 属 M5

## 运行命令

```
# 全量测试（Mock 模式，无网络）
D:\Conda\envs\PBIAgent\python.exe -m pytest backend\tests -q

# Golden Cases
D:\Conda\envs\PBIAgent\python.exe -m backend.app.harness.cases

# M2.1 Local MCP 人工连接 Smoke（先打开测试 PBIX）
D:\Conda\envs\PBIAgent\python.exe scripts\manual_smoke\powerbi_local_mcp_connection_smoke.py

# M2.2 Local MCP 人工 Schema Smoke（先打开测试 PBIX）
D:\Conda\envs\PBIAgent\python.exe scripts\manual_smoke\powerbi_local_mcp_schema_smoke.py

# M2.3 Local MCP 人工 DAX Smoke（先打开测试 PBIX）
D:\Conda\envs\PBIAgent\python.exe scripts\manual_smoke\powerbi_local_mcp_dax_smoke.py

# M2.4 DeepSeek + Local Power BI Chat Smoke（先打开测试 PBIX，需本地 DeepSeek 配置）
D:\Conda\envs\PBIAgent\python.exe scripts\manual_smoke\deepseek_local_powerbi_chat_smoke.py

# 人工验收 Smoke（需 .env 中 DEEPSEEK_API_KEY）
D:\Conda\envs\PBIAgent\python.exe scripts\manual_smoke\deepseek_chat_smoke.py

# 安全扫描
D:\Conda\envs\PBIAgent\python.exe scripts\check_repository_safety.py

# CI（本地模拟）
LLM_MODE=mock POWERBI_MODE=mock D:\Conda\envs\PBIAgent\python.exe -m pytest backend\tests -q
```

## 未完成事项

- M2.5: Business Golden、Bad Case、回归验收与 M2 封板候选（下一阶段）
- M3: 报表正式渲染管线、报表资源 ID
- M4: 会话持久化、搜索、最近对话
- M5: React 前端
- Remote 生产化：公司 Tenant setting、Entra App、委托权限与目标模型权限（Deferred，等待管理员条件和用户批准）

## 重要 Tag

| Tag | Commit | 说明 |
|-----|--------|------|
| `m1.7.2-m0-m1正式封板` | `23d8ddb` | M0—M1 正式封板基线 |
| `m1-deepseek-pipeline-release` | `a926b5e` | M1 DeepSeek 全链路封板 |
| `m0.4.1-foundation-release` | `1f967b0` | M0.4.1 封板 |
| `m0.4-foundation-release` | `d5c1634` | M0.4 封板 |

## 近期变更摘要

- M2.4: Local Provider 注入现有 DeepSeekTurnService / TurnPipeline；Layer 2/3、Answer provenance、real Snapshot/Replay 与三个真实自然语言 Case 完成候选
- M2.3: 通过 ToolGateway → LocalMCPPowerBIAdapter 真实执行固定 DAX 并获取 row data；QueryResult、错误与截断边界已标准化，当前实机未复现 Issue #124
- M2.2: 通过 ToolGateway → LocalMCPPowerBIAdapter 单次只读会话真实读取并标准化 Schema；Measure 与基础模型关系已可用于 Semantic Grounding
- M2.1: Demo 路径调整为 Local MCP + Power BI Desktop；新增 ADR-007、Local Adapter / stdio Client 与只读安全边界；Remote ADR-006 完整保留
- M2.0: 官方证据复核、ADR-005 文件化、ADR-006 与原始 M2.1—M2.5 路线固化；生产业务实现为 0
- M1.8: Codex 接管准备与仓库上下文固化
- M1.7.2: M0—M1 正式封板（`23d8ddb`，Tag `m1.7.2-m0-m1正式封板`）
- M1.7.1: 最终状态收口与封板候选修复（`1dd20de`，CI Run #30991136311 success）
- M1.7: MVP轻量化与通用CI固化（`e5d1740`）
- M1.6.6: CI建立、最终架构审计、文档收尾（`084aa76`）
- M1.6.5: 真实测试、机器错题本、架构防偏移治理（`e850f14`）
- M1.6.4: AI真实性门禁、异常处理与对抗测试加固（`4217b66`）
- M1.6.3: 统一TurnPipeline与旧Agent抽象清理（`d6665bd`→`d99d243`→`d57e38c`）
- M1.6.1-2: 架构定案、Harness与配置收口

---

*最后更新：2026-08-11 | M2.4 现有 TurnPipeline 接入真实 Power BI 完成候选；下一阶段 M2.5*
