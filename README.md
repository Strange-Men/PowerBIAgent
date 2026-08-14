# PowerBIAgent — Power BI 数据分析 Agent MVP

PowerBIAgent 面向公司内部少量业务用户，通过自然语言查询 Power BI 语义模型，并在后续阶段以固定模板生成静态 HTML 报表。

当前版本：**M2.6.4 final hardened candidate**；本地 offline/Real hardened acceptance 已完成，等待远程审计。

```text
Natural Language
→ FastAPI / TurnPipeline
→ Semantic Grounding
→ Canonical QueryPlan
→ Deterministic DAX
→ Independent Layer 3
→ Power BI MCP
→ QueryResult
→ VerifiedFactSet
→ fact-bounded Answer / ReportSpec
```

Real 路径的 DAX LLM authority/call count 为 0。LLM 不定义 canonical Measure、Dimension、Member、Time、DAX、QueryResult 或外部事实；VerifiedFactSet 是数值、结果顺序、极值、筛选、时间与 provenance 的唯一事实 authority。

## 当前状态

- M0—M1 已正式封板；M2 Local MCP + Power BI Desktop 真实数据问答已完成 final hardening 候选。
- Business Semantic Catalog、Grounding/StateTransition、PendingClarificationContext、Deterministic DAX、Independent Layer 3 与 VerifiedFactSet 已实现。
- TopN boundary ties 可超过 N；Answer 只表达 QueryResult `result_position`，不把 row index 写成严格 business rank。
- Bounded LLM selector 只能选择 Catalog-owned、metadata-backed shortlist ID；无唯一证据必须 clarification。
- data/report-shaped 请求不会仅因 Intent LLM 的 `UNSUPPORTED` 绕过 Grounding；明确破坏性、越权、任意代码与非数据请求仍 early-stop。
- Remote MCP 生产化 Deferred。下一功能阶段是 M3 Renderer，但当前分支不进入 M3/M4/M5。
- `dev/m2.6.4-final-hardening` 只等待远程审计；不合并 `main`，不创建 Tag。

幂等规则：相同 `request_id` + 相同请求重放且不重复执行；相同 ID + 不同内容返回 HTTP 409；并发同 ID 只有一个 Owner 执行。

## 开发环境

要求 Windows、Python 3.11；本仓库固定 Conda 环境名为 `PBIAgent`。

```powershell
D:\Conda\Scripts\conda.exe create -n PBIAgent python=3.11 -y
D:\Conda\envs\PBIAgent\python.exe -m pip install -e ".[dev]"
```

Mock 模式无需 API Key。需要真实 DeepSeek 时，由用户本人创建本地配置：

```powershell
Copy-Item .env.example .env
```

`.env`、Token、PBIX、真实业务输出和 `local_state/` 禁止提交；代码 Agent 不读取 `.env` 内容。Provider Secret 永不进入前端。

主要配置：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `LLM_MODE` | `mock` | `mock` / `deepseek` |
| `POWERBI_MODE` | `mock` | `mock` / `local_mcp`；`remote_mcp` 仍 Deferred |
| `POWERBI_LOCAL_SEMANTIC_MODEL_KEY` | `local_desktop_model` | Local friendly model key |
| `HOST` | `127.0.0.1` | 后端监听地址 |
| `PORT` | `8000` | 后端监听端口 |

## 启动与接口

```powershell
D:\Conda\envs\PBIAgent\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
curl http://127.0.0.1:8000/health
```

Health 示例：

```json
{
  "status": "ok",
  "ready": true,
  "configuration_ready": true,
  "powerbi_live_connected": false,
  "version": "M2.6.4",
  "llm_mode": "mock",
  "powerbi_mode": "mock"
}
```

`ready` 等同 `configuration_ready`，只说明当前配置可创建运行模式，不代表 Power BI Desktop 实时在线。真实连接由实际 Turn 或人工 Smoke 验证。

对话接口：

```powershell
curl -X POST http://127.0.0.1:8000/api/v1/chat `
  -H "Content-Type: application/json" `
  -d '{"message":"本月销售额是多少？"}'
```

## Local MCP 前置

- Windows + 已打开测试 PBIX 的 Power BI Desktop。
- Node.js 20+；Local Server 固定实机基线为 `@microsoft/powerbi-modeling-mcp@0.5.0-beta.12`，以 stdio + `--readonly` 启动。
- Local Demo 不要求 Tenant ID、Client ID 或 Microsoft Token。
- 业务层只能经 TurnPipeline → ToolGateway → PowerBIAdapter；不得直接调用 MCP。

## 验证命令

```powershell
# Full offline regression
D:\Conda\envs\PBIAgent\python.exe -m pytest backend\tests -q
D:\Conda\envs\PBIAgent\python.exe -m backend.app.harness.cases

# Deterministic gates
D:\Conda\envs\PBIAgent\python.exe scripts\check_architecture_gate.py
D:\Conda\envs\PBIAgent\python.exe scripts\check_repository_safety.py
D:\Conda\envs\PBIAgent\python.exe scripts\check_ai_error_ledger.py
D:\Conda\envs\PBIAgent\python.exe scripts\check_documentation_governance.py

# Known-answer / multi-turn offline
D:\Conda\envs\PBIAgent\python.exe scripts\manual_smoke\m2_known_answer_multiturn_smoke.py --mode offline
```

真实 M2 hardened acceptance（需用户本地 DeepSeek 配置并打开测试 PBIX）：

```powershell
D:\Conda\envs\PBIAgent\python.exe scripts\manual_smoke\m2_semantic_grounding_smoke.py --historical-repeats 5
D:\Conda\envs\PBIAgent\python.exe scripts\manual_smoke\m2_known_answer_multiturn_smoke.py --mode real --historical-repeats 10
```

旧的分层 Local 连接/Schema/DAX/Chat/Business Golden Smoke 仍位于 `scripts/manual_smoke/`，仅在对应 Provider 诊断时按需执行。真实输出必须保持脱敏且不进入 Git。

## 里程碑边界

| 层级 | 当前状态 |
|---|---|
| FastAPI / TurnPipeline / ToolGateway | ✅ 统一确定性控制面 |
| DeepSeek + Mock LLM | ✅ 共用 Provider 边界；Real DAX authority=0 |
| Power BI | ✅ Local Desktop；Remote Deferred |
| Semantic Grounding / Clarification | ✅ Canonical authority + Pending/Committed 分离 |
| VerifiedFactSet / factual output | ✅ 事实边界 |
| 正式 HTML Renderer | ⬜ M3 |
| 持久化会话 | ⬜ M4 |
| React + Vite UI | ⬜ M5 |

## 文档入口

- `AGENTS.md`：代码 Agent 仓库入口、铁律与 Cold Start。
- `docs/index.md`：Documentation Map 与 P0—P3 阅读优先级。
- `PROJECT_CHARTER.md`：项目北极星。
- `docs/00_product_requirements_document.md`：正式唯一 PRD。
- `docs/08_development_roadmap.md`：精简路线。
- `docs/09_context_handoff.md`：当前状态与下一步。
- `docs/adr/`：长期架构决策。
- `docs/specs/`、`docs/milestones/`：专项规范和阶段计划。
- `docs/archive/`：默认不读的历史资料。

专有软件，公司内部使用。

---

*最后更新：2026-08-14 | M2.6.4 final hardened candidate*
