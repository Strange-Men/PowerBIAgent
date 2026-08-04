# 08 — 开发路线

> **状态：** M1.6.3.1 已完成（M1.6.3 复验与收口），M1.6.4 待开始
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

M1 真实 DeepSeek 接入
  M1.0 M0遗留收口与M1路线固化       ✅ 已完成 (9247322)
  M1.0.1 幂等并发与文档收尾修复      ✅ 已完成
  M1.0.2 密钥与仓库安全规则固化      ✅ 已完成
  M1.1 DeepSeek Provider基础接入    ✅ 已完成 (073a819)
  M1.2 真实意图识别                 ✅ 已完成 (53cf43e)
  M1.3 真实QueryPlan与DAX生成       ✅ 已完成 (441ca45)
  M1.3.1 QueryPlan与DAX验证修复     ✅ 已完成 (6647760)
  M1.3.2 前端视觉与结构化回答契约固化  ✅ 已完成 (db0a7e8)
  M1.4 真实Answer与ReportSpec生成   ✅ 已完成
  M1.4.1 真实性验证与Smoke验收修复    ✅ 已完成
  M1.5 全链路验收与封板              ✅ 已完成 (a926b5e)

M1.6 架构收口与加固
  M1.6.1 审计复验与架构定案           ✅ 已完成 (0f6424f)
  M1.6.2 Harness与配置收口             ✅ 已完成 (208bca4)
  M1.6.3 统一TurnPipeline与旧Agent抽象清理 ✅ 已完成（M1.6.3.1 复验收口）
  M1.6.3.1 统一管线复验与彻底收口         ✅ 已完成（本轮）
  M1.6.4 AI真实性、异常处理与对抗测试    ⬜
  M1.6.5 CI、全量回归与封板             ⬜

MVP 功能阶段 (后续)
  M2 真实 Power BI MCP 与数据问答    ⬜
  M3 报表生成闭环                   ⬜
  M4 多轮记忆完善                   ⬜
  M5 React 前端与联调                ⬜

各阶段前固化：
  M1.4 前 — 已固化 AnswerSpec、QueryResult、ReportSpec 与组合回答关系 (M1.3.2)
  M3 前 — 需固化报表查看与下载资源契约
  M4 前 — 需固化会话历史与持久化方案
  M5 前 — 需完善完整视觉、交互和响应式规范

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

### M1.3.2｜前端视觉与结构化回答契约固化

**状态：** ✅ 已完成 | **Commit：** `db0a7e8`

**完成内容：**
- 两张前端参考图归档至 `docs/assets/frontend/`（整体01: 已有对话与组合回答态、整体02: 新聊天欢迎态与菜单展开态）
- 确定最终 GPT 式对话页面方向：带左侧栏（新聊天、搜索聊天、项目、最近报表、最近对话、用户信息）、主对话区（欢迎态、已有对话态、底部输入器）
- 输入器："+"菜单（数据模型 + 报表模板两分组）、模型菜单（DeepSeek 唯一启用、Mock 仅测试、GPT-5.6 未接入）
- 全局视觉：纯白/极浅灰为主、黑色深灰正文、克制蓝色图表、大面积留白
- 结构化组合回答契约固化：text、metrics、table、chart、report_attachment
- AI 回答数据必须来自 QueryResult，LLM 不得虚构
- 图表仅允许 bar/line/pie/scatter 结构化字段，禁止 HTML/JS/外部脚本
- 当前能力与未来边界明确：DeepSeek 唯一模型、Mock 仅测试、前端延后 M5、真实 Power BI 属 M2、报表资源属 M3、会话历史属 M4
- 创建正式视觉规范文档 `docs/10_frontend_visual_and_interaction_spec.md`
- 创建结构化组合回答契约文档 `docs/11_structured_answer_contract.md`

**本轮不开发前端和业务代码。不创建 React 项目。不修改 Python 代码。不修改 Settings.version。**
**下一轮仍为 M1.4。**

---

### M1.4｜真实Answer与ReportSpec生成

**状态：** ✅ 已完成

**完成内容：**
- 根据 Mock 查询结果生成真实自然语言 Answer
- 生成结构化 ReportSpec
- Report Renderer 仍使用现有 Mock 实现
- 校验回答、证据、模型和 source_mode 一致性

---

### M1.4.1｜真实性验证与Smoke验收修复

**状态：** ✅ 已完成

**完成内容：**
- KPI 列顺序 Bug 修复（set → 有序列映射）
- Answer semantic_model_key 强制非空绑定
- Report data_source 强制非空绑定
- KPI.value=None/bool 拒绝
- Metrics metric_provenance 结构化来源契约
- 模板冲突与空权限集合正确拒绝
- Table 类型严格比较（bool/int/float/str/null 区分）
- Smoke 成功条件加固与 Token 统计修复
- Settings.is_real_ready 注释更新

**本轮不创建 Tag。不进入 M1.5。**

---

### M1.5｜全链路验收与封板

**状态：** ✅ 已完成 | **Commit：** 本轮提交 | **Tag：** `m1-deepseek-pipeline-release`

**完成内容：**
- Token/repair 统计修复：建立请求级 LLMCallCollector + ObservedLLMProvider 观察层
- LLMValidationError 安全携带 usage，校验失败仍计入 attempt 和 Token
- ValidationService 空权限语义修复：[] 拒绝全部，None 使用默认
- TurnServiceProtocol 通用协议 + MockTurnService 适配
- MockPowerBIAdapter.execute_fixture 内部 Fixture 选择
- DeepSeekTurnService：DeepSeek Intent → QueryPlan → DAX → Mock QueryResult → Answer/ReportSpec → Memory 全链路
- Mock/DeepSeek 模式切换：Health 200/503、Chat 可用/不可用
- ChatResponse 扩展：llm_mode / powerbi_mode / source_mode / usage 字段
- Settings 新增可选成本配置：input/output cost per million tokens
- 错误映射：409/422/502/503/504
- Trace 安全强化：LLM 调用事件 + 验证事件
- 幂等、Memory REAL 空间隔离、并发 Collector 隔离
- 前端文档边界修正：移除绝对布局表述，明确 M2-M4 不绑定 UI
- Golden Cases 11 passed / 1 skipped
- M1 封板 Commit 和 Tag `m1-deepseek-pipeline-release`

**真实 API Smoke：** 由用户以真实 Key 执行 `python -m backend.app.application.deepseek_chat_smoke`。

**本轮不接入真实 Power BI、OAuth、Remote MCP。**

---

### M1.6｜架构收口与加固

**状态：** 🔄 进行中

> ⭐ 本轮为文档轮，仅修改白名单文档，不修改业务代码。

**完成内容：**
- 动态复验确认：PydanticAI生产路径未使用、DeepSeek绕过ToolGateway和ContextBuilder、TurnController限制未生效、DeepSeek误用DEFAULT_MOCK_CONFIG、Mock与DeepSeek存在双管线
- 架构决定固化：废弃PydanticAI作为生产Agent框架、确定性TurnPipeline、LLM只负责受约束结构化生成、ToolGateway为唯一入口、Mock与DeepSeek共享执行骨架
- ADR-001→superseded，ADR-005新增：确定性TurnPipeline与受控LLM调用架构
- M1.6五轮路线固化
- PROJECT_CHARTER、docs/02、docs/08、docs/09、CHANGELOG同步更新

**本轮不修改业务代码、不删除PydanticAI依赖、不发布Tag。**

---

### M1.6.2｜Harness与配置收口

**状态：** ✅ 已完成 | **Commit：** `208bca4`

**完成内容：**
- ETCLOVG Harness统一配置收口
- DEFAULT_MOCK_CONFIG误用修复
- Mock/DeepSeek共享配置入口
- 工具白名单统一管理
- 配置文件与环境变量规范

**本轮不开发M2功能。**

---

### M1.6.3｜统一TurnPipeline与旧Agent抽象清理

**状态：** ✅ 已完成 | **Commit：** `d6665bd`

**完成内容：**
- 统一确定性TurnPipeline（共享执行骨架）— Mock/DeepSeek 使用同一 TurnPipeline 类型
- DeepSeek 路径纳入 ToolGateway — 工具白名单、权限、超时、重试真实生效
- TurnPipeline 在 M1.6.3 仅统一：ID 生成、请求指纹、Owner/Waiter 幂等协调、TraceRecorder、Snapshot
- 清理旧 Agent 抽象（AgentRuntime、MockAgentRuntime 已删除）
- 移除 PydanticAI 依赖（pyproject.toml 不再声明）
- 防回归测试（共享骨架、无直接调用、统一 Registry、无 PydanticAI 残留）

**M1.6.3 遗留（M1.6.3.1 修复）：**
- TurnController 创建、ContextBuilder 入口仍在两个 Service 中各自复制
- ToolExecutionContext 直接构造仍在两个 Service 中重复
- Memory 失败标记未统一委托
- CHANGELOG 宣称的职责范围超过代码实际实现

**本轮不开发 M2 功能。**

---

### M1.6.3.1｜统一管线复验与彻底收口

**状态：** ✅ 已完成 | **Commit：** 本轮提交

**复验发现：**
- M1.6.3 CHANGELOG 宣称 TurnPipeline 统一了 TurnController、ContextBuilder 但实际未实现
- 两个 Service 各自复制通用控制面（ContextBuilder、TurnController、ToolExecutionContext、Memory 失败标记）
- 文档与实际代码状态不一致

**控制面补全：**
- TurnPipeline 扩展为真正的控制面：ContextBuilder 创建、TurnController 创建与传递、ToolExecutionContext 工厂、create_pending_memory()、mark_memory_failed()、commit_memory_safe()
- 两个 Service 移除各自 ContextBuilder、统一委托给 TurnPipeline
- 两个 Service 移除直接 ToolExecutionContext 构造、Memory 失败标记委托给 TurnPipeline
- 7 个防回归测试验证控制面统一

**最终验收：**
- pytest：967 passed（960 + 7 M1.6.3.1 新增）
- Golden Cases：11 passed，1 skipped
- 安全扫描：PASS
- DeepSeek Smoke：overall_success=true（执行 2 次）
- PydanticAI 残留：0 | AgentRuntime 残留：0 | 直接 Adapter 调用：0

**本轮不开发 M2 功能。**

---

### M1.6.4｜AI真实性、异常处理与对抗测试

**状态：** ⬜ 待开始

**计划内容：**
- 强化真实性验证（数据源头、数值一致性、LLM不虚构）
- 异常处理全链路覆盖（网络、超时、鉴权、限流、模型错误、验证失败）
- 对抗测试（恶意输入、边界值、超长输入、SQL注入尝试）
- 安全扫描补强

---

### M1.6.5｜CI、全量回归与封板

**状态：** ⬜ 待开始

**计划内容：**
- CI管线配置（安全扫描 + pytest + Golden Cases）
- 全量回归与漏洞检查
- M1.6封板Commit和Tag
- 确保所有测试通过、Golden Cases全部通过

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

*最后更新：2026-08-04 | M1.6.2 Harness与配置收口*
