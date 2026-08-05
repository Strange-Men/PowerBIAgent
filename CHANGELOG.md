# CHANGELOG

## [M1.6.5] — 2026-08-05

### 阶段A：路线修订与治理基线

**来源：** M1.6.5 真实测试、机器错题本与架构防偏移治理 — 阶段A。

#### GOV-165-001：路线修订

- `docs/08_development_roadmap.md`：M1.6.4 状态改为 ✅ 已完成、Commit 补充为 `4217b66`
- M1.6.5 路线改为「真实测试、机器错题本与架构防偏移治理」
- 新增 M1.6.6「CI、最终审计、真实Smoke与封板」
- 明确 M1.6.5 不创建 Tag、不封板；M1.6.6 创建 M1.6 最终 Tag
- `docs/09_context_handoff.md`：M1.6.4 记录补充 Commit `4217b66`、入已完成版本表
- 当前阶段更新为 M1.6.5、下一轮更新为 M1.6.6
- 明确 M1.6.5 和 M1.6.6 职责边界
- "上一轮"修正为 M1.6.4（原误写 M1.6.3.1）

#### GOV-165-002：错题本空壳与冷启动入口

- 新增 `docs/ai_development_error_ledger.yaml`：正式机器错题总账
  - Schema 版本 1.0、状态枚举、必填字段定义
  - entries 为空列表，阶段B迁移历史错误
- `CLAUDE.md` 冷启动协议更新：
  - 必须阅读文件新增：`docs/adr/README.md` 及 ADR、`docs/ai_development_error_ledger.yaml`
  - 新增「防偏移检查」步骤（命中错误ID、ADR限制、可能偏移、禁止边界）
  - 新增阻塞条件：无法读取错题本或格式错误时禁止开发

**修改文件清单（5个）：**
- `docs/08_development_roadmap.md`
- `docs/09_context_handoff.md`
- `CLAUDE.md`
- `docs/ai_development_error_ledger.yaml`
- `CHANGELOG.md`

**本轮 Tag：** 无

---

## [M1.6.4] — 2026-08-05

### 架构稳定性、AI真实性、异常边界与对抗测试加固

**来源：** M1.6.4 架构稳定性、AI真实性、异常边界与对抗测试加固。

**本轮不是功能开发轮。**

#### ARCH-164-001：Service 不再暴露可写 Memory Repository

- MockTurnService 和 DeepSeekTurnService 移除 `memory_repo` @property
- 只读验证使用 TurnPipeline 只读方法：
  `request_exists_in_memory()` / `get_memory_by_request_id()` / `get_latest_committed_memory()`
- TurnPipeline 新增 `get_latest_committed_memory()` 只读查询方法
- Service 源码不含 `def memory_repo`、`self.memory_repo`、`pipeline.memory_repo`

#### ERR-164-001：API 错误映射收口

- HTTP 402 余额不足独立映射为 `deepseek_insufficient_balance`（不再伪装为 `deepseek_api_key_missing`）
- LLMConfigurationError 根据 error_code 区分：`api_key_missing` / `insufficient_balance` / `invalid_base_url` / `invalid_model`
- 补齐显式映射：LLMRequestError → 502 `deepseek_request_error`、LLMResponseError → 502 `deepseek_response_error`、LLMValidationError → 502 `deepseek_validation_error`
- 新增 LLMProviderError 兜底处理器，已知 Provider 异常不再落入通用 500 `internal_error`
- API 错误响应不泄漏 API Key、Authorization Header、完整 Prompt、模型响应、网络 Body、内部堆栈
- 保持公开响应基本结构不变

#### ERR-164-002：HTTPX 异常分类细化

基于 HTTPX 官方文档完善异常分类：
- `ConnectTimeout` → `connect_timeout`
- `ReadTimeout` → `read_timeout`
- `WriteTimeout` → `write_timeout`
- `PoolTimeout` → `pool_timeout`
- `TimeoutException` 兜底 → `unknown_timeout`
- 保留 `ConnectError/ReadError/WriteError/CloseError/RemoteProtocolError/LocalProtocolError` 现有 error_code

#### DOC-164-001：版本与文档同步

- Settings.version → `M1.6.4`
- README 移除 PydanticAI 作为当前依赖/Agent 架构的描述，更新当前状态至 M1.6.4
- 健康检查示例版本同步 → `M1.6.4`
- docs/09 M1.6.3.2 Commit SHA 回填为 `d57e38c`
- docs/09 记录 M1.6.3.2 真实 DeepSeek Chat Smoke：overall_success=true、6 案例通过、source_mode=mock 当前设计、estimated_cost_usd=null 未配置价格
- docs/08 状态更新至 M1.6.4

#### TRUTH-164-001 & TRUTH-164-002：AI 真实性门禁

- 增强 ValidationService 数值一致性验证（优先增强现有服务，未另建重复框架）
- KPI bool/None/str 数值拒绝、虚构值拒绝、列不存在拒绝
- 空 QueryResult 不得返回 KPI/Chart/Table
- Table 类型严格比较（int≠str、bool≠int）
- Answer evidence 强制绑定校验、metrics 可追溯校验、semantic_model_key 一致性校验
- 模型输出冲突时拒绝而非猜测修正

#### ADV-164-001 & ADV-164-002：最小对抗测试

输入/Prompt 注入覆盖：
- 忽略系统规则、输出 API Key/环境变量/Prompt、绕过 ToolGateway、调用未注册工具、
  将 Mock 说成真实数据、空字符串、纯空白、大量 emoji、null 字节、XSS、重复注入、伪造 JSON
- 不泄漏 Secret、不改变工具白名单、不绕开 ToolGateway、不改变 runtime_mode

DAX 边界覆盖：
- 多语句 DROP/DELETE/INSERT/UPDATE/CREATE、注释隐藏（`--`、`/**/`、`//`）、
  SQL 语法、Shell shebang、Python exec/eval、不存在表/列、跨表错误引用
- 正常 DAX 仍通过（FILTER/SUMMARIZE）
- 仅增强现有 DAXSafetyValidator，未重写 DAX 生成体系

**新增测试：** 84 个（test_m164_arch_truth_adv.py）

**最终验收结果：**
- pytest：1070 passed（986 现有 + 84 M1.6.4 新增）
- Golden Cases：11 passed，1 skipped（gc_012_real_baseline 等待 M2）
- 安全扫描：PASS
- 真实 LLM 调用次数：0
- Service 公开 memory_repo 属性：0
- Service 直接 memory_repo 写入：0
- Service 直接 Snapshot 写入：0
- Service 源码 pipeline.memory_repo：0
- PydanticAI 生产依赖：0
- AgentRuntime 有效残留：0（仅注释/文档字符串）
- DeepSeek 直接 Adapter 调用：0
- 测试中真实 api.deepseek.com 网络访问：0
- 无限重试：0
- 每个问题修复次数：≤2

**修改文件清单（12 个）：**
- `backend/app/config/settings.py` — version → M1.6.4
- `backend/app/application/mock_turn_service.py` — 移除 memory_repo @property
- `backend/app/application/deepseek_turn_service.py` — 移除 memory_repo @property
- `backend/app/application/turn_pipeline.py` — 新增 get_latest_committed_memory()
- `backend/app/llm/deepseek.py` — HTTPX timeout 细化、LLMConfigurationError error_code
- `backend/app/api/routes.py` — 错误映射补全、LLMProviderError 兜底
- `backend/app/harness/cases/case_runner.py` — memory_repo → pipeline.memory_repo
- `backend/tests/unit/test_m164_arch_truth_adv.py` — 新增（84 个测试）
- `backend/tests/api/test_health.py` — version 断言同步
- `backend/tests/api/test_chat.py` — version 断言同步
- `backend/tests/unit/test_settings.py` — version 断言同步
- `backend/tests/integration/test_m1_fixes.py` — version 断言同步、memory_repo → pipeline
- `backend/tests/integration/test_mock_pipeline.py` — memory_repo → pipeline
- `backend/tests/integration/test_m1_2_intent_isolation.py` — version 断言同步
- `README.md` — PydanticAI 移除、状态更新、版本示例同步
- `docs/08_development_roadmap.md` — 状态更新、SHA 回填
- `docs/09_context_handoff.md` — SHA 回填、Smoke 记录、状态更新
- `CHANGELOG.md` — 本轮记录

**本轮 Tag：** 无

**留给 M1.6.5 的人工 Smoke 命令：**
```
D:\Conda\envs\PBIAgent\python.exe -m backend.app.application.deepseek_chat_smoke
```

---

## [M1.6.3.2] — 2026-08-05

### 事务边界与单写入者彻底收口

**来源：** M1.6.3.2 事务边界、单写入者与证据驱动修复收口。

**架构问题发现：**

- **TX-001** Service 直接写 Memory：两个 Service 的 `_do_execute` 中仍直接调用 `self.memory_repo.mark_failed()` 和 `self.memory_repo.commit()`，而非通过 TurnPipeline 统一事务协调
- **TX-002** Snapshot 双重写入：DeepSeekTurnService 成功路径中 `_do_execute` 内部调用 `_save_snapshot()` 后再由 TurnPipeline.execute() 二次保存
- **TX-003** Service 与 Pipeline 事务边界不清：Service 持有 `self.memory_repo`、`self.snapshot_store` 实例字段，自行管理提交、失败标记和快照生命周期

**整改内容：**

**Memory 写入统一（TX-001）：**
- `DeepSeekTurnService` 4 处 `self.memory_repo.mark_failed()`/`self.memory_repo.commit()` → `self.pipeline.mark_memory_failed()`/`self.pipeline.commit_memory_safe()`
- `MockTurnService` 3 处同类直接调用 → 统一委托 TurnPipeline
- 两个 Service 移除 `self.memory_repo` 实例字段，仅通过 `self.pipeline` 访问
- TurnPipeline 新增只读查询方法：`request_exists_in_memory()`、`get_memory_by_request_id()`

**Snapshot 单写入者（TX-002）：**
- 移除 `DeepSeekTurnService._do_execute()` 中的 `_save_snapshot()` 调用（双写消除）
- 移除两个 Service 的 `self.snapshot_store` 实例字段
- SnapshotStore 完全由 TurnPipeline 持有和调用
- TurnPipeline.execute() 成功时保存快照 + complete，异常时 abort

**错误分类完善（NET-001）：**
- `_classify_http_error()` 新增 402 Insufficient Balance 显式映射 + error_code 三值返回
- HTTP 状态错误现在携带 `error_code` 字段（基于 DeepSeek 官方文档 api-docs.deepseek.com/quick_start/error_codes）
- HTTPX 异常分类与官方文档一致（python-httpx.org/exceptions）

**机器错题本：**

| 问题ID | 问题现象 | 本地证据 | 外部权威资料 | 根因 | 修复 | 回归测试 | 状态 |
|--------|---------|---------|------------|------|------|---------|------|
| TX-001 | Service 直接写 Memory | deepseek_turn_service.py:463,529,570,641; mock_turn_service.py:498,520,597 | — 架构原则 | M1.6.3 未完全收口直接写 | 全部替换为 TurnPipeline 方法 | 19 个 M1.6.3.2 测试 | ✅ |
| TX-002 | Snapshot 双重写入 | deepseek_turn_service.py:613 + turn_pipeline.py:205 | — 架构原则 | Service 成功路径自行保存后再由 Pipeline 二次保存 | 移除 Service 内 `_save_snapshot()` | test_successful_owner_saves_snapshot_exactly_once | ✅ |
| TX-003 | Service 和 Pipeline 事务边界不清 | Service 各自持有 memory_repo/snapshot_store | — 架构原则 | 控制面未完全统一到 Pipeline | Service 移除实例字段，Pipeline 成为唯一写入者 | test_service_does_not_hold_self_memory_repo | ✅ |
| NET-001 | HTTP 错误缺 error_code | _classify_http_error 返回 2 值无 error_code | DeepSeek API Docs (api-docs.deepseek.com), HTTPX Docs (python-httpx.org) | 错误分类未携带结构化 error_code | 新增 error_code + 402 显式映射 | 全量 986 passed | ✅ |
| GOV-001 | 无证据规则 | CLAUDE.md 无修复证据门禁 | — | 历史开发协议未包含 | CLAUDE.md 新增「外部证据修复门禁」 | 文档规则已固化 | ✅ |
| GOV-002 | 无修复上限 | CLAUDE.md 无两次修复上限 | — | 历史开发协议未包含 | CLAUDE.md 新增「两次修复上限」 | 文档规则已固化 | ✅ |

**防回归测试新增（19 个）：**
- 源码静态门禁（10 个）：禁止 `self.memory_repo.mark_failed/commit/create_pending`、`self.snapshot_store.*`、`_save_snapshot(`、`pipeline._save_snapshot(`、`self.memory_repo =`
- Snapshot 调用次数（4 个）：成功 1 次 save、幂等 0 次、异常 0 save + 1 abort、业务失败仍保存
- Memory 事务边界（3 个）：commit 由 commit_memory_safe 触发、失败标记由 pipeline 触发、版本冲突通过 pipeline
- 全仓静态搜索（2 个）：snapshot_store.save 仅 TurnPipeline、Service 使用 pipeline 方法

**最终验收结果：**
- pytest：986 passed（+19 M1.6.3.2 新增）
- Golden Cases：11 passed，1 skipped
- 安全扫描：PASS
- DeepSeek Smoke：（见下方 Smoke 执行记录）
- Service 直接 Memory 写入：0 处（Service 源码不含 `self.memory_repo.mark_failed/commit/create_pending`）
- Service Snapshot 写入：0 处（Service 源码不含 `snapshot_store.save/complete/abort`）
- SnapshotStore.save 生产调用者：仅 TurnPipeline
- PydanticAI 残留：0 | AgentRuntime 残留：0 | DeepSeek 直接 Adapter：0
- 新增无限重试：0 | 未经官方确认的模型名修改：0

**Service 与 TurnPipeline 最终职责边界：**

| 职责 | TurnPipeline | Service | 说明 |
|------|-------------|---------|------|
| ID 生成 | ✅ | — | conversation_id/request_id/trace_id |
| 请求指纹 | ✅ | — | SHA-256 + 冲突检测 |
| Owner/Waiter 协调 | ✅ | — | claim/complete/abort |
| TraceRecorder | ✅ | — | 创建与传递 |
| TurnController 生命周期 | ✅ | — | 创建、状态管理 |
| ContextBuilder | ✅ | — | 输入截断、Memory 状态检查 |
| ToolExecutionContext | ✅ | — | 统一工厂 |
| Memory 只读查询 | ✅ | — | request_exists_in_memory 等 |
| Memory create_pending | ✅ | — | 仅 Pipeline |
| Memory mark_failed | ✅ | — | 仅 Pipeline |
| Memory commit | ✅ | — | 仅 Pipeline（commit_memory_safe） |
| Snapshot save/complete/abort | ✅ | — | 仅 Pipeline |
| Intent 识别 | — | ✅ | LLM 结构化阶段 |
| QueryPlan 生成 | — | ✅ | LLM 结构化阶段 |
| DAX 生成与安全验证 | — | ✅ | LLM 结构化阶段 |
| Answer/ReportSpec 生成 | — | ✅ | LLM 结构化阶段 |
| ToolGateway 调用 | — | ✅ | 通过 Gateway |
| 业务数据验证 | — | ✅ | ValidationService |
| Memory 分析字段填充 | — | ✅ | 计算，不持久化 |

**修改文件清单（6 个）：**
- `CLAUDE.md` — 新增「外部证据修复门禁」和「两次修复上限」两节
- `backend/app/application/turn_pipeline.py` — 新增只读 Memory 查询方法
- `backend/app/application/deepseek_turn_service.py` — 移除直接 Memory/Snapshot 写入、移除实例字段
- `backend/app/application/mock_turn_service.py` — 移除直接 Memory/Snapshot 写入、移除实例字段
- `backend/app/llm/deepseek.py` — error_code 完善、402 显式映射
- `backend/tests/unit/test_m1632_transaction_boundary.py` — 新增（19 个测试）

**本轮 Tag：** 无

---

## [M1.6.3.1] — 2026-08-04

### 统一管线复验与彻底收口

**来源：** M1.6.3.1 复验与收口轮次。

**复验发现：**
- M1.6.3 CHANGELOG 宣称 TurnPipeline 统一了 TurnController、ContextBuilder、状态转换和 Memory 失败处理，但代码中这些职责仍在两个 Service 的 `_do_execute` 回调中各自复制
- 文档与代码状态不一致（CHANGELOG 写"已完成"但实际管线控制面未统一）
- M1.6.3 的 DeepSeek Smoke 在 `d6665bd` 时记录了 HTTP 500 失败（因上游 API 问题），后经实际运行证实通过
- 其余门禁项（pytest、Golden Cases、安全扫描、PydanticAI 残留、直接 Adapter 调用）实际上均已通过

**TurnPipeline 控制面扩展：**
- `TurnPipeline` 新增：`ContextBuilder`（构造时创建）、`create_tool_context()` 工厂、`create_pending_memory()`、`mark_memory_failed()`、`commit_memory_safe()`、`fail_controller_safe()`
- `TurnPipeline.execute()` 现统一创建 `TurnController` 并传递给 `do_execute` 回调
- `TurnPipeline.execute()` 现统一调用 `context_builder.build()` 并传递 context dict
- `TurnPipeline.execute()` 现统一加载 committed memory 并传递给回调

**两个 Service 简化：**
- `MockTurnService` 和 `DeepSeekTurnService` 均移除各自的 `ContextBuilder` 实例
- 两个 Service 的 `_do_execute` 不再直接构造 `ToolExecutionContext`（改用 `self.pipeline.create_tool_context()`）
- 两个 Service 的 Memory 失败标记统一委托给 `self.pipeline.mark_memory_failed()`
- 两个 Service 的 pending memory 创建统一委托给 `self.pipeline.create_pending_memory()`
- 移除未使用的导入（`ContextBuilder`、`ToolExecutionContext`、`UserContext`、`MemoryStatus`）

**防回归测试新增（7 个）：**
- `test_mock_service_no_own_context_builder` / `test_deepseek_service_no_own_context_builder`
- `test_turn_pipeline_creates_context_before_callback`
- `test_turn_pipeline_has_create_tool_context` / `test_turn_pipeline_has_mark_memory_failed`
- `test_both_services_have_no_own_tool_context_creation`
- `test_shared_turn_pipeline_has_commit_memory_safe`

**机器错题本：**

| 问题ID | 问题现象 | 根因 | 修复内容 | 回归测试 | 防复发门禁 | 状态 |
|--------|---------|------|---------|---------|-----------|------|
| E1 | M1.6.3 宣称 TurnPipeline 统一控制面但代码未实现 | CHANGELOG 写入时未逐项验证代码实际行为 | TurnPipeline 扩展为真正的控制面，ContextBuilder/TurnController/失败处理统一入口 | 7 个 M1.6.3.1 防回归测试 | 测试验证 service 不持有 context_builder | ✅ |
| E2 | 两个 Service 各自复制完整生命周期和通用失败处理 | `_do_execute` 回调中包含通用控制面逻辑（ContextBuilder、TurnController、ToolExecutionContext、Memory 失败标记），Mock 和 DeepSeek 各有一份 | 通用控制面移入 TurnPipeline，Service 只保留 LLM 阶段差异 | test_both_services_have_no_own_tool_context_creation | 源码检查：_do_execute 不含 ToolExecutionContext( 直接构造 | ✅ |
| E3 | M1.6.3 Smoke 记录为"未通过"但实际可通过 | `d6665bd` 时上游 API 临时问题导致 HTTP 500，该记录未回验 | M1.6.3.1 运行 2 次 Smoke，均 overall_success=true | Smoke 6/6 cases passed | 仅在有明确本地代码证据时修改，否则保持阻塞 | ✅ |
| E4 | 文档宣称的职责边界与代码实现不一致 | 文档更新时未对代码执行逐条验证 | 文档回写为真实状态，TurnPipeline 职责边界如实描述 | doc/code 一致性由复验流程保证 | 每轮结束前逐条验证文档断言 | ✅ |

**最终验收结果：**
- pytest：967 passed（+7 M1.6.3.1 新增）
- Golden Cases：11 passed，1 skipped
- 安全扫描：PASS
- DeepSeek Chat Smoke：overall_success=true（执行 2 次）
- PydanticAI 残留：0（pyproject.toml 无声明，生产代码无 import）
- DeepSeek 直接 Adapter/Renderer：0
- AgentRuntime：不可导入（模块已删除）

**TurnPipeline 最终职责边界：**
- **ID 生成** — conversation_id、request_id、trace_id
- **请求指纹** — SHA-256 计算与冲突检测
- **Owner/Waiter 幂等协调** — claim/complete/abort 生命周期
- **TraceRecorder** — 创建与传递
- **TurnController** — 创建、状态转换管理
- **ContextBuilder** — 统一构建入口（输入截断、Memory 状态检查、runtime_mode 匹配）
- **ToolExecutionContext** — 统一工厂方法
- **Memory 失败标记** — mark_memory_failed()、commit_memory_safe()
- **Snapshot** — 保存、重放（build_replay）、abort

**两个 Service 保留的差异：**
- LLM 阶段实现（Intent、QueryPlan、DAX、Answer/ReportSpec）
- Provider（Mock vs DeepSeek）
- Fixture Key 选择逻辑

**修改文件清单：**
- `backend/app/application/turn_pipeline.py` — 生产代码扩展
- `backend/app/application/deepseek_turn_service.py` — 生产代码简化
- `backend/app/application/mock_turn_service.py` — 生产代码简化
- `backend/tests/unit/test_agent_framework.py` — 防回归测试新增
- `backend/tests/unit/test_m162_config.py` — 测试适配
- `docs/08_development_roadmap.md` — 文档更新
- `docs/09_context_handoff.md` — 交接文档更新
- `docs/02_technology_selection_and_system_architecture.md` — 架构文档更新
- `docs/adr/README.md` — ADR 状态更新
- `CHANGELOG.md` — 本条目

**本轮 Tag：** 无

---

## [M1.6.3] — 2026-08-04

### 统一TurnPipeline与旧Agent抽象清理

**来源：** M1.6.3 开发轮次。

**M1.6.2 遗留补齐：**
- DeepSeekTurnService 初始化共享 ToolGateway（`create_default_tool_gateway()`）
- `allowed_tools` 统一来自 `gateway.list_tools()`，不再硬编码
- 真实工具执行统一经过 ToolGateway（白名单、Intent权限、runtime_mode、超时和重试真实生效）
- ContextBuilder 统一进入 DeepSeek 管线（输入截断、Memory状态检查、runtime_mode匹配）
- 补充 main DeepSeek 有 Key 路径测试（Mock 注册表/Provider 禁止网络，验证 lifespan 创建 DeepSeekTurnService，验证 HarnessConfig 为 DEEPSEEK 且 is_mock=False）
- 文档闭环：M1.6.2 标记 ✅ 完成（Commit `208bca4`）

**统一确定性 TurnPipeline：**
- 新增 `backend/app/application/turn_pipeline.py`：共享执行骨架类
- M1.6.3 统一：ID 生成、请求指纹、Owner/Waiter 幂等协调、TraceRecorder、Snapshot 保存与重放
- M1.6.3.1 补全：TurnController 创建、ContextBuilder 统一入口、ToolExecutionContext 工厂、Memory 失败标记、pending memory 创建
- Mock 和 DeepSeek 实际调用同一个 `TurnPipeline` 类型
- `DeepSeekTurnService` 通过 ToolGateway 执行所有工具调用（`get_semantic_model_schema`、`execute_dax`、`render_report`）
- DeepSeek 源码中不存在直接 Adapter/Renderer 调用
- 工具超时、重试、权限、max_tool_calls 在 DeepSeek 路径真实生效

**清理旧 Agent 抽象：**
- 删除 `backend/app/agent/runtime.py`（AgentRuntime 抽象类）
- 删除 `backend/app/agent/mock_runtime.py`（MockAgentRuntime）
- 删除 `backend/app/agent/__init__.py`
- 移除 `pyproject.toml` 中 `pydantic-ai==2.21.0` 依赖
- `MockTurnService` 直接使用 `MockLLMProvider`（通过 `_LLMProviderAdapter` 保持测试兼容）
- `main.py` 移除 MockAgentRuntime 导入
- 重写 `test_agent_framework.py` → M1.6.3 防回归测试
- 更新 `test_mock_pipeline.py`、`test_m1_fixes.py`、`test_m1_0_1_fixes.py`、`test_m162_config.py` 移除旧引用

**防回归测试：**
- Mock 和 DeepSeek 使用同一 `TurnPipeline` 类型
- DeepSeek 源码中无直接 Adapter/Renderer 调用
- 两条路径的工具来自同一个 Registry（`create_default_tool_gateway`）
- ContextBuilder 输入截断和 runtime_mode 检查在 DeepSeek 路径生效
- 仓库中不存在 PydanticAI 生产引用或依赖声明（全仓搜索验证）
- API 响应字段、Golden Case 和现有 Smoke 语义未回归

**真实 DeepSeek Chat Smoke：**
- `d6665bd` 提交时因临时上游 API 问题返回 HTTP 500，记录为"未通过"
- M1.6.3.1 复验时实际执行通过（overall_success=true），确认代码逻辑正确

**测试结果（`d6665bd` 提交时）：**
- pytest：960 passed（包含 M1.6.3 新增/重写测试）
- Golden Cases：11 passed，1 skipped
- 安全扫描：PASS（138 文件）
- 全仓搜索：0 处 PydanticAI 生产引用，0 处 Adapter/Renderer 直接调用

**文档修改：**
- `docs/02`：移除 PydanticAI 引用，更新实施状态为 M1.6.3 完成
- `docs/08`：M1.6.2 → ✅ 已完成（`208bca4`），M1.6.3 → 进行中
- `docs/09`：M1.6.2 入已完成版本表，当前阶段改为 M1.6.3
- `docs/adr/README.md`：更新整改范围为已完成
- `CHANGELOG.md`：本条目

**Commit SHA：** 本轮提交
**本轮 Tag：** 无

---

## [M1.6.2] — 2026-08-04

### Harness与配置收口

**来源：** M1.6.2 开发轮次。

**配置收口：**
- `harness/models.py`：移除重复 Enum 定义（AppEnv/LLMMode/PowerBIMode/HarnessMode），统一从 `config/settings.py` 导入
- `HarnessConfig.from_settings()`：Settings → HarnessConfig 完整映射入口，覆盖四种运行模式 + 8 个字段（request/powerbi timeout、max_tool_calls、max_dax_repairs、max_llm_format_retries、max_powerbi_retries、max_query_rows、max_user_input_length）
- 移除 `DEFAULT_MOCK_CONFIG`：不再作为 DeepSeekTurnService 的默认回退
- `DeepSeekTurnService`：移除 `DEFAULT_MOCK_CONFIG` 导入，config fallback 仅从自身 settings 构建（`HarnessConfig.from_settings(settings)`），禁止回退 Mock 配置
- `main.py` lifespan：统一从 Settings 构建一次 `HarnessConfig`，显式传给 MockTurnService 和 DeepSeekTurnService

**工具注册单一来源：**
- 新增 `backend/app/harness/tool_registry.py`：`register_default_tools()` + `create_default_tool_gateway()` 共享入口
- 集中注册三个白名单工具：`get_semantic_model_schema`、`execute_dax`、`render_report`
- 工具超时和重试从 `HarnessConfig` 读取（不再写死 30s/1 等魔数）
- `MockTurnService._build_tool_gateway()` 改用共享入口，不再自行维护三套 ToolSpec
- `SchemaInput` 移至 `tool_registry.py` 作为共享模型

**测试新增：**
- 新增 `backend/tests/unit/test_m162_config.py`（24 个测试）
- Settings 与 HarnessConfig Enum 类型统一验证
- from_settings() 全部 12 个字段映射验证
- DeepSeek 配置 llm_mode=DEEPSEEK 且 is_mock=False
- main lifespan 配置传递验证（Mock/DeepSeek）
- 共享工具注册三工具白名单 + 超时/重试来自配置

**文档残差修正：**
- `docs/08`：M1.6.1 → ✅已完成(0f6424f)，M1.6 章节标题修正，M1.6.2 → 进行中
- `docs/09`：M1.6.1 Commit 回填 0f6424f，m1-deepseek-pipeline-release Tag SHA 修正为 a926b5e
- `docs/adr/README.md`：明确 PydanticAI 和旧 Agent 抽象暂时保留，M1.6.3 确认无引用后删除，非永久保留
- `docs/02`：同步临时保留说明，实施状态表更新

**测试结果：**
- pytest：961 passed（937 + 24 新增）
- Golden Cases：11 passed，1 skipped
- 安全扫描：PASS（141 文件）

**本轮不统一 TurnPipeline、不接入 ContextBuilder、不把 DeepSeek 工具调用改经 ToolGateway（M1.6.3 范围）。**

**Commit SHA：** 本轮提交
**本轮 Tag：** 无

---

## [M1.6.1] — 2026-08-04

### 审计复验与架构定案

**来源：** M1.6.1 文档轮次。

**动态复验结论：**
- PydanticAI 生产路径实际未使用（DeepSeekTurnService 绕过 AgentRuntime）
- DeepSeek 绕过 ToolGateway 和 ContextBuilder
- TurnController 限制未生效
- DeepSeek 误用 DEFAULT_MOCK_CONFIG
- Mock 与 DeepSeek 存在事实上的双管线

**架构决定（用户明确批准）：**
1. 废弃 PydanticAI 作为生产 Agent 框架（ADR-001 → superseded）
2. 采用确定性 TurnPipeline 控制对话生命周期
3. LLM 只负责受约束的结构化生成（Intent、QueryPlan、DAX、Answer、ReportSpec）
4. ToolGateway 是 Power BI 和 Renderer 的唯一调用入口
5. Mock 与 DeepSeek 共享同一执行骨架，只替换 Provider、Adapter 或 Fixture

**文档修改：**
- PROJECT_CHARTER.md：移除 PydanticAI 约束，改为确定性管线和 Provider 抽象
- docs/02：ADR 表更新（ADR-001→superseded，ADR-005 新增），架构定案章节
- docs/adr/README.md：ADR-001→superseded，ADR-005 摘要
- docs/08：M1.6 五轮路线固化
- docs/09：更新当前阶段为 M1.6.1 完成，下一轮 M1.6.2
- CHANGELOG.md：本条目

**M1.6 五轮路线：**
- M1.6.1 审计复验与架构定案（本轮）
- M1.6.2 Harness与配置收口
- M1.6.3 统一TurnPipeline与旧Agent抽象清理
- M1.6.4 AI真实性、异常处理与对抗测试
- M1.6.5 CI、全量回归与封板

**本轮未修改业务代码、未删除 PydanticAI 依赖、未创建 Tag。**

---

## [M1.5] — 2026-08-03

### 全链路验收与M1封板

**来源：** M1.5 开发轮次。

**P0 修复：**
- Token/repair 统计修复：建立请求级 LLMCallCollector + ObservedLLMProvider 观察层
- Provider 失败调用计入 attempt_count，可取得 usage 的校验失败计入 Token
- LLMValidationError 安全携带 usage/model/finish_reason
- ValidationService 空权限语义修复：[] 拒绝全部，None 使用默认
- MockPowerBIAdapter 新增 execute_fixture 内部方法，客户端不可控制 Fixture
- 前端文档边界修正：移除绝对布局表述，明确 M2-M4 不绑定 UI

**DeepSeek Chat 全链路：**
- TurnServiceProtocol 通用协议
- DeepSeekTurnService：Intent → Schema → QueryPlan → DAX → Mock QueryResult → Answer/ReportSpec → Mock Renderer → Memory Commit
- RuntimeDataMode.REAL 空间隔离
- 每个请求独立 LLMCallCollector + ObservedLLMProvider
- DeepSeek 失败不回退 Mock LLM
- 幂等重放不重复调用 LLM

**API 模式切换：**
- Mock+Mock: Health 200, Chat Mock 链路
- DeepSeek+Mock (有 Key): Health 200, Chat 真实 DeepSeek
- DeepSeek+Mock (无 Key): Health 503, Chat 503
- Remote MCP: 503
- is_real_ready 更新为 M1.5 边界

**ChatResponse 扩展：**
- 新增 llm_mode、powerbi_mode、source_mode、usage 字段
- usage: call_count, repair_count, prompt_tokens, completion_tokens, total_tokens, duration_ms, estimated_cost_usd, pricing_configured
- is_mock 动态反映 LLM 层
- 不新增 UI 布局字段

**Settings 新增：**
- deepseek_input_cost_per_million_tokens、deepseek_output_cost_per_million_tokens（可选）

**错误映射：**
- 409/422/502/503/504

**文档修改：**
- Settings.version → M1.5
- docs/08/09/10/11 + README + CHANGELOG 同步更新
- docs/10 前端边界软化

**测试结果：**
- pytest：937 passed
- Golden Cases：11 passed，1 skipped
- 安全扫描：PASS（138 文件）

**Commit SHA：** 本轮提交
**封板 Tag：** `m1-deepseek-pipeline-release`

---

## [M1.4.1] — 2026-08-03

### 真实性验证与Smoke验收修复

**来源：** M1.4.1 修复轮次。

**P0 修复：**
- KPI 列顺序 Bug：`_validate_kpis_strict` 从 set 枚举改为有序列映射，确保列索引稳定
- Answer `semantic_model_key` 强制非空绑定（空值拒绝）
- Report `data_source` 强制非空绑定（空值拒绝）
- KPI.value=None 和 bool 拒绝（不再静默通过）
- Metrics 使用 `metric_provenance` 结构化来源契约（direct/sum/avg/count/min/max），旧自由文本 evidence 不再放行
- QueryPlan `requested_template` 限制为三个内部 Key（sales_weekly/satisfaction/operating_overview）或 null，中文名称在 Prompt 中映射到内部 Key
- 非法模板 Key 触发 QueryPlan 一次修复，Provider 最多调用 2 次
- 模板冲突（显式模板与 QueryPlan 模板不一致）零次 ReportSpec 调用
- 空模板权限集合正确拒绝所有模板（不错误回退默认）
- Table 类型严格比较：区分 bool/int/float/string/null（True≠1, 1≠1.0, 1≠"1", None≠"None"）
- Smoke 成功条件加固：所有关键条件参与判定，dax_safe/renderer_ok 失败时 success=false
- Smoke Token 统计包含 Intent、QueryPlan、DAX、Answer/ReportSpec 全部阶段
- `intent_repairs` 不再硬编码为 0，各阶段独立统计
- Settings.is_real_ready 注释更新为 M1.4.1 当前边界

**真实 DeepSeek Smoke 结果：**
- 总体 success=true，model=deepseek-chat，total_tokens=8570
- 数据问答：Answer repairs=0，evidence_bound=true，metrics_provenance_valid=true
- 报表生成：ReportSpec repairs=0，qp_requested_template=sales_weekly，template_consistent=true
- 使用真实 DeepSeek + 本地 Mock QueryResult，未调用真实 Power BI

**测试结果：**
- pytest：936 passed
- Golden Cases：11 passed，1 skipped
- 安全扫描：PASS（134 文件）

**文档修改：**
- Settings.version → M1.4.1
- docs/05/07/08/09/11 + README + CHANGELOG 同步更新

**Commit SHA：** 本轮提交
**本轮 Tag：** 无

---

## [M1.4] — 2026-08-03

### 真实 Answer 与 ReportSpec 生成

**来源：** M1.4 开发轮次（M1.4-A/B/C/D1/D1.1/D2）。

**M1.4-A：遗留问题收口**
- 文档一致性：docs/08/05/11/04 M3/M4/M5 边界统一
- QueryPlan 模型 Key 权威性：传入值与 schema.key 不一致时 LLM 调用前拒绝
- DAX 独立表引用验证：FILTER/COUNTROWS/ALL/VALUES 等独立表名验证
- 旧 QueryPlan+DAX Smoke 收紧：调用真实 Intent、输出白名单、try/finally

**M1.4-B：真实 Answer 生成**
- `DeepSeekAnswerService`：安全上下文、集中式 Prompt、最多一次修复
- `AnswerContext`：行/单元格截断、不含 DAX/Secret
- Evidence 四大字段强制绑定（result_id/semantic_model_key/row_count/source_mode）
- Metrics 可追溯验证（列名直接匹配 + 跨列聚合匹配）
- Truncated/input_truncated 强制披露（error，非 warning）
- 空结果不得虚构 metrics

**M1.4-C：真实 ReportSpec 生成**
- `DeepSeekReportSpecService`：安全上下文、集中式 Prompt
- KPI field/value 真实性验证（数值必须可由 QueryResult 复现）
- Chart x_field/y_field 必须在 QueryResult.columns 中，type 仅允许 bar/line/pie/scatter
- Table 整行投影验证（防跨行拼接 + 重复行限制 + 类型严格比较）
- Mock Renderer 兼容性验证
- M1.4 Smoke 入口：双案例（data_question + report_generation），安全脱敏输出

**M1.4-D1/D1.1：Smoke 判定修复与安全诊断**
- Overall success 严格由两个案例 AND 决定
- 失败时退出码非 0、终端提示动态生成
- 安全诊断字段：stage/error_type/error_code/validation_codes
- 运行时 Intent 互斥分流验证

**真实 DeepSeek Smoke 结果：**
- 总体 success=true，model=deepseek-chat，total_tokens=7568
- 数据问答：Answer repairs=1（首次需修复，修复后严格验证通过）
- 报表生成：ReportSpec repairs=0，Mock Renderer 兼容通过
- 使用真实 DeepSeek + 本地 Mock QueryResult，未调用真实 Power BI

**Answer repairs=1 说明：**
- 真实 DeepSeek 首次 Answer 输出未通过 evidence 严格验证（首次缺失某字段）
- 一次修复后（≤2 次 Provider 调用）evidence 完整绑定，严格验证通过
- 修复机制工作正常，符合设计预期

**测试结果：**
- pytest：858 passed（M1.3.2 基线 706 + M1.4 新增 ~152）
- Golden Cases：11 passed，1 skipped
- 安全扫描：PASS（133 文件）
- 离线测试不访问互联网

**文档修改：**
- Settings.version → M1.4
- docs/05：同步最终测试结果与真实 Smoke 结果
- docs/07：M1.4 完成，待观察项更新
- docs/08：M1.4 已完成，M1.5 为下一轮
- docs/09：当前代码能力、运行边界、真实 Smoke 结果
- CHANGELOG：本记录
- README：M1.4 能力说明

**Commit SHA：** 本轮提交
**本轮 Tag：** 无

---

## [M1.3.2] — 2026-08-03

### 前端视觉与结构化回答契约固化

**来源：** M1.3.2 纯文档与视觉资产固化轮次。

**视觉资产归档：**
- 两张前端参考图归档至 `docs/assets/frontend/`：
  - `整体01.png` — 已有对话与组合回答态
  - `整体02.png` — 新聊天欢迎态与菜单展开态
- 图片作为未来 M5 React 前端开发的视觉参考

**前端最终产品方向固化：**
- 最终为带左侧栏的 GPT 式极简对话网页（React + Vite，M5 开发）
- 左侧栏：PowerBIAgent 标识、新聊天、搜索聊天、项目、最近报表、最近对话、用户信息
- 主对话区：新聊天欢迎态、已有对话态、底部输入器
- 输入器：胶囊形容器、"+"按钮、文本输入、模型选择、发送按钮
- 全局视觉：纯白/极浅灰为主，黑色/深灰正文，克制蓝色用于图表，大面积留白

**结构化组合回答契约：**
- AI 回答未来可由多个内容块按顺序组成：text、metrics、table、chart、report_attachment
- 表格和图表数据必须来自 QueryResult，LLM 不得虚构
- 图表仅允许 bar/line/pie/scatter，使用结构化字段，禁止生成 HTML/JS/外部脚本
- 报表附件引用由后端生成，禁止 LLM 生成任意外部 URL
- 当前不创建新的 Python 消息 Envelope 或 API 代码

**当前能力与未来边界：**
- 当前正式用户模型仅 DeepSeek；Mock 仅测试；GPT-5.6 未接入
- 当前 QueryResult 仍为 Mock；真实 Power BI 属于 M2
- 报表资源（查看/下载）属于 M3；会话历史/搜索属于 M4
- 前端正式开发延后至 M5；M1.4 继续复用现有 AnswerSpec 和 ReportSpec

**文档修改：**
- CHANGELOG：新增 M1.3.2 记录
- `docs/00`：补充组合回答和左侧栏布局
- `docs/01`：替换为带左侧栏的完整页面骨架
- `docs/04`：核对真实 API 路径，补充 AnswerSpec/QueryResult/ReportSpec/RenderedReport 职责
- `docs/05`：同步 706 passed / 11 Golden Cases 基线，补充未来验收项
- `docs/07`：修复过期状态，新增待确认项
- `docs/08`：插入 M1.3.2 记录，补充各阶段前固化内容
- `docs/09`：覆盖更新交接文档
- `frontend/README.md`：更新前端方向和引用
- 新增 `docs/10_frontend_visual_and_interaction_spec.md`
- 新增 `docs/11_structured_answer_contract.md`

**本轮性质：**
- 纯文档与视觉资产固化
- 不修改后端业务代码、不修改前端业务代码
- 不创建 React 项目、不修改 Settings.version
- 不进入 M1.4、不创建 Tag
- 下一轮仍为 M1.4 真实Answer与ReportSpec生成

**测试结果：**
- pytest：706 passed（无变化，本轮无代码修改）
- Golden Cases：11 passed，1 skipped（无变化）
- 安全扫描：PASS

**Commit SHA：** 本轮提交
**本轮 Tag：** 无

---

## [M1.3.1] — 2026-08-03

### QueryPlan 与 DAX 验证修复

**来源：** M1.3.1 开发轮次。

**QueryPlan 真实 Schema 验证：**
- `DeepSeekQueryPlanService` 生成后实际调用 `ValidationService.validate_query_plan()`
- 为每次调用构造当前 `schema.key` 的专用 `ValidationService`（不依赖固定白名单）
- 验证覆盖：`semantic_model_key` 匹配、measures/dimensions/filters 字段真实存在、top_n 合法
- 验证错误与格式错误共用一次修复配额，总调用 ≤2 次
- 验证修复请求携带安全错误代码和最多5个非法对象名，不含完整异常或响应
- 网络/鉴权/限流/超时/HTTP 5xx 不进入修复

**DAX 表—对象归属验证：**
- 构建 `_SchemaIndex`：表→列集合、表→度量值集合、度量值→表集合、列→表集合
- 带表限定引用：验证表存在且对象确实属于该表（不因对象存在于其他表而误判通过）
- 未限定引用 `[X]`：度量值需唯一解析，多表同名标记 `ambiguous_measure`；列引用标记 `unqualified_column_reference`
- 未加引号表名 `Table[Column]` 正确识别和验证
- 含空格表名 `'Sales Detail'[Amount]` 正确支持
- 双引号字符串别名不被误判为 Schema 对象
- 新增错误代码：`unknown_table`、`object_not_in_table`、`unknown_measure`、`ambiguous_measure`、`unqualified_column_reference`
- 修复请求只携带 QueryPlan 摘要、安全 Schema、错误代码和非法对象名（≤5），不含完整失败 DAX

**测试补强：**
- QueryPlan：11 个新增真实验证集成测试（合法通过、虚构 measure/dimension/filter 修复、model_key 不匹配、修复仍失败停止、仅两次调用、Provider 错误不修复、错误脱敏等）
- DAX：12 个新增多表归属测试（合法跨表引用、非法跨表引用、未知表、未限定度量值/列、歧义度量值、空格表名、字符串别名、修复边界等）

**Smoke：**
- 新增 `query_plan_repair_count`、`dax_repair_count`、`prompt_tokens`、`completion_tokens`、`total_tokens` 脱敏输出字段
- 使用多表 Schema（Sales + Customer）

**文档修正：**
- M1.3 真实 Commit 关系：主体实现 `441ca45`，文档 SHA 回填 `c0e782b`

**测试结果：**
- pytest：706 passed（M1.3 703 + M1.3.1 新 3 回归测试）
- Golden Cases：11 passed，1 skipped
- 安全扫描：PASS
- 真实 Smoke：✅ 通过（QP 0 修复、DAX 0 修复、2178 tokens、deepseek-chat）

**Commit SHA：** 本轮
**本轮 Tag：** 无

---

## [M1.3] — 2026-08-03

### 真实 QueryPlan 与 DAX 生成

**来源：** M1.3 开发轮次。

**真实 Commit 关系：**
- M1.3 主体实现：`441ca45`
- M1.3 文档 SHA 回填（补充遗漏文件）：`c0e782b`

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
- **注意：** M1.3 仅声明复用 ValidationService，实际调用在 M1.3.1 中补齐

**DeepSeekDAXService：**
- `backend/app/dax/deepseek_service.py` — 复用 DeepSeekLLMProvider
- `backend/app/dax/prompt.py` — 集中式 DAX 提示词
- `backend/app/dax/safety.py` — DAX 只读安全验证器
- Prompt：只生成一个只读 EVALUATE DAX、只用 Schema 对象、不生成 SQL/脚本/答案
- DAX 安全验证：禁止写入/删除/更新、SQL/Shell/Python/JS、多语句注入、注释绕过、非法对象、空 DAX、超长/超复杂
- 允许：EVALUATE、SUMMARIZECOLUMNS、FILTER、TOPN、ORDER BY、DEFINE MEASURE、VAR、RETURN
- 验证结果结构化：is_valid、errors、warnings、referenced_objects
- 最多一次修复（同 M1.2 规则）
- **注意：** M1.3 使用全局名称集合验证，表—对象归属验证在 M1.3.1 中补齐

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

**Commit SHA：** `441ca45`（主体实现）、`c0e782b`（文档回填）
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

**Commit SHA：** `53cf43e`
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
