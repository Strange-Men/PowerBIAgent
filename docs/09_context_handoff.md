# 09 — 跨对话上下文交接

> **所有新 Claude 恢复上下文的唯一最新交接入口。**
> **每轮结束时覆盖更新，不追加失效信息。**
> **最后更新：2026-08-03 | M1.1 DeepSeek Provider基础接入**

---

## 当前项目目标摘要

开发供公司内部少量人员使用的 Power BI 数据分析 Agent MVP。用户通过自然语言对话查询 Power BI 语义模型数据，并以固定模板生成静态 HTML 报表。

## 当前阶段

**M1.1 DeepSeek Provider基础接入** — ✅ 已完成。

## 当前完成轮次

**M1.1** — DeepSeek Provider基础接入

## 下一轮

**M1.2 真实意图识别**

M1.3—M1.5：未开始

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
| M1.1 | DeepSeek Provider基础接入 | 待下轮写入 | 2026-08-03 |

## 最近封板 Tag

| Tag | Commit | 说明 |
|-----|--------|------|
| `m0.4.1-foundation-release` | `1f967b0` | M0.4.1 封板 — 保留不动 |
| `m0.4-foundation-release` | `d5c1634` | M0.4 封板 — 保留不动 |

## M1.0.2 交付内容

### 安全规则固化

**CLAUDE.md：**
- 新增「Secret 与 API Key 绝对规则」章节（共 6 条子规则）
- Secret 永不进入仓库、Claude 不得读取 .env、API Key 仅后端使用
- 前端禁止持有 Provider Secret、日志与测试禁止泄漏
- 提交前安全检查：禁止 `git add .`/`git add -A`，必须使用文件白名单
- Commit 规则新增文件白名单和安全检查步骤

**docs/06 安全规范：**
- 新增 1.1—1.6 节：Secret 文件规则、Claude 禁止读取 .env、后端 Key 规则、前端禁止 Secret、日志安全、API Key 填写规则
- 提交前检查清单更新为 10 项（新增文件白名单和安全扫描步骤）

**.gitignore：**
- 新增 `.env.backup`、`.env.bak`、`.env.old`、`credentials/`、`private_credentials/`
- 新增 `*.har`、`http_dumps/`、`network_capture/`、`debug_responses/`、`smoke_outputs/`、`secret_scan_output/`

**安全检查脚本：**
- `scripts/check_repository_safety.py` — 检查：禁止跟踪文件名、前端 Secret、明显真实 Secret
- 排除测试和脚本目录中的安全检测样本
- 退出码：安全=0，发现风险=非0

**安全测试：**
- `backend/tests/unit/test_repository_safety.py` — 26 个测试全部通过
- 覆盖：禁止文件名、空值/占位值允许、疑似真实值拒绝、前端 Secret 拒绝、输出不含 Secret 原文、当前仓库通过

**.env 状态：**
- `.env.example` 继续受 Git 跟踪，已清理为安全默认状态（所有 Key 为空值，`LLM_MODE=mock`）
- 本地 `.env` 已创建（从 `.env.example` 复制），已被 `.gitignore` 忽略且未被 Git 跟踪
- Claude 本轮未读取 `.env` 内容
- `.env` 中所有 Key 为空，待 M1.1 前由用户本人手动填写真实 DeepSeek API Key

**README：**
- 新增 `.env` 创建和安全说明
- 新增仓库安全检查命令

## M1.1 交付内容

### DeepSeekLLMProvider
- `backend/app/llm/deepseek.py` — 完整实现，支持 httpx 网络调用
- 构造时校验：Key 为空/Base URL 为空/Model 为空 → LLMConfigurationError
- URL 拼接：`<base_url>/chat/completions`，去除末尾 `/`，不产生重复 `//`
- 请求：messages、stream=false、temperature=0、response_format=json_object
- 响应解析：choices[0].message.content → json.loads() → output_type.model_validate()
- 无自动重试、无 Markdown 去除、无 JSON 自动修复

### 异常分类（10 种）
- LLMConfigurationError / LLMAuthenticationError / LLMRateLimitError
- LLMConnectionError / LLMRequestError / LLMServiceError
- LLMResponseError / LLMTimeoutError / LLMValidationError / LLMProviderError

### Factory 与 Registry
- `backend/app/llm/factory.py` — build_llm_registry()
- Mock 模式：仅注册 MockLLMProvider，默认 mock
- DeepSeek 模式：注册 Mock + DeepSeek，默认 deepseek

### Settings
- 版本 M1.1
- `is_deepseek_configured` 属性（仅判断 Secret 是否非空，不访问网络）
- `safe_repr()` 返回 `deepseek_configured=true/false`

### Health 与 Chat
- DeepSeek 无 Key：503, `deepseek_api_key_missing`
- DeepSeek 有 Key：503, `deepseek_pipeline_not_ready`
- Chat DeepSeek 模式：503, 不回退 Mock

### ScenarioFingerprint
- `backend/app/memory/request_fingerprint.py` — 独立 Pydantic 模型
- 五个字段：intent_key/query_plan_key/dax_key/powerbi_key/response_key
- 替代旧的无约束 `Optional[Any]`

### IdempotencyCoordinationError
- Owner/Waiter 协调失败 → HTTP 503
- 不与 IdempotencyConflictError (HTTP 409) 混淆

### 安全扫描器加强
- 不再整体排除 backend/tests 和 scripts
- 测试安全标记系统 (TEST_SAFE_MARKERS)
- 值看起来像 Python 变量名时跳过

### 真实连通测试
- `backend/app/llm/deepseek_smoke.py`
- 通过：success=True, model=deepseek-v4-flash, 70 tokens

### 测试结果
**pytest：** 506 passed
**Golden Cases：** 11 passed，1 skipped
**安全扫描：** PASS

## M1.2 开始前准备

- 无额外准备项（DeepSeek Key 已在 M1.1 验证可用）
- M1.2 只实现真实意图识别，不涉及 QueryPlan/DAX/Answer/ReportSpec

## 未完成或待观察事项

- 跨进程持久化和分布式锁延后处理
- 项目负责人 Power BI 账号状态（M2 前确认）
- Entra App Registration 权限（M2 前确认）
- Power BI Tenant 设置（M2 前确认）
- Remote MCP Server 端点可用性（M2 早期验证）
- DeepSeek Chat 真实意图链路仍未接通

## M1.2 允许范围

**下一轮：** M1.2 真实意图识别

**允许：**
- DeepSeek 输出严格 IntentSpec
- 支持 data_question / report_generation / clarification / unsupported
- JSON 或结构化格式错误自动修复一次
- 真实模式禁止调用 MockScenarioResolver

**M1.2 禁止：**
- 真实 QueryPlan / DAX / Answer / ReportSpec 生成
- 真实 Power BI 连接
- React 前端 / SSE / Docker / Redis / LangGraph / 多 Agent
- 修改历史 Tag

---

*最后更新：2026-08-03 | M1.1 DeepSeek Provider基础接入*
