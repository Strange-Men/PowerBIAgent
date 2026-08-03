# 09 — 跨对话上下文交接

> **所有新 Claude 恢复上下文的唯一最新交接入口。**
> **每轮结束时覆盖更新，不追加失效信息。**
> **最后更新：2026-08-03 | M1.2 真实意图识别**

---

## 当前项目目标摘要

开发供公司内部少量人员使用的 Power BI 数据分析 Agent MVP。用户通过自然语言对话查询 Power BI 语义模型数据，并以固定模板生成静态 HTML 报表。

## 当前阶段

**M1.2 真实意图识别** — ✅ 已完成。

## 当前完成轮次

**M1.2** — 真实意图识别

## 下一轮

**M1.3 真实QueryPlan与DAX生成**

M1.4—M1.5：未开始

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
| M1.2 | 真实意图识别 | 待提交 | 2026-08-03 |

## 最近封板 Tag

| Tag | Commit | 说明 |
|-----|--------|------|
| `m0.4.1-foundation-release` | `1f967b0` | M0.4.1 封板 |
| `m0.4-foundation-release` | `d5c1634` | M0.4 封板 |

## M1.2 交付内容

### M1.1 审计收口（四项）

1. **网络异常分类补齐** — `backend/app/llm/deepseek.py`：ReadError/WriteError/CloseError/RemoteProtocolError → LLMConnectionError (retryable=true)；LocalProtocolError → LLMRequestError (retryable=false)；均携带安全 error_code
2. **响应结构防御强化** — `_parse_response()` 增加 14 层严格验证：Body 类型、choices 类型、choice 类型、message 类型、finish_reason 类型、model 类型、usage 类型、Token 类型/非负/bool 拒绝；content JSON 对象校验
3. **安全扫描豁免收紧** — `scripts/check_repository_safety.py`：TEST_SAFE_MARKERS 仅在 `backend/tests/` 生效；生产目录不可使用；新增 `_is_python_variable_ref` 全局豁免；新增 `_is_scan_pattern_definition` 窄范围豁免
4. **M1.1 SHA 文档修正** — `docs/09` 和 `CHANGELOG.md` 写入 M1.1 SHA `073a819`，删除"待下轮写入"

### DeepSeekIntentService

- **位置：** `backend/app/intent/deepseek_service.py`
- 基于 `DeepSeekLLMProvider`，复用现有 Provider 和 Registry
- `provider.is_mock=True` 时明确失败
- 支持四类意图：data_question / report_generation / clarification / unsupported
- 最多一次格式修复（仅 JSON/Schema 错误允许修复）
- Service 不保存请求级可变状态，支持并发
- 不调用 MockScenarioResolver、不回退 Mock、不写 Memory、不执行工具

### IntentContextSnapshot

- **位置：** `backend/app/intent/context.py`
- 白名单模型（`extra="forbid"`, `frozen=True`）
- 从 committed memory 提取安全字段子集
- 禁止发送：DAX、查询结果、Trace、pending/failed memory、Secret

### Prompt

- **位置：** `backend/app/intent/prompt.py`
- 集中式构造：系统提示词（12 条规则）、四类意图规则、修复指令
- 上下文渲染：白名单展示，无上下文时提示 clarification

### 格式修复

- **修复次数：** 最多 1 次（首次 + 1 次修复 = 2 次 LLM 调用）
- **可修复错误：** `invalid_content_json`、`output_schema_invalid`
- **不可修复：** 网络、鉴权、限流、5xx、HTTP Envelope 错误
- 修复请求不携带原始完整响应

### IntentSpec 严格化

- IntentSpec 和 FilterSpec 增加 `extra="forbid"`
- 字符串首尾空白清理、列表去空去重保持顺序
- 第五类意图拒绝、空 normalised_question 拒绝、confidence 越界拒绝
- 跨字段规则：clarification/unsupported/data_question/report_generation 互斥

### 测试结果

**pytest：** 604 passed（M1.1 506 + M1.2 新增 98, 5 个版本号更新）
**Golden Cases：** 11 passed，1 skipped
**安全扫描：** PASS

### API 与 Health 边界

- Mock 模式：Health 200, ready=true, version=M1.2
- DeepSeek 无 Key：Health 503, deepseek_api_key_missing
- DeepSeek 有 Key：Health 503, deepseek_pipeline_not_ready
- Chat DeepSeek 模式：503，不回退 Mock
- Health 不发起网络请求

### 真实 Intent Smoke

- **Smoke 命令：** `python -m backend.app.intent.deepseek_intent_smoke`
- 5 个合成案例覆盖四类意图
- 输出仅含脱敏字段（case_id, expected, actual, confidence, schema_valid, attempts, model, tokens）
- 不输出 normalized_question 全文、clarification_question 全文、原始 Prompt/响应

## M1.3 允许和禁止范围

**允许：**
- QueryPlan 结构化生成
- 根据 Semantic Model Schema 生成 DAX
- DAX 只读安全验证
- 格式失败、非法字段和超限兜底

**M1.3 禁止：**
- 真实 Answer / ReportSpec 生成
- 真实 Power BI 连接
- React 前端 / SSE / Docker / Redis / LangGraph / 多 Agent
- 修改历史 Tag

## 未完成或待观察事项

- 跨进程持久化和分布式锁延后处理
- 项目负责人 Power BI 账号状态（M2 前确认）
- Entra App Registration 权限（M2 前确认）
- Power BI Tenant 设置（M2 前确认）
- Remote MCP Server 端点可用性（M2 早期验证）
- DeepSeek Chat 真实意图链路已接通但完整 Chat 仍未开放（待 M1.3-M1.4）

---

*最后更新：2026-08-03 | M1.2 真实意图识别*
