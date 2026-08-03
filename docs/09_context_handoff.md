# 09 — 跨对话上下文交接

> **所有新 Claude 恢复上下文的唯一最新交接入口。**
> **每轮结束时覆盖更新，不追加失效信息。**
> **最后更新：2026-08-03 | M1.3.1 QueryPlan与DAX验证修复**

---

## 当前项目目标摘要

开发供公司内部少量人员使用的 Power BI 数据分析 Agent MVP。用户通过自然语言对话查询 Power BI 语义模型数据，并以固定模板生成静态 HTML 报表。

## 当前阶段

**M1.3.1 QueryPlan与DAX验证修复** — ✅ 已完成。

## 当前完成轮次

**M1.3.1** — QueryPlan与DAX验证修复

## 上一轮

**M1.3** — 真实QueryPlan与DAX生成（主体实现 `441ca45`，文档回填 `c0e782b`）

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
| M1.3 | 真实QueryPlan与DAX生成 | `441ca45` / `c0e782b` | 2026-08-03 |

## 最近封板 Tag

| Tag | Commit | 说明 |
|-----|--------|------|
| `m0.4.1-foundation-release` | `1f967b0` | M0.4.1 封板 |
| `m0.4-foundation-release` | `d5c1634` | M0.4 封板 |

## M1.3 交付内容（主体实现 `441ca45` + 文档回填 `c0e782b`）

### M1.2 审计收口（三项）

1. **from_committed_memory() state_status 检查** — `backend/app/intent/context.py`：committed 继承白名单字段、pending/failed/缺失不继承任何业务上下文
2. **无效 Prompt 测试修复** — `test_prompt_forbids_dax_and_answer`：永真断言 `"不得生成 DAX" in system or "不得生成 DAX" not in system` → `"不得生成 DAX" in system`
3. **验证错误脱敏** — `DeepSeekIntentService` 不再将 `str(LLMValidationError)` 拼入 `IntentRecognitionError`

### DeepSeekQueryPlanService

- **位置：** `backend/app/query_plan/`（deepseek_service.py、prompt.py、context.py）
- 复用现有 `QueryPlan`、`IntentSpec`、`SemanticModelSchema` 模型
- 声明复用 `ValidationService.validate_query_plan()`（**实际调用在 M1.3.1 补齐**）
- 只处理 `data_question` 和 `report_generation`；`clarification`/`unsupported` 明确拒绝
- Prompt：严格 JSON、只用 Schema 真实字段、不生成 DAX/答案、不调用工具、不虚构
- 最多一次格式修复（仅 JSON/Schema 错误）
- Schema 安全精简视图（不暴露 DAX 表达式）

### DeepSeekDAXService

- **位置：** `backend/app/dax/`（deepseek_service.py、prompt.py、safety.py）
- DAX 只读安全验证器（**M1.3 使用全局名称集合验证，表—归属验证在 M1.3.1 补齐**）
- 禁止：写入/删除/更新、SQL/Shell/Python/JS、多语句注入、注释绕过、非法对象、空 DAX
- 允许：EVALUATE、SUMMARIZECOLUMNS、FILTER、TOPN、ORDER BY、DEFINE MEASURE、VAR、RETURN
- 验证结果结构化：is_valid、errors、warnings、referenced_objects
- 最多一次修复（JSON/Schema/安全验证错误）

### API 与 Health 边界

- Mock：200，ready=true，version=M1.3
- DeepSeek 无 Key：503，deepseek_api_key_missing
- DeepSeek 有 Key：503，deepseek_pipeline_not_ready
- Health 不访问网络
- Chat DeepSeek 模式仍 503（完整链路待 M1.4-M1.5）

### 测试结果（M1.3 结束时）

- pytest：675 passed
- Golden Cases：11 passed，1 skipped
- 安全扫描：PASS
- 真实 Smoke：`python -m backend.app.query_plan.deepseek_query_dax_smoke`（脱敏输出）

---

## M1.3.1 交付内容

### QueryPlan 真实 Schema 验证

- `DeepSeekQueryPlanService.generate()` 实际调用 `ValidationService.validate_query_plan(plan, schema)`
- 为每次调用构造 `ValidationService(allowed_semantic_models=[schema.key])`
- 验证错误与格式错误共用一次修复配额
- 验证修复请求携带安全错误代码 + ≤5 个非法对象名
- 网络/鉴权/限流/超时/HTTP 5xx 不进入修复

### DAX 表—对象归属验证

- `_SchemaIndex`：表→{columns, measures}，measure→tables，column→tables
- 带表限定引用验证归属关系（不因全局名称集合误判）
- 未限定引用分别处理：度量值唯一解析、列拒绝、歧义标记
- 未加引号/含空格表名正确识别
- 字符串别名不被误判为 Schema 对象
- 新增错误代码：unknown_table、object_not_in_table、unknown_measure、ambiguous_measure、unqualified_column_reference

### 测试

- QueryPlan：11 个新增真实验证集成测试
- DAX：12 个新增多表归属测试

### Smoke

- query_plan_repair_count=0、dax_repair_count=0、total_tokens=2178
- 多表 Schema（Sales + Customer）
- true positive: intent=data_question, QP valid, DAX valid+read_only
- 修复：llm_mode 默认值导致 Provider 未注册的 KeyError

---

## M1.3.1 允许和禁止范围

**允许：**
- QueryPlan 与 DAX 验证修复
- 多表和 Smoke 测试

**禁止：**
- Answer 真实生成
- ReportSpec 真实生成
- 真实 Power BI 连接
- 完整 Chat 链路开放
- 前端 / SSE / Docker / Redis / LangGraph / 多 Agent
- 新建 Tag
- 修改历史 Tag / Commit
- Force push
- M1.4 代码

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
