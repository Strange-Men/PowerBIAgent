# 08 — 开发路线

> **状态：** M1.0.1 已完成
> **更新频率：** 每轮结束时更新完成状态

---

## 路线总览

```
M0 开发准备 (7轮)
  M0.1 仓库初始化与文档基线        ✅ 已完成 (eb5812d)
  M0.2 智能体架构与记忆设计         ✅ 已完成 (d03ac6c)
  M0.3 数据接入与验证闭环           ✅ 已完成 (c3510f2)
  M0.3.1 验证闭环加固修复           ✅ 已完成 (3c7cc7c)
  M0.3.2 工具网关与并发闭环修正      ✅ 已完成 (ec1afcc)
  M0.3.3 Mock场景并发隔离修复        ✅ 已完成 (d0d47e3)
  M0.4 项目骨架与阶段收尾           ✅ 已完成 (d5c1634)
  M0.4.1 API骨架真实性修复          ✅ 已完成 (1f967b0)

M1 真实 DeepSeek 接入 (7轮)
  M1.0 M0遗留收口与M1路线固化       ✅ 已完成 (9247322)
  M1.0.1 幂等并发与文档收尾修复      ✅ 已完成
  M1.0.2 密钥与仓库安全规则固化      ✅ 已完成
  M1.1 DeepSeek Provider基础接入    ✅ 已完成 (073a819)
  M1.2 真实意图识别                 ✅ 已完成 (53cf43e)
  M1.3 真实QueryPlan与DAX生成       ✅ 已完成 (441ca45)
  M1.3.1 QueryPlan与DAX验证修复     ✅ 已完成
  M1.4 真实Answer与ReportSpec生成   ⬜
  M1.5 全链路验收与封板              ⬜

MVP 功能阶段 (后续)
  M2 真实 Power BI MCP 与数据问答    ⬜
  M3 报表生成闭环                   ⬜
  M4 多轮记忆完善                   ⬜
  M5 React 前端与联调                ⬜

后续阶段 (延后)
  商业化权限与部署                    ⬜
```

---

## M1 轮次详细路线

> **重要：M1 必须按照 M1.0 → M1.1 → M1.2 → M1.3 → M1.4 → M1.5 顺序执行。**
> 当前轮未验收不得进入下一轮。不允许跨轮提前实现功能。
> 调整小轮顺序必须由用户明确批准，调整前必须先更新本文件。
> **本文件是小轮路线唯一权威来源。** `docs/09_context_handoff.md` 只负责记录实时进度，不重新定义路线。

---

### M1.0｜M0遗留收口与M1路线固化

**状态：** ✅ 已完成 | **Commit：** `9247322`

**完成内容：**
- clarification/unsupported 保留 conversation_id
- 固定 request_id 幂等重放规则与实现
- 实际报表模板同步写入 Memory（默认 sales_weekly）
- 更新版本号为 M1.0 和开发依赖安装说明
- 固化 M1.0—M1.5 开发顺序

**本轮不接入 DeepSeek。**

---

### M1.0.1｜幂等并发与文档收尾修复

**状态：** ✅ 已完成

**完成内容：**
- 请求指纹与冲突检测：相同 request_id 不同内容 → HTTP 409
- 并发 Owner/Waiter 防重：相同指纹等待，不同指纹冲突
- Report 快照结构化：ReportResultSnapshot 替代无约束 dict
- Service 统一 UUID 生成：conversation_id 和 request_id 未传时服务端生成

**本轮不接入 DeepSeek，不改变 M1.0—M1.5 主路线。**

---

### M1.0.2｜密钥与仓库安全规则固化

**状态：** ✅ 已完成

**完成内容：**
- 确认 `.env.example` 文件名，从模板创建本地 `.env`
- `.env` 被 `.gitignore` 正确忽略且未被 Git 跟踪
- `CLAUDE.md`：新增「Secret 与 API Key 绝对规则」章节（Secret 不入仓库、Claude 不读 .env、API Key 仅后端使用、前端禁止 Secret、日志禁止泄漏、提交前安全检查）
- `docs/06`：同步固化 Secret 文件规则、前端禁止 Secret、日志安全、API Key 填写规则
- `.gitignore`：新增 `.env.backup`、`.env.bak`、`.env.old`、`*.har`、`http_dumps/`、`network_capture/`、`debug_responses/`、`smoke_outputs/`、`secret_scan_output/`、`credentials/`、`private_credentials/`
- 新增 `scripts/check_repository_safety.py`：检查禁止跟踪文件名、前端 Secret、明显真实 Secret
- 新增 `backend/tests/unit/test_repository_safety.py`：26 个测试覆盖
- `README.md`：新增安全设置说明和提交前检查命令
- `docs/08`：新增 M1.0.2 记录
- `docs/09`：交接文档更新

**本轮属于用户批准的专项安全修复，不改变 M1.0—M1.5 六轮主路线。**
**本轮不接入 DeepSeek，不开发 Provider 代码。**

---

### M1.1｜DeepSeek Provider基础接入

**状态：** ✅ 已完成

**完成内容：**
- 从 Settings 读取 API Key、Base URL、模型名
- 实现 DeepSeekLLMProvider（可独立调用、可测试、错误可分类）
- 超时、鉴权、限流、网络和服务错误分类（10 种异常类型）
- 最小真实连通测试通过（deepseek-v4-flash, 70 tokens）
- Mock 模式保持完整可用
- ScenarioFingerprint 替代无约束 Any
- IdempotencyCoordinationError（Owner/Waiter 协调失败 → HTTP 503）
- 安全扫描器纳入测试和 scripts 目录

**本轮不接入真实 Intent 业务流程。**

---

### M1.2｜真实意图识别

**状态：** ✅ 已完成

**完成内容：**
- M1.1 四项审计收口：网络异常分类补齐（ReadError/WriteError/CloseError/RemoteProtocolError/LocalProtocolError）、响应结构防御强化（14 层严格验证）、安全扫描豁免收紧（TEST_SAFE_MARKERS 仅测试目录生效）、M1.1 SHA 文档修正
- DeepSeekIntentService：复用 DeepSeekLLMProvider，支持四类真实意图识别
- IntentContextSnapshot：白名单上下文提取（冻结模型，extra="forbid"）
- 集中式 Prompt 构造：12 条系统规则 + 四类意图定义
- IntentSpec 严格化：extra="forbid"、字符串清理、去重排序、第五类意图拒绝
- 一次格式修复（仅 invalid_content_json / output_schema_invalid 可修复）
- 真实模式不调用 MockScenarioResolver，不回退 Mock
- 真实 Intent Smoke 入口（5 个合成案例，脱敏输出）
- Provider.is_mock=True 时明确失败
- Chat 仍 503（deepseek_pipeline_not_ready），不形成完整业务闭环

---

### M1.3｜真实QueryPlan与DAX生成

**状态：** ✅ 已完成 | **Commit：** `441ca45`（主体实现）、`c0e782b`（文档 SHA 回填）

**完成内容：**
- M1.2 审计收口：from_committed_memory() state_status 检查、无效 Prompt 测试修复、验证错误脱敏
- DeepSeekQueryPlanService：基于 DeepSeek Provider 的真实 QueryPlan 生成
  - 位置：`backend/app/query_plan/`（deepseek_service.py、prompt.py、context.py）
  - 只处理 data_question/report_generation；clarification/unsupported 明确拒绝
  - 复用现有 QueryPlan Pydantic 模型和 ValidationService
  - 最多一次格式修复（JSON/Schema 错误）
- DeepSeekDAXService：基于 DeepSeek Provider 的真实 DAX 生成
  - 位置：`backend/app/dax/`（deepseek_service.py、prompt.py、safety.py）
  - DAX 只读安全验证器：禁止写入/删除/SQL/脚本/注释绕过/多语句/非法对象
  - 结构化解验证结果：is_valid、errors、warnings、referenced_objects
  - 最多一次修复
- Schema 安全精简视图（不暴露 DAX 表达式等内部细节）
- Mock 链路完整可用；Chat DeepSeek 模式仍返回 503
- 真实 Smoke 分离入口：`python -m backend.app.query_plan.deepseek_query_dax_smoke`

---

### M1.3.1｜QueryPlan与DAX验证修复

**状态：** ✅ 已完成

**完成内容：**
- QueryPlan 真实接入 ValidationService.validate_query_plan()（M1.3 声明但未实际调用）
- DAX 表—列/度量值归属关系严格验证（替换全局名称集合验证）
- 多表、未加引号、跨表错误引用测试补强
- 脱敏真实 Smoke 验收通过（QP 0 修复、DAX 0 修复、2178 tokens）
- Smoke KeyError 修复（llm_mode 默认值导致 Provider 未注册）
- M1.3 真实 Commit 关系修正（441ca45 + c0e782b）

---

### M1.4｜真实Answer与ReportSpec生成

**状态：** ⬜ 未开始

**完成内容：**
- 根据 Mock 查询结果生成真实自然语言 Answer
- 生成结构化 ReportSpec
- Report Renderer 仍使用现有 Mock 实现
- 校验回答、证据、模型和 source_mode 一致性

---

### M1.5｜全链路验收与封板

**状态：** ⬜ 未开始

**完成内容：**
- Mock 和 DeepSeek 模式切换
- API 真实调用验证
- DeepSeek 失败不得静默回退 Mock
- 成本、Token、耗时和 Trace 记录
- Golden Cases 继续全部通过
- 新增真实 LLM 基线案例
- 文档收尾
- M1 封板 Commit 和 Tag

---

## M0 历史轮次

### M0.4.1 — API骨架真实性修复

**状态：** ✅ 已完成 | **Commit：** `1f967b0` M0.4.1_API骨架真实性修复

- 依赖可复现（fastapi/uvicorn/pydantic-settings/httpx 版本锁定）
- 公开 API 真实意图流（MockScenarioResolver）
- Answer/Report 真实返回
- Health 真实性（ready/reasons/503）
- app.state 与 lifespan

### M0.4 — 项目骨架与阶段收尾

**状态：** ✅ 已完成 | **Commit：** `d5c1634` M0.4_项目骨架与阶段收尾

- 请求级并发上下文收口
- FastAPI 最小骨架（Settings、Health、Chat 接口）
- M0 全量验收（265 测试 + Golden Cases）

### M0.3.3 — Mock场景并发隔离修复

**状态：** ✅ 已完成 | **Commit：** `d0d47e3` M0.3.3_Mock场景并发隔离修复

- 删除 MockLLMProvider._active_scenario 共享状态
- Scenario Key 仅通过 context 局部传递

### M0.3.2 — 工具网关与并发闭环修正

**状态：** ✅ 已完成 | **Commit：** `ec1afcc` M0.3.2_工具网关与并发闭环修正

- ToolGateway 完整策略检查链
- TraceRecorder 深度安全返回值 + 真实耗时
- Repository (runtime_mode, request_id) 复合键
- 205 个测试全部通过 + 11/11 Golden Cases 通过

### M0.3.1 — 验证闭环加固修复

**状态：** ✅ 已完成 | **Commit：** `3c7cc7c` M0.3.1_验证闭环加固修复

- Memory 模型重构（RuntimeDataMode 枚举）
- Repository 原子化、ToolGateway 真实接入
- MockTurnService 重构、GoldenCaseRunner 异步重构
- 191 个测试全部通过 + Golden Cases 11/11 通过

### M0.3 — 数据接入与验证闭环

**状态：** ✅ 已完成 | **Commit：** `c3510f2` M0.3_数据接入与验证闭环

- Power BI MCP ADR-003、PowerBIAdapter、核心数据契约
- Harness ETCLOVG 完整实现（ADR-004）
- Golden Cases（10 条）、166 个测试全部通过

### M0.2 — 智能体架构与记忆设计

**状态：** ✅ 已完成 | **Commit：** `d03ac6c` M0.2_智能体架构与记忆设计

### M0.1 — 仓库初始化与文档基线

**状态：** ✅ 已完成 | **Commit：** `eb5812d` M0.1_仓库初始化与文档基线

---

*最后更新：2026-08-03 | M1.3.1 QueryPlan与DAX验证修复*
