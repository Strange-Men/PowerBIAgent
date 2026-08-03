# 09 — 跨对话上下文交接

> **所有新 Claude 恢复上下文的唯一最新交接入口。**
> **每轮结束时覆盖更新，不追加失效信息。**
> **最后更新：2026-08-03 | M1.3 真实QueryPlan与DAX生成**

---

## 当前项目目标摘要

开发供公司内部少量人员使用的 Power BI 数据分析 Agent MVP。用户通过自然语言对话查询 Power BI 语义模型数据，并以固定模板生成静态 HTML 报表。

## 当前阶段

**M1.3 真实QueryPlan与DAX生成** — ✅ 已完成。

## 当前完成轮次

**M1.3** — 真实QueryPlan与DAX生成

## 下一轮

**M1.4 真实Answer与ReportSpec生成**

M1.5：未开始

## 已完成版本

| 版本 | 名称 | Commit SHA | 日期 |
|------|------|-----------|------|
| M0.1 | 仓库初始化与文档基线 | `eb5812d` | 2026-07-31 |
| M0.2 | 智能体架构与记忆设计 | `d03ac6c` | 2026-07-31 |
| M0.3 | 数据接入与验证闭环 | `c3510f2` | 2026-07-31 |
| M0.3.1 | 验证闭环加固修复 | `3c7cc7c` | 2026-07-31 |
| M0.3.2 | 工具网关与并发闭环修正 | `ec1afcc` | 2026-07-31 |
| M0.3.3 | Mock场景并发隔离修复 | `d0d47e3` | 2026-07-31 |
| M0.4 | 项目骨架与阶段收尾 | `d5c1634` | 2026-07-31 |
| M0.4.1 | API骨架真实性修复 | `1f967b0` | 2026-07-31 |
| M1.0 | M0遗留收口与M1路线固化 | `9247322` | 2026-07-31 |
| M1.0.1 | 幂等并发与文档收尾修复 | `c223d7b` | 2026-07-31 |
| M1.0.2 | 密钥与仓库安全规则固化 | `5726959` | 2026-07-31 |
| M1.1 | DeepSeek Provider基础接入 | `073a819` | 2026-08-03 |
| M1.2 | 真实意图识别 | `53cf43e` | 2026-08-03 |
| M1.3 | 真实QueryPlan与DAX生成 | 待提交 | 2026-08-03 |

## 最近封板 Tag

| Tag | Commit | 说明 |
|-----|--------|------|
| `m0.4.1-foundation-release` | `1f967b0` | M0.4.1 封板 |
| `m0.4-foundation-release` | `d5c1634` | M0.4 封板 |

## M1.3 交付内容

### M1.2 审计收口（三项）

1. **from_committed_memory() state_status 检查** — `backend/app/intent/context.py`：committed 继承白名单字段、pending/failed/缺失不继承任何业务上下文
2. **无效 Prompt 测试修复** — `test_prompt_forbids_dax_and_answer`：永真断言 `"不得生成 DAX" in system or "不得生成 DAX" not in system` → `"不得生成 DAX" in system`
3. **验证错误脱敏** — `DeepSeekIntentService` 不再将 `str(LLMValidationError)` 拼入 `IntentRecognitionError`

### DeepSeekQueryPlanService

- **位置：** `backend/app/query_plan/`（deepseek_service.py、prompt.py、context.py）
- 复用现有 `QueryPlan`、`IntentSpec`、`SemanticModelSchema` 模型
- 复用现有 `ValidationService.validate_query_plan()`
- 只处理 `data_question` 和 `report_generation`；`clarification`/`unsupported` 明确拒绝
- Prompt：严格 JSON、只用 Schema 真实字段、不生成 DAX/答案、不调用工具、不虚构
- 最多一次格式修复（仅 JSON/Schema 错误）
- Schema 安全精简视图（不暴露 DAX 表达式）

### DeepSeekDAXService

- **位置：** `backend/app/dax/`（deepseek_service.py、prompt.py、safety.py）
- 复用现有 `DAXRequest` 模型
- Prompt：只生成只读 EVALUATE DAX、只用 Schema 对象、不生成 SQL/脚本/答案
- 独立 DAX 只读安全验证器（不依赖 EVALUATE 字符串匹配）
- 禁止：写入/删除/更新、SQL/Shell/Python/JS、多语句注入、注释绕过、非法对象、空 DAX
- 允许：EVALUATE、SUMMARIZECOLUMNS、FILTER、TOPN、ORDER BY、DEFINE MEASURE、VAR、RETURN
- 验证结果结构化：is_valid、errors、warnings、referenced_objects
- 最多一次修复（JSON/Schema/安全验证错误）

### 一次修复边界

- QueryPlan 修复：仅 `invalid_content_json` / `output_schema_invalid`
- DAX 修复：JSON/Schema 错误 + 安全验证失败
- 修复请求只包含：原 QueryPlan 摘要、精简 Schema、安全错误代码、缺失/非法对象名
- 不发送：Secret、完整异常堆栈、HTTP Body、完整历史响应、真实查询结果
- 第二次仍失败立即停止，不允许第三次调用

### API 与 Health 边界

- Mock：200，ready=true，version=M1.3
- DeepSeek 无 Key：503，deepseek_api_key_missing
- DeepSeek 有 Key：503，deepseek_pipeline_not_ready
- Health 不访问网络
- Chat DeepSeek 模式仍 503（完整链路待 M1.4-M1.5）
- 不混用真实 Intent + Mock QueryPlan 等混合链路

### 测试结果

- pytest：675 passed
- Golden Cases：11 passed，1 skipped
- 安全扫描：PASS
- 真实 Smoke：`python -m backend.app.query_plan.deepseek_query_dax_smoke`（脱敏输出）

## M1.4 允许和禁止范围

**允许：**
- 真实 Answer 生成
- 真实 ReportSpec 生成
- 根据 Mock QueryResult 生成自然语言答案
- Answer 和 ReportSpec 校验

**M1.4 禁止：**
- 真实 Power BI 连接和查询
- React 前端 / SSE / Docker / Redis / LangGraph / 多 Agent
- 修改历史 Tag

## 未完成或待观察事项

- 跨进程持久化和分布式锁延后处理
- 项目负责人 Power BI 账号状态（M2 前确认）
- Entra App Registration 权限（M2 前确认）
- Power BI Tenant 设置（M2 前确认）
- Remote MCP Server 端点可用性（M2 早期验证）
- 完整 Chat 仍未开放（待 M1.4-M1.5）
- Answer/ReportSpec 生成仍使用 Mock（待 M1.4）

---

*最后更新：2026-08-03 | M1.3 真实QueryPlan与DAX生成*
