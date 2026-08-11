# 09 — 跨对话上下文交接

> **当前状态交接入口；Claude / Codex / 其他代码 Agent 必须先从仓库根目录 `AGENTS.md` 进入。**
> **每轮结束时覆盖更新，不追加失效信息。**
> **最后更新：2026-08-11 | M2.0 Remote MCP 接入规划与开发路线固化**

---

## 当前项目目标

开发供公司内部少量人员使用的 Power BI 数据分析 Agent MVP。用户通过自然语言查询 Power BI 语义模型数据，以固定模板生成静态 HTML 报表。前端为 GPT 式极简对话网页（M5 React 开发）。

## 当前阶段

**M2.0 真实 Power BI Remote MCP 官方证据复核、架构设计与路线固化** — ✅ 已完成候选。

> 本轮只修复治理/ADR 文档结构并固化 Remote MCP 官方证据、ADR-006 与 M2.1—M2.5 路线。生产业务逻辑变化为 0；真实 Power BI 仍未接入，M2 业务实现尚未开始。

## 上一轮

**M1.8** — Codex 接管准备与仓库上下文固化（起始基线 Commit `8aede040b74cfeb4f18514ffef3c049da02a5e43`，远程 CI Run #31449122624 success）。

## 固定封板 Tag

`m1.7.2-m0-m1正式封板` — 已真实存在，指向 `23d8ddb94a166d51fa7ba0d14620320b3e8d6b75`。

## 下一动作

进入 **M2.1 MCP Client / OAuth 最小真实连接验证**。只验证 OAuth、initialize/协议协商、`list_tools` 与 connection/health；不得接 Chat 或完整自然语言问答。

以后 Claude / Codex / 其他代码 Agent 均以根目录 `AGENTS.md` 为仓库级入口。

## 当前真实能力

- **LLM:** DeepSeek（真实 API）+ Mock（确定性测试）
- **Power BI:** Mock；真实 Remote MCP 仍未接入
- **管线:** 确定性 TurnPipeline（ADR-005），Mock/DeepSeek 共享执行骨架
- **能力:** 意图识别 → QueryPlan → DAX → Answer/ReportSpec，幂等重放，请求指纹冲突检测
- **API:** Health 200/503、Chat 可用/不可用，Mock/DeepSeek 模式切换
- **源模式:** source_mode=mock（Power BI 使用 Mock 适配器；Real 传播设计延后 M2.4）

## 当前技术边界

- ADR-005 负责 TurnPipeline 总体架构；ADR-006 负责真实 Remote MCP 接入。ADR-003 的认证实现部分已被 ADR-006 替代
- M2 只允许 Remote MCP 的 Schema 与 Execute Query；Generate Query 不进入白名单，避免第二个 DAX 生成入口
- Remote MCP SDK/OAuth 只能位于 PowerBIAdapter 边界之后；Service/API/LLM 不得直接调用 MCP；Real 失败不得回退 Mock
- M2.1—M2.3 不接完整 Chat；M2.4 才接入现有 TurnPipeline。会话持久化属 M4，报表正式渲染属 M3，React 属 M5

## 运行命令

```
# 全量测试（Mock 模式，无网络）
D:\Conda\envs\PBIAgent\python.exe -m pytest backend\tests -q

# Golden Cases
D:\Conda\envs\PBIAgent\python.exe -m backend.app.harness.cases

# 人工验收 Smoke（需 .env 中 DEEPSEEK_API_KEY）
D:\Conda\envs\PBIAgent\python.exe scripts\manual_smoke\deepseek_chat_smoke.py

# 安全扫描
D:\Conda\envs\PBIAgent\python.exe scripts\check_repository_safety.py

# CI（本地模拟）
LLM_MODE=mock POWERBI_MODE=mock D:\Conda\envs\PBIAgent\python.exe -m pytest backend\tests -q
```

## 未完成事项

- M2.1: MCP Client、用户委托 OAuth 与最小真实连接验证（尚未开始）
- M2.2: 真实 Semantic Model Schema 与安全 Model ID 映射（尚未开始）
- M2.3: 真实 DAX 与 QueryResult 标准化（尚未开始）
- M2.4: 接入现有 TurnPipeline（尚未开始）
- M2.5: 真实全链路验收与封板候选（尚未开始）
- M3: 报表正式渲染管线、报表资源 ID
- M4: 会话持久化、搜索、最近对话
- M5: React 前端
- 公司 Power BI 账号、Tenant Remote MCP 设置、Entra App、目标模型 ID 与 Build 权限（M2.1 前确认）

## 重要 Tag

| Tag | Commit | 说明 |
|-----|--------|------|
| `m1.7.2-m0-m1正式封板` | `23d8ddb` | M0—M1 正式封板基线 |
| `m1-deepseek-pipeline-release` | `a926b5e` | M1 DeepSeek 全链路封板 |
| `m0.4.1-foundation-release` | `1f967b0` | M0.4.1 封板 |
| `m0.4-foundation-release` | `d5c1634` | M0.4 封板 |

## 近期变更摘要

- M2.0: 官方证据复核、ADR-005 文件化、ADR-006 与 M2.1—M2.5 路线固化；生产业务实现为 0
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

*最后更新：2026-08-11 | M2.0 Remote MCP 接入规划与开发路线固化*
