# 09 — 跨对话上下文交接

> **当前状态交接入口；Claude / Codex / 其他代码 Agent 必须先从仓库根目录 `AGENTS.md` 进入。**
> **每轮结束时覆盖更新，不追加失效信息。**
> **最后更新：2026-08-11 | M2.3 真实 DAX 执行与 QueryResult 标准化完成候选**

---

## 当前项目目标

开发供公司内部少量人员使用的 Power BI 数据分析 Agent MVP。用户通过自然语言查询 Power BI 语义模型数据，以固定模板生成静态 HTML 报表。前端为 GPT 式极简对话网页（M5 React 开发）。

## 当前阶段

**M2.3 真实 DAX 执行与 QueryResult 标准化** — ✅ 已完成候选。

> 当前 Demo 通过既有 ToolGateway → PowerBIAdapter → Local MCP 边界真实读取 Schema、执行 `dax_query_operations Execute` 并标准化 Power BI Desktop row data。实机协议为 `2025-11-25`；固定 ROW 值 1 与 `Total Sales` / `Total Quantity` 实际数值均验证成功，结果为 `source_mode=real` 的 QueryResult。未调用 DeepSeek、未接完整 Chat、未将 Local Provider 注入 TurnPipeline；Remote 生产化 Deferred。

## 上一轮

**M2.2** — 真实 Semantic Model Schema 接入（Commit `caf21ebcd9650599b39374d5a815e6f966b38482`，远程 CI Run #31465570747 success）。

## 固定封板 Tag

`m1.7.2-m0-m1正式封板` — 已真实存在，指向 `23d8ddb94a166d51fa7ba0d14620320b3e8d6b75`。

## 下一动作

进入 **M2.4 接入现有 TurnPipeline**。只允许把现有 Local Adapter 注入既有组合根并在现有 QueryPlan → DAX → ToolGateway → QueryResult → Answer / Snapshot 链传播 `source_mode=real`；不得复制 Real Service / Pipeline，不得静默回退 Mock。Issue #124 仍为 Open，虽然当前 beta.12 + mcp 2.0.0 + Desktop 实机未复现，后续 Preview 版本变更仍需重新 Smoke。

以后 Claude / Codex / 其他代码 Agent 均以根目录 `AGENTS.md` 为仓库级入口。

## 当前真实能力

- **LLM:** DeepSeek（真实 API）+ Mock（确定性测试）
- **Power BI:** Mock 完整可用；Local MCP Server 与 Power BI Desktop 已真实连接；Schema、DAX Execute 与 QueryResult 已真实接入；Remote MCP 未实现并因管理员条件 Deferred
- **管线:** 确定性 TurnPipeline（ADR-005），Mock/DeepSeek 共享执行骨架
- **能力:** 意图识别 → QueryPlan → DAX → Answer/ReportSpec，幂等重放，请求指纹冲突检测
- **API:** Health 200/503、Chat 可用/不可用，Mock/DeepSeek 模式切换
- **源模式:** Local QueryResult 已为 `source_mode=real`；Answer / Snapshot 全链传播延后 M2.4，当前 Chat 仍使用 Mock Power BI

## 当前技术边界

- ADR-005 负责 TurnPipeline 总体架构；ADR-006 负责 Remote 生产化；ADR-007 负责当前 Local Demo 路径，三者均 accepted
- M2.3 只允许 Adapter 内部使用 `connection_operations`、五类 Schema 工具的 `List` / `Get` 与 `dax_query_operations Execute`；业务层仍只有 Schema 与 DAX Execute 两类抽象能力
- 任何 Local / Remote MCP SDK 只能位于 PowerBIAdapter 边界之后；Service/API/LLM 不得直接调用 MCP；Real 失败不得回退 Mock
- M2.1—M2.3 不接完整 Chat；M2.4 才接入现有 TurnPipeline。会话持久化属 M4，报表正式渲染属 M3，React 属 M5

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

# 人工验收 Smoke（需 .env 中 DEEPSEEK_API_KEY）
D:\Conda\envs\PBIAgent\python.exe scripts\manual_smoke\deepseek_chat_smoke.py

# 安全扫描
D:\Conda\envs\PBIAgent\python.exe scripts\check_repository_safety.py

# CI（本地模拟）
LLM_MODE=mock POWERBI_MODE=mock D:\Conda\envs\PBIAgent\python.exe -m pytest backend\tests -q
```

## 未完成事项

- M2.4: 接入现有 TurnPipeline（下一阶段）
- M2.5: 真实全链路验收与封板候选（尚未开始）
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

*最后更新：2026-08-11 | M2.3 真实 DAX 执行与 QueryResult 标准化完成候选*
