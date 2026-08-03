# CHANGELOG

## [M1.3] — 2026-08-03

### 真实 QueryPlan 与 DAX 生成

**来源：** M1.3 开发轮次。

**M1.2 审计收口（三项）：**
- `from_committed_memory()` state_status 检查：committed 继承、pending/failed/缺失不继承
- 无效 Prompt 测试修复：`test_prompt_forbids_dax_and_answer` 永真断言修正
- 验证错误脱敏：IntentRecognitionError 不再拼接 `str(LLMValidationError)`

**DeepSeekQueryPlanService：**
- `backend/app/query_plan/deepseek_service.py` — 复用 DeepSeekLLMProvider
- `backend/app/query_plan/prompt.py` — 集中式 QueryPlan 提示词
- `backend/app/query_plan/context.py` — Schema 安全精简视图
- 只处理 data_question/report_generation；clarification/unsupported 明确拒绝
- Prompt：严格 JSON、只用 Schema 真实字段、不生成 DAX/答案、不调用工具、不虚构
- 最多一次格式修复（仅 JSON/Schema 错误可修复）
- 复用现有 QueryPlan Pydantic 模型和 ValidationService

**DeepSeekDAXService：**
- `backend/app/dax/deepseek_service.py` — 复用 DeepSeekLLMProvider
- `backend/app/dax/prompt.py` — 集中式 DAX 提示词
- `backend/app/dax/safety.py` — DAX 只读安全验证器
- Prompt：只生成一个只读 EVALUATE DAX、只用 Schema 对象、不生成 SQL/脚本/答案
- DAX 安全验证：禁止写入/删除/更新、SQL/Shell/Python/JS、多语句注入、注释绕过、非法对象、空 DAX、超长/超复杂
- 允许：EVALUATE、SUMMARIZECOLUMNS、FILTER、TOPN、ORDER BY、DEFINE MEASURE、VAR、RETURN
- 验证结果结构化：is_valid、errors、warnings、referenced_objects
- 最多一次修复（同 M1.2 规则）

**API 与 Health 边界：**
- Mock：200，ready=true，version=M1.3
- DeepSeek 无 Key：503，deepseek_api_key_missing
- DeepSeek 有 Key：503，deepseek_pipeline_not_ready
- Health 不访问网络
- Chat DeepSeek 模式仍 503

**测试结果：**
- pytest：675 passed（M1.2 604 + M1.3 新 126 - 版本号更新 5）
- Golden Cases：11 passed，1 skipped
- 安全扫描：PASS
- 真实 Smoke：分离入口 `python -m backend.app.query_plan.deepseek_query_dax_smoke`

**Commit SHA：** 待提交
**本轮 Tag：** 无

---

## [M1.2] — 2026-08-03

### 真实意图识别

**来源：** M1.2 开发轮次。

**M1.1 审计收口（四项）：**
- 网络异常分类补齐：ReadError/WriteError/CloseError/RemoteProtocolError → LLMConnectionError (retryable=true)；LocalProtocolError → LLMRequestError (retryable=false)；均携带安全 error_code
- 响应结构防御强化：`_parse_response()` 增加 14 层严格验证
- 安全扫描豁免收紧：TEST_SAFE_MARKERS 仅在 `backend/tests/` 生效；Python 变量引用全局豁免
- M1.1 SHA 文档修正：`docs/09` 和 `CHANGELOG.md` 写入 `073a819`

**DeepSeekIntentService：**
- `backend/app/intent/deepseek_service.py` — 复用 DeepSeekLLMProvider
- `provider.is_mock=True` 时明确失败，禁止 Mock 回退
- 支持四类意图：data_question / report_generation / clarification / unsupported
- 最多一次格式修复（仅 JSON/Schema 错误可修复）
- 不保存请求级状态，支持并发

**IntentContextSnapshot：**
- `backend/app/intent/context.py` — 白名单上下文提取（extra="forbid", frozen=True）
- 从 committed memory 提取安全字段子集

**Prompt：**
- `backend/app/intent/prompt.py` — 集中式 Prompt 构造
- 12 条系统规则、四类意图定义、修复指令、上下文渲染

**IntentSpec 严格化：**
- IntentSpec 和 FilterSpec 增加 `extra="forbid"`
- 字符串清理、列表去空去重、跨字段规则、第五类意图拒绝

**真实 Intent Smoke：**
- `backend/app/intent/deepseek_intent_smoke.py` — 5 个合成案例
- 脱敏输出（仅含 case_id、expected、actual、confidence、tokens 等）

**测试结果：**
- pytest：604 passed（M1.1 506 + M1.2 新增 98）
- Golden Cases：11 passed，1 skipped
- 安全扫描：PASS

**Commit SHA：** 待提交
**本轮 Tag：** 无（本轮不创建 Tag）

---

## [M1.1] — 2026-08-03

### DeepSeek Provider基础接入

**来源：** M1.1 开发轮次。

**DeepSeekLLMProvider 实现：**
- `backend/app/llm/deepseek.py` — 完整实现，支持独立调用
- 构造时校验 Key/Base URL/Model，空值明确失败
- URL 拼接正确去除末尾 `/`，不产生重复 `//`
- 请求：messages、stream=false、temperature=0、response_format=json_object
- 响应解析：choices[0].message.content → json.loads() → model_validate()
- 无自动重试、无 Markdown 去除、无 JSON 自动修复（留待 M1.2）

**LLM 异常契约（10 种）：**
- LLMConfigurationError、LLMAuthenticationError、LLMRateLimitError
- LLMConnectionError、LLMRequestError、LLMServiceError
- LLMResponseError、LLMTimeoutError、LLMValidationError、LLMProviderError
- 错误映射：HTTP 401/403 → Authentication、429 → RateLimit、5xx → Service 等
- LLMProviderError 可安全携带 provider/retryable/status_code/error_code

**Provider Factory 与 Registry：**
- `backend/app/llm/factory.py` — build_llm_registry() 统一创建入口
- Mock 模式：仅注册 MockLLMProvider
- DeepSeek 模式：Mock + DeepSeek 同时注册，默认 deepseek
- 每个 Factory 调用返回独立 Registry 实例

**Settings 更新：**
- 版本 M1.1
- `is_deepseek_configured` 属性（不访问网络，不泄露 Key 信息）
- `safe_repr()` 增加 `deepseek_configured` 字段

**Health 与 Chat 边界：**
- DeepSeek 无 Key：Health 503, `deepseek_api_key_missing`
- DeepSeek 有 Key：Health 503, `deepseek_pipeline_not_ready`
- Chat DeepSeek 模式：503，不回退 Mock

**历史审计收口：**
- docs/09：写入 M1.0.1 `c223d7b`、M1.0.2 `5726959`、pytest 415 passed
- CHANGELOG：删除所有"由 Git 解析"和"待推送"占位符
- ScenarioFingerprint：独立 Pydantic 模型替代 `Optional[Any]`
- IdempotencyCoordinationError：Owner/Waiter 协调失败 → HTTP 503
- 安全扫描器：不再整体排除 backend/tests 和 scripts
- httpx==0.28.1 提升为运行依赖

**真实连通测试：**
- `backend/app/llm/deepseek_smoke.py` — 最小合成请求
- 通过：success=True, model=deepseek-v4-flash, 70 tokens
- 安全输出仅含脱敏字段

**测试结果：**
- pytest：506 passed
- Golden Cases：11 passed，1 skipped
- 安全扫描：PASS

**Commit SHA：** `073a819`
**本轮 Tag：** 无（本轮不创建 Tag）

---

## [M1.0.2] — 2026-07-31

### 密钥与仓库安全规则固化

**来源：** 用户批准的 M1.0.2 专项安全修复轮次。

**Secret 与 API Key 安全规则固化：**
- `CLAUDE.md`：新增「Secret 与 API Key 绝对规则」章节（6 条子规则）
  - Secret 永不进入仓库、Claude 不得读取 .env、API Key 仅后端使用
  - 前端禁止持有 Provider Secret、日志与测试禁止泄漏
  - 提交前安全检查（禁止 `git add .`/`git add -A`，必须文件白名单）
- Commit 规则：提交前检查清单更新为 10 项（新增文件白名单和安全扫描步骤）

**docs/06 安全规范同步：**
- 新增 1.1—1.6 节：Secret 文件规则、Claude 禁止读取 .env、后端 Key 规则、前端禁止 Secret、日志安全、API Key 填写规则
- 提交前检查清单更新

**.env.example 清理：**
- 所有 Secret 值改为空值（DeepSeek Key、Client Secret 等均设为空，无占位示例值）
- 默认 `LLM_MODE=mock`、`POWERBI_MODE=mock`
- 移除所有疑似真实 Key 格式的示例值
- 本地 `.env` 从模板创建，已被 `.gitignore` 忽略且未跟踪

**.gitignore 加强：**
- 新增敏感产物忽略：`*.har`、`http_dumps/`、`network_capture/`、`debug_responses/`、`smoke_outputs/`、`secret_scan_output/`
- 新增本地 Secret 备份忽略：`.env.backup`、`.env.bak`、`.env.old`、`credentials/`、`private_credentials/`

**仓库安全检查：**
- 新增 `scripts/check_repository_safety.py`：检查禁止跟踪文件名、前端 Secret、明显真实 Secret
- 新增 `backend/tests/unit/test_repository_safety.py`：26 个测试覆盖
- 提交前必须执行安全检查脚本

**README：**
- 新增 `.env` 创建和安全说明
- 新增仓库安全检查命令

**文档更新：**
- `docs/08`：新增 M1.0.2 专项修复记录
- `docs/09`：交接文档更新为 M1.0.2 完成状态
- 本轮不改变 M1.0—M1.5 六轮主路线
- 本轮不接入 DeepSeek，不开发 Provider 代码

**测试结果：**
- 安全扫描通过
- 26 个安全测试全部通过
- 待全量 pytest 和 Golden Cases 验证

**Commit SHA：** `5726959`
**本轮 Tag：** 无（本轮不创建 Tag）

---

## [M1.0.1] — 2026-07-31

### 幂等并发与文档收尾修复

**来源：** M1.0 审计发现 5 项问题。

**修复1：请求指纹与冲突检测**
- 新增 `RequestFingerprint` Pydantic 模型（`backend/app/memory/request_fingerprint.py`）
- 使用 Canonical JSON + SHA-256 生成稳定指纹 Hash
- 相同 `request_id` 不同指纹 → `IdempotencyConflictError` → API 返回 HTTP 409
- message 仅首尾空白清理；client_conversation_id 保留客户端原始值
- 不将原始 message 或完整请求内容写入日志和 Trace

**修复2：并发 Owner/Waiter 防重**
- `IdempotencyTracker` 集成到 `ResultSnapshotStore`（claim/complete/abort）
- 使用 `asyncio.Lock` 保护 in-flight 字典，锁只用于领取执行权
- 相同指纹并发：一个 Owner 执行，其余 Waiter 等待重放
- 不同指纹并发：立即返回冲突
- Owner 异常时清理 in-flight 并唤醒 Waiter

**修复3：Report 快照结构化**
- 新增 `ReportResultSnapshot` Pydantic 模型（report_id/template_key/html 必填）
- `TurnResultSnapshot.report` 类型从 `Optional[dict]` 改为 `Optional[ReportResultSnapshot]`
- 快照保存时 Pydantic 校验，非法 report 不能进入 Store
- 跨字段校验：response_type 与对应数据一致性
- 快照包含 `request_fingerprint_hash` 字段

**修复4：Service 统一 UUID 生成**
- `MockTurnService.execute()` 签名改为 `conversation_id: str | None = None`
- 未传时 Service 内部生成 UUID，不依赖路由层
- 指纹使用客户端原始值，不使用服务端生成的 UUID

**修复5：文档状态收尾**
- `docs/08`：M1.0 → 已完成，新增 M1.0.1 专项修复记录
- `docs/09`：当前轮次 M1.0.1，下一轮 M1.1
- README 补充：幂等重放、HTTP 409 冲突、单进程限制说明
- 不再保留"进行中、待推送、由下一轮获取"等失效状态

**测试结果：**
- pytest 全部通过
- Golden Cases：11/11 mock_ready 通过，1 skipped
- compileall 通过 | pip check 通过

**Commit SHA：** `c223d7b`
**本轮 Tag：** 无（本轮不创建 Tag）

---

## [M1.0] — 2026-07-31

### M0遗留收口与M1路线固化

**来源：** M0.4.1 审计遗留问题修复 + M1 路线规划。

**修复1：clarification/unsupported 保留 conversation_id**
- `_build_result()` 新增显式 `conversation_id` 参数
- clarification/unsupported 路径传入当前 conversation_id，不再依赖 Memory 是否存在
- 用户未提供 conversation_id 时服务端自动生成（FastAPI 路由层）
- Service 直接调用和 FastAPI 调用均成立

**修复2：request_id 幂等重放**
- 新增 `TurnResultSnapshot` Pydantic 模型 + `ResultSnapshotStore`（`backend/app/memory/result_snapshot.py`）
- 首次请求保存完整响应快照（Answer/Report/clarification/unsupported/失败）
- 重复请求返回：terminal_state="duplicate"、tool_sequence=[]、memory_commit=false、新 trace_id
- `ChatResponse` 新增 `idempotent_replay: bool` 和 `replayed_request_id: Optional[str]`
- 快照检查优先于 Memory 检查，覆盖无 Memory 的 clarification/unsupported 幂等

**修复3：默认报表模板 sales_weekly**
- `MockScenarioResolver.resolve()` 返回 `MockScenarioResolution`（含 `effective_report_template_key`）
- 默认报表模板固定为 `sales_weekly`
- 客户端显式传入合法模板时优先使用客户端模板
- `report_template_key` 贯穿：Context → ReportSpec → RenderedReport → Memory → API 响应
- `memory.report_template_key` 在成功报表请求中不为 None

**修复4：版本号和安装说明**
- Settings.version → `M1.0`；Health 返回 `version: "M1.0"`
- README：新增 `pip install -e ".[dev]"` 开发依赖安装说明
- README Health 示例增加 `ready`/`reasons` 字段
- README Chat 示例与当前真实响应契约一致

**M1.0—M1.5 路线固化：**
- `docs/08_development_roadmap.md` 写入完整六轮路线（M1.0→M1.5）
- 路线执行规则：顺序执行、未验收不进入下一轮、不允许跨轮
- `docs/08` 是路线唯一权威来源；`CLAUDE.md` 不重复粘贴完整路线

**测试结果：**
- 327 个 pytest 全部通过（原 285 + 42 新增/重写）
- Golden Cases：11/11 mock_ready 通过，1 skipped
- compileall 通过 | pip check 通过
- 新增 `backend/tests/integration/test_m1_fixes.py`（30 个 M1.0 专项测试）

**Commit SHA：** `9247322`
**本轮 Tag：** 无（本轮不创建 Tag）

---

## [M0.4.1] — 2026-07-31

**来源：** M0.4 审计发现 5 项 API 骨架真实性问题。

**修复1：依赖可复现**
- `pyproject.toml`：新增 fastapi==0.141.1、uvicorn[standard]==0.52.0、pydantic-settings==2.14.2 为运行时依赖；新增 httpx==0.28.1 为测试依赖
- `environment.yml`：启用 `-e .` 安装，移除"尚未验证"标注
- `README.md`：标注版本已锁定
- `pip install -e .` + `pip check` 验证通过

**修复2：公开API真实意图流**
- 新增 `backend/app/application/mock_scenario_resolver.py` — MockScenarioResolver
- 根据用户 message + report_template_key 推断 Mock 场景（支持 data_question/report_generation/clarification/unsupported）
- API 路由不再构造 MockScenarioSelection
- 路由只负责校验请求、生成 ID、调用 Service、转换响应
- 客户端不可传 Scenario Key（extra="forbid" 仍然生效）
- Golden Cases 仍可显式传 Scenario

**修复3：返回真实Answer和Report**
- `MockTurnService._build_result()` 保存实际 AnswerSpec.answer 和 RenderedReport 数据
- `last_result_summary` 仅作为 Memory 摘要保留，不再替代 API 响应
- ChatResponse 新增结构化 ReportResponse（report_id/template_key/html）
- clarification 返回 clarification_question；unsupported 返回 unsupported_reason

**修复4：Health真实性**
- HealthResponse 新增 `ready`（bool）和 `reasons`（list[str]）
- Mock 模式：200、status="ok"、ready=true
- DeepSeek 模式：503、status="not_ready"、ready=false、reason="deepseek_not_implemented"
- Remote MCP 模式：503、status="not_ready"、ready=false、reason="powerbi_remote_mcp_not_implemented"
- 使用 `response.status_code` 正确设置 HTTP 状态码
- Health 不调用 LLM 或 Power BI 网络
- Health 响应不含 Secret

**修复5：app.state与真实lifespan**
- 删除模块级全局 `_mock_turn_service` 和 `set_mock_turn_service()`
- `app.state.settings` 和 `app.state.mock_turn_service` 在 lifespan 中初始化
- `get_mock_turn_service(request)` 从 `request.app.state` 读取
- `get_settings_dep(request)` 从 `request.app.state` 读取（不使用全局缓存）
- `create_app(settings=...)` 支持测试注入自定义 Settings
- 多个 app 实例互不覆盖 state
- lifespan 退出后 state 清理
- 测试通过真实 lifespan 初始化（`app.router.lifespan_context(app)` + `ASGITransport`）

**测试结果：**
- 285 个 pytest 全部通过（原 265 + 20 新增/重写）
- Golden Cases：11/11 mock_ready 通过，1 skipped
- compileall 通过
- pip check 通过
- Uvicorn 启动验证：Health Mock 200、数据问答返回真实 answer、报表返回 HTML、unsupported 真实可达

**Commit SHA：** `1f967b0`
**本轮 Tag：** `m0.4.1-foundation-release`（M0.4.1 封板）

---

## [M0.4] — 2026-07-31

### 项目骨架与阶段收尾

**来源：** M0 开发准备最后一轮 — 请求级并发收口 + FastAPI 骨架 + M0 全量验收。

**阶段A：请求级并发上下文收口**

根因：`MockTurnService._trace`、`ToolGateway._trace_recorder`、`ToolGateway._turn_controller` 为共享实例字段，同一 Service/Gateway 实例并发时后到达请求覆盖前一个请求的 Trace/Controller/工具计数。

修复：
- **删除** `ToolGateway._trace_recorder` 和 `ToolGateway._turn_controller` 实例字段
- **删除** `ToolGateway.set_trace_recorder()` 和 `ToolGateway.set_turn_controller()` 方法
- **删除** `MockTurnService._trace` 实例字段
- `ToolGateway.execute()` 改为显式接收 `trace` 和 `controller` 参数
- `MockTurnService._build_result()` 改为显式接收 `trace` 参数
- `MockTurnService._fail_turn()` 不再静默吞掉 `TurnStateError`，意外非法转换记录 Trace 后重新抛出
- ToolGateway 保持为无请求状态、可安全复用

**新增并发测试（6 个）：**
- `TestSameServiceFullToolChainConcurrent`：同一 Service 并发 data_question vs report_generation + 循环稳定性 + 工具计数独立
- `TestSameServiceFailAndSuccessConcurrent`：同一 Service 并发失败+成功 + 工具序列不污染 + 失败不阻塞成功 commit

**阶段B：FastAPI 最小骨架**

- **Settings** (`backend/app/config/settings.py`)：Pydantic Settings，环境变量可覆盖，Mock 模式无需 API Key，不打印 Secret，Real 模式未实现时 `is_real_ready=False`
- **FastAPI 应用** (`backend/app/main.py`)：`create_app()` + lifespan 管理 MockTurnService
- **Health 接口** (`GET /health`)：返回结构化状态，不含 Secret，不调用 LLM/Power BI
- **Chat 接口** (`POST /api/v1/chat`)：非流式对话，Pydantic 请求/响应，message 非空校验，extra="forbid"，Real 模式返回 503

**API 测试（26 个）：**
- `test_settings.py`：默认 Mock、环境变量覆盖、非法模式拒绝、Secret 不泄露、Real 模式未 ready、缓存隔离
- `test_health.py`：200 OK、模式正确、无敏感字段、不调用 LLM
- `test_chat.py`：数据问答、报表生成、空消息 422、幂等、clarification、结构完整性、Real 模式 503、额外字段 422、并发 data vs report + 不串场

**测试结果：**
- 265 个 pytest 全部通过（219 + 26 API + 20 Settings/Health/Chat 新增）
- Golden Cases：11/11 mock_ready 通过，1 skipped (pending_real_baseline)
- compileall 通过
- Uvicorn 启动验证：/health 返回 200，/api/v1/chat 数据问答和报表均成功

**Commit SHA：** `d5c1634`
**本轮 Tag：** `m0.4-foundation-release`（M0 封板，本 Prompt 已批准）

---

## [M0.3.3] — 2026-07-31

### Mock场景并发隔离修复

**来源：** M0.3.2 审计发现共享 `_active_scenario` 状态在并发请求下可能串场。

**根因：**
- `MockAgentRuntime.set_scenario()` 将 scenario_key 写入共享的 `MockLLMProvider._active_scenario`
- 同一 Runtime/Provider 实例并发处理不同 Scenario 时，后到达的请求覆盖先到达请求的 Scenario
- 虽然 M0.3.2 删除了 Runtime 的 `_scenario_key`，但通过 LLM Provider 的 `_active_scenario` 仍存在共享状态
- 无 async delay 时请求顺序执行掩盖了问题，但本质上并发不安全

**修复方案：**
- 删除 `MockLLMProvider._active_scenario` 实例字段
- 删除 `MockAgentRuntime.set_scenario()` 方法
- Scenario Key 仅通过 `context["mock_scenario_key"]` 在 `run()` 调用时局部传入
- `MockAgentRuntime.run()` 从 `context.get("mock_scenario_key")` 读取，不使用任何共享状态
- `MockTurnService.execute()` 在每次 `run()` 前设置 `context["mock_scenario_key"]`

**删除的共享状态：**
- `MockLLMProvider._active_scenario: str`（源码第 51 行）
- `MockAgentRuntime.set_scenario()` 方法（源码第 30-37 行）
- `MockAgentRuntime.run()` 中的 `getattr(self._llm, "_active_scenario", ...)` 读取

**新增并发测试（8 个）：**
- `TestSameRuntimeConcurrent`：同一 Runtime + 不同 Service，data_question vs report_generation + 10 次循环
- `TestSameServiceConcurrent`：同一 Service，data_question vs unsupported + data_question vs report(共享Runtime) + 10 次循环
- `TestForcedInterleaving`：scenario_delay 强制异步交错 + 10 次循环 + 共享Runtime report交错

**兼容性确认：**
- 五类 Scenario Key 正常
- Golden Cases 全部通过（11/11 mock_ready）
- 多轮 Memory 继承正常
- ToolGateway 调用链正常
- request_id 幂等正常
- Mock Fixture 路径不变
- 未知 Scenario 仍明确失败

**测试结果：**
- 213 个 pytest 全部通过（原 205 + 8 新增）
- Golden Cases：11/11 mock_ready 通过，1 skipped
- compileall 通过

**Commit SHA：** `d0d47e3`
**Push 状态：** ✅ 已推送至 origin/main
**本轮 Tag：** 无（本轮不创建 Tag）

---

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

**Commit SHA：** `ec1afcc`
**Push 状态：** ✅ 已推送至 origin/main
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
