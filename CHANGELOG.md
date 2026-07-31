# CHANGELOG

## [M0.3.1] — 2026-07-31

### 验证闭环加固修复

**来源：** M0.3 专项代码审计发现 16 项闭环真实性问题。

**Memory 模型修复：**
- `runtime_mode` 统一为 `RuntimeDataMode` 枚举（不再使用任意字符串）
- 版本语义固化：首次提交 0→1，第二轮 1→2，base_memory_version 驱动
- 移除公共 `commit()`、`bump_version()`、`fail()` 方法 — 只能通过 Repository 改变状态
- 新增 `base_memory_version` 字段 — pending 记录读取时的基准版本
- `MemoryCommitEvidence.business_satisfied` 区分业务条件和版本匹配
- `version_matches` 由 Repository 原子提交时设置，调用方不可伪造

**Repository 加固：**
- `asyncio.Lock` 保护 create_pending/commit/mark_failed 原子性
- 版本检查和递增在同一临界区完成
- `get_latest_committed()` 强制 runtime_mode 过滤
- `list_by_conversation()` 支持 runtime_mode 过滤
- `commit()` 拒绝：不完整 Evidence、failure_reason 非空、非 PENDING 状态、failed/committed、版本冲突、模式不一致
- `mark_failed()` 记录 failure_reason 和 failure_stage
- 保存完整 Memory 快照（全部分析字段）
- Mock 与 Real 完全隔离（相同 conversation_id 不同模式互不可见）

**ToolGateway 真实接入：**
- 三个工具真实注册：get_semantic_model_schema、execute_dax、render_report
- 所有 Adapter 调用统一经过 `gateway.execute()`
- 主链路不再直接调用 `self.powerbi.*` 或 `self.report_renderer.*`
- ToolSpec 权限、UserContext 模型/模板/工具白名单全部生效
- 工具序列来自真实 Gateway 执行，不再硬编码
- 新增异常类型：ToolTimeoutError、ToolExecutionError、ToolOutputValidationError

**MockTurnService 重构：**
- 结构化 `MockScenarioSelection`（五类 Key 全部生效）
- clarification/unsupported 不创建 pending memory
- 移除 `initial_memory` 任意 dict setattr
- 提交前填充完整 Memory 字段（再调用 commit）
- 多轮通过正常第一轮建立真实 committed memory
- 所有失败分支统一标记 failed（含 reason 和 stage）
- `RenderedReport` 结构化返回结果

**ContextBuilder 加固：**
- 检查 Memory 必须为 committed 状态才注入
- runtime_mode 与当前模式一致才注入
- semantic_model_key 与当前选择一致才注入
- failed/pending 不注入
- recent_messages 和 schema_subset 递归 Secret 过滤
- Secret 值模式匹配（sk-、Bearer、JWT）

**TraceRecorder 加固：**
- 每个 Turn 生成唯一 trace_id
- 每条事件自动携带 trace_id/request_id/conversation_id
- 事件索引支持精确更新（不再只更新最后一条）
- Secret 脱敏覆盖：api_key、apiKey、clientSecret、Authorization、Bearer token、嵌套列表
- `get_tool_sequence()` 从 Trace 提取真实工具序列

**ValidationService 加固：**
- `validate_query_result()` 对 error 结果返回 valid=False
- `validate_report()` 绑定当前 QueryResult 字段（KPI/Chart/Table）
- 新增 `validate_answer()` — 语义模型、source_mode、evidence 一致性
- data_source 与当前模型一致检查
- source_mode 与当前运行模式一致检查
- 每行长度与 columns 一致性检查

**GoldenCaseRunner 重构：**
- Async-first：`run_one_async()` / `run_all_async()`
- 安全处理已存在事件循环
- 传入全部五类 Scenario Key（不再只传 intent_key）
- Pydantic 强校验 Case 结构（未知字段/状态/类别拒绝）
- Runtime 配置真实生效（llm_mode/powerbi_mode/harness_mode）
- pending_real_baseline 计为 skipped（不计 error）
- Runner 读取 Repository 验证 Memory 状态
- actual=None 时不假通过
- 稳定命令行入口：`python -m backend.app.harness.cases`

**Golden Cases 重做（12 条）：**
- 11 条 mock_ready + 1 条 pending_real_baseline
- gc_007 虚假字段 → response_failed（不再假通过为 completed）
- gc_002 多轮继承 → setup_turns 真实建立第一轮
- 新增：permission_denied、dax_error、oversized、幂等
- 报表链路期望包含 render_report

**集成测试重做：**
- 所有失败场景检查无 committed、pending 已 failed、版本未递增
- 新增真实版本冲突测试（两个 pending 同 base → 第二个冲突）
- 新增 Gateway 链路测试（工具注册、未注册拒绝、工具序列来源）
- 新增多轮 Repository 字段验证（version、measures、filters、dax）
- 删除名称与断言矛盾的假测试

**测试结果：**
- 191 个 pytest 全部通过（原 166 + 25 新增/重写）
- Golden Cases：11/11 mock_ready 通过，1 skipped
- compileall 通过

**Commit SHA：** `3c7cc7c`
**Push 状态：** ✅ 已推送至 origin/main
**本轮 Tag：** 无（本轮不创建 Tag）

---

## [M0.3.2] — 2026-07-31

### 工具网关与并发闭环修正

**来源：** M0.3.1 专项审计后剩余的小范围真实性问题。

**ToolGateway 策略真正生效：**
- 取消全局 `TOOL_INTENT_POLICY`，以 `ToolSpec.allowed_intents` 为 Intent 权限唯一来源
- `supported_modes` 统一使用 `RuntimeDataMode` 枚举（使用 `default_factory` 安全默认值）
- `read_only` 真实检查 — read_only=False 工具拒绝执行
- 完整策略检查链：read_only → Intent → runtime_mode → 用户工具权限 → 用户模型权限 → 用户模板权限 → 输入类型 → Handler → 输出类型
- 新增 `ToolExecutionContext` 结构化执行上下文（替换松散参数）
- 正确异常分类：ToolTimeoutError/ToolOutputValidationError
- 不重试异常：未注册、权限拒绝、输入/输出类型错误、read_only 不满足
- 有限重试：仅 asyncio.TimeoutError 和 retryable=True 的 Power BI 错误
- Gateway 真实产生 tool_call_started/completed/failed Trace 事件（含 attempt、duration_ms）
- 工具序列唯一来源：`TraceRecorder.get_tool_sequence()` — Application 不再手工拼装

**TraceRecorder 修复：**
- 深度超限返回 `[MAX_DEPTH_REACHED]` 而非原始对象（防止泄露）
- 事件耗时在 `record()` 时自动计算并写入 duration_ms

**状态机失败流修复：**
- `PLAN_READY` 新增合法转换目标：`TOOL_EXECUTED`、`TOOL_FAILED`
- 统一 `_fail_turn()` 方法处理所有失败分支
- Memory 冲突时 pending 标记 failed、不返回 memory_commit=True

**Mock 场景并发安全：**
- MockAgentRuntime 移除共享 `_scenario_key` 实例字段
- 新增并发测试：同一 Runtime 两个不同 Scenario 不串场

**Repository 模式复合键：**
- request_id 索引使用 `(runtime_mode, request_id)` 复合键
- 全部 Repository 方法显式接收 runtime_mode
- Mock 和 Real 相同 request_id 可以共存

**MemoryPolicies 一致性：**
- 提交前策略只检查 `business_satisfied`（不要求 `all_satisfied`）
- `version_matches` 只由 Repository 在原子提交时设置

**查询产物唯一 ID：**
- `QueryResult` 新增 `result_id` 字段（UUID 自动生成）
- Memory 写入 `last_query_result_id` 和 `last_report_id`

**Answer 来源校验：**
- source_mode 不一致从 warning 升级为 error

**Golden Case 模型严格化：**
- 全部模型 `extra="forbid"`，五类 Scenario Key 强制存在
- 每个 Case 独立 Service 和 Repository
- 幂等 Case 真实执行两次（repeat_target_turn）
- 多轮 Case 验证 base_memory_version > 0
- 失败 Case 验证 failed record、reason、stage

**测试结果：**
- 205 个 pytest 全部通过
- Golden Cases：11/11 mock_ready 通过，1 skipped
- compileall 通过

**Commit SHA：** 由下一轮 Git 解析
**Push 状态：** 将在 Git 收尾完成推送
**本轮 Tag：** 无（本轮不创建 Tag）

---

## [M0.3] — 2026-07-31

### 数据接入与验证闭环

**M0.2 审计修复：**
- AgentRuntime 从三引号字符串修复为 runtime.py 真实抽象类
- PydanticAI API 准确性修正：`output_type`（非 `result_type`）
- Mock Fixture 统一到 `harness/fixtures/`
- Mock LLM 异步修复（time.sleep → asyncio.sleep）
- 未知 scenario 严格失败（LLMScenarioNotFoundError）
- IntentSpec 跨字段规则（7 条）+ FilterSpec 结构化筛选
- DeepSeek SecretStr 安全（repr 不泄露 Key）
- 核心依赖锁定（pydantic-ai==2.21.0, pydantic==2.13.4, pytest==9.1.1, pytest-asyncio==1.4.0）
- 记忆系统 Mock 空间规则 + MemoryCommitEvidence + Correction 审计 + InMemoryMemoryRepository
- 状态文档修正（M0.2 Commit `d03ac6c`、自引用 SHA 规则、ADR 编号）

**Power BI 与数据契约：**
- ADR-003：Power BI MCP 认证与接入（Remote MCP + MSAL + Entra App）
- PowerBIAdapter 接口 + MockPowerBIAdapter（可运行 8 种场景）+ RemoteMCP 骨架
- 核心数据契约：QueryPlan、DAXRequest、QueryResult、AnswerSpec、ReportSpec（KPISpec/ChartSpec/TableSpec）、UserContext、FilterSpec

**Harness ETCLOVG：**
- ADR-004：轻量控制面设计
- ToolGateway（工具注册、Intent 权限矩阵、async timeout、有限重试）
- ContextBuilder（最近 5 轮、Secret 排除、输入截断）
- TurnController（19 状态完整状态机、资源限制、MemoryCommitEvidence）
- ValidationService（Intent/QueryPlan/DAX/QueryResult/Report/Memory 六类验证）
- TraceRecorder（JSON Trace + Secret 脱敏）

**Application 与 Golden Cases：**
- MockAgentRuntime + MockReportRenderer + MockTurnService
- Golden Cases 10 条（8 mock_ready）+ GoldenCaseRunner
- 166 个测试全部通过

**Commit SHA：** `c3510f2`
**Push 状态：** ✅ 已推送至 origin/main
**本轮 Tag：** 无（本轮不创建 Tag）

**已锁定依赖：**
- pydantic-ai 2.21.0, pydantic 2.13.4
- pytest 9.1.1, pytest-asyncio 1.4.0
- pyyaml 6.0.3

---

## [M0.2] — 2026-07-31

### 智能体架构与记忆设计

**新增：**

**Agent 框架：**
- ADR-001：Agent 框架选择 — PydanticAI 2.21.0
- AgentRuntime Adapter 骨架（`backend/app/agent/`），隔离框架依赖

**意图识别：**
- IntentType 四类意图枚举：data_question、report_generation、clarification、unsupported
- IntentSpec 完整 Pydantic 模型（12 个字段）
- IntentService 抽象接口
- unsupported 意图（非法/越权要求），禁止进入后续流程

**LLM Provider：**
- LLMProvider 抽象基类（支持意图识别、QueryPlan、DAX、AnswerSpec、ReportSpec）
- LLMProviderRegistry：统一 Provider 选择，业务层不散落 if/else
- DeepSeekProvider 骨架（API Key、Base URL、Model、超时、重试），M1 实现真实调用
- MockLLMProvider 可运行：7 种预设场景（data_question/report_generation/clarification/unsupported/timeout/invalid_structure/missing_fields）

**记忆系统：**
- ADR-002：记忆系统与存储方案
- 四层记忆设计：原始对话、结构化工作记忆、滚动摘要、查询产物
- StructuredWorkMemory 完整 Pydantic 模型（30+ 字段）
- 三态机制：pending、committed、failed
- 记忆提交准入条件（MemoryPolicies.check_commit_eligibility）
- request_id 幂等 + memory_version 乐观锁
- 上下文切换策略：模型切换、模板切换、重新开始、纠正口径
- Context Assembly 契约（允许/禁止的上下文类型）
- MemoryRepository 抽象接口

**测试：**
- 65 个单元测试全部通过
- 覆盖：IntentSpec 合法/非法、Mock LLM 全部场景、Provider Registry、Memory 状态/版本/幂等/准入/切换/Context Assembly
- PydanticAI 框架 Smoke Test

**M0.1 一致性修复 (M0.2 本轮完成)：**
- 修复 CHANGELOG、docs/07、docs/09 中的错误 Commit SHA（`fd9e57a` → `eb5812d`）
- 修复 "待提交"/"待推送" 状态为已完成
- 统一文档来源优先级（原始 PRD 降级为历史参考，正式 PRD 为需求基线）
- 更新 PROJECT_CHARTER.md、CLAUDE.md、docs/06 中的文档优先级
- 修复 M0.3 职责（包含完整 Harness、Golden Cases、Mock 闭环）
- 修复 M0.4 职责（收敛为 FastAPI 骨架与收尾）
- 明确真实 Power BI 账号不是 M0.3 硬性前置条件
- 统一后端目录为 `backend/app` 和 `backend/tests`
- 修复 pyproject.toml 包发现和测试路径
- 修复 README Conda 命令（标注未验证命令）
- 修复 docs/03 记忆提交机制表述（每轮结束提交 → only-committed）
- 修复 environment.yml（移除未验证的 `-e .`）

**已安装依赖：**
- pydantic-ai 2.21.0
- pydantic 2.13.4
- pydantic-ai-slim 2.21.0
- pytest 9.1.1
- pytest-asyncio 1.4.0

**Commit SHA：** `d03ac6c`（完整：`d03ac6c...`）
**Push 状态：** ✅ 已推送至 origin/main
**本轮 Tag：** 无（本轮不创建 Tag）

---

## [M0.1] — 2026-07-31

### 仓库初始化与文档基线

**新增：**
- 识别并保留原始 PRD（`PRD.md`）
- 创建 `PROJECT_CHARTER.md` — 项目北极星文件
- 创建 `CLAUDE.md` — 开发协议、冷启动协议、Commit/Tag 规则
- 创建 `README.md` — 项目说明和环境准备指南
- 创建 `CHANGELOG.md` — 本文件
- 创建 `.gitignore` — 覆盖敏感文件和本地产物
- 创建 `.env.example` — 环境配置模板
- 创建 `environment.yml` — Conda 环境配置（PBIAgent, Python 3.11）
- 创建 `pyproject.toml` — Python 项目配置
- 创建 `docs/00_product_requirements_document.md` — 正式 PRD
- 创建 `docs/01_product_scope_and_frontend_skeleton.md` — 产品范围与前端骨架
- 创建 `docs/02_technology_selection_and_system_architecture.md` — 技术选型骨架
- 创建 `docs/03_intent_recognition_and_memory_system.md` — 意图识别与记忆骨架
- 创建 `docs/04_powerbi_mcp_and_api_contracts.md` — Power BI MCP 骨架
- 创建 `docs/05_harness_test_and_acceptance.md` — Harness 骨架
- 创建 `docs/06_security_git_and_development_standards.md` — 安全与开发规范
- 创建 `docs/07_milestones_status_and_open_questions.md` — 里程碑状态
- 创建 `docs/08_development_roadmap.md` — 开发路线
- 创建 `docs/09_context_handoff.md` — 跨对话交接
- 创建 `docs/adr/README.md` — ADR 目录说明
- 创建 `frontend/README.md` — 前端占位说明
- 初始化 Git 仓库，配置远程 `origin`
- 创建 `PBIAgent` Conda 环境（Python 3.11.15）

**Conda 环境：**
- Conda 版本：26.5.3
- Conda 路径：`D:\Conda\Scripts\conda.exe`
- 环境名称：`PBIAgent`
- 环境路径：`D:\Conda\envs\PBIAgent`
- Python 版本：3.11.15

**Commit SHA：** `eb5812d`（完整：`eb5812dfa9a76bcbb8505c31e1b8f24b67afadf0`）
**Push 状态：** ✅ 已推送至 origin/main
**本轮 Tag：** 无（本轮不创建 Tag）

---

## 图例

- `[Mx.y]` — M0 开发准备轮次
- `[Mx]` — MVP 功能轮次
