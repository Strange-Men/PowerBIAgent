# 08 — 开发路线

> **状态：** M2.6.3 Deterministic Execution & Verified Facts 已完成开发分支验收候选
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
  M1.6.3 统一TurnPipeline与旧Agent抽象清理 ✅ 已完成 (d6665bd)
  M1.6.3.1 统一管线复验与彻底收口         ✅ 已完成 (d99d243)
	  M1.6.3.2 事务边界与单写入者彻底收口       ✅ 已完成 (`d57e38c`)
  M1.6.4 AI真实性、异常处理与对抗测试    ✅ 已完成 (4217b66)
  M1.6.5 真实测试、机器错题本与架构防偏移治理  ✅ 已完成 (e850f14 / cb2826e / 762f4cf)
  M1.6.6 CI、最终架构审计与二审候选版       ✅ 已完成 (084aa76)

M1.7 MVP轻量化与通用CI固化                     ✅ 已完成 (e5d1740)
M1.7.1 最终状态收口与封板候选修复                 ✅ 已完成 (1dd20de)
M1.7.2 M0—M1 最终文档收口与封板           ✅ 已完成 (23d8ddb，Tag: m1.7.2-m0-m1正式封板)
M1.8 Codex接管准备与仓库上下文固化          ✅ 已完成候选

M2 真实 Power BI MCP 与数据问答
  M2.0 官方证据、架构与路线固化                 ✅ 已完成候选
  M2.1 Local MCP 最小真实连接验证                ✅ 已完成候选
  M2.2 真实 Semantic Model Schema 接入          ✅ 已完成候选
  M2.3 真实 DAX 与 QueryResult 标准化            ✅ 已完成候选
  M2.4 接入现有 TurnPipeline                    ✅ 已完成候选
  M2.5 真实全链路验收与封板候选                  ✅ 已完成
  M2.6 正确性契约与架构治理加固                  ✅ 已完成
  M2.6.1 Known-answer Oracle + Real Multi-turn   ✅ 已完成（离线固化）
  M2.6.2 Business Semantic Grounding Foundation  ✅ 已完成
  M2.6.3 Deterministic DAX / Verified FactSet     ✅ 已完成候选
  M2.6.4 最终 hardened release gate               ⬜ 未开始

MVP 功能阶段 (后续)
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

**状态：** ✅ 已完成 | **Commit：** `a926b5e` | **Tag：** `m1-deepseek-pipeline-release`

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

**状态：** ✅ 已完成

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

**状态：** ✅ 已完成 | **Commit：** `d99d243`

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

**状态：** ✅ 已完成 | **Commit：** `4217b66`

**完成内容：**
- ARCH-164-001: Service 不再暴露可写 Memory Repository
- ERR-164-001: API 错误映射收口（402独立映射、LLMConfigurationError error_code区分、显式映射补齐、LLMProviderError兜底）
- ERR-164-002: HTTPX 异常分类细化（ConnectTimeout/ReadTimeout/WriteTimeout/PoolTimeout）
- DOC-164-001: 版本与文档同步
- TRUTH-164-001 ＆ TRUTH-164-002: AI 真实性门禁（数值一致性验证、KPI类型拒绝、虚构值拒绝、空结果不得返回KPI/Chart/Table、Answer evidence强制绑定）
- ADV-164-001 ＆ ADV-164-002: 最小对抗测试（输入/Prompt注入、DAX边界）
- 新增测试：84 个（test_m164_arch_truth_adv.py）
- 真实 LLM 调用次数：0
- Service 公开 memory_repo 属性：0 | Service 直接 Memory 写入：0 | Service 直接 Snapshot 写入：0

**本轮不创建 Tag。**

---

### M1.6.5｜真实测试、机器错题本与架构防偏移治理

**状态：** ✅ 已完成 | **Commit：** `e850f14`、`cb2826e`、`762f4cf`

**完成内容：**
- 阶段A：路线修订与治理基线（GOV-165-001/002）
- 阶段B：真实行为测试（TEST-165-001 Prompt注入、TEST-165-002 API异常集成、TEST-165-003测试真实性证明）
- 正式机器错题本（GOV-165-003）与校验器
- 架构偏移复验矩阵（AUDIT-165-001）
- 本轮不开发CI、不进行最终封板、不创建Tag、不开发M2

**本轮不创建 Tag。**

---


### M1.6.6｜CI、最终架构审计与二审候选版

**状态：** ✅ 已完成 | **Commit：** `084aa76`

**计划内容：**
- M1.6.5遗留收口
- 错题本与校验器强化
- Prompt注入行为测试补强
- TurnController真实限制路径验证
- GitHub Actions CI
- 全量回归和安全检查
- 最终候选版架构审计
- 文档、版本与状态同步
- Commit和Push

**本轮不创建Tag、不执行真实DeepSeek Smoke、不宣布M1.6正式封板。**
**二审通过前不进入M2。**

**M1.6.6结束后仍需用户连接仓库二审。**


### M1.7｜MVP轻量化、测试收敛与通用CI固化

**状态：** ✅ 已完成 | **Commit：** `e5d1740`

**目标：** M0—M1 正式封板前最后一次整理，不是新功能开发轮。

**计划内容：**
- 测试体系收敛（按领域组织，删除重复/纸面/恒真测试）
- 通用CI固化（版本无关动态一致性检查）
- Smoke脚本轻量化（只保留一个人工验收入口）
- 文档与冷启动轻量化（归档历史审计、压缩活跃文档）

**本轮不创建Tag、不进入M2、不新增功能、不执行真实DeepSeek Smoke。**

---

### M1.7.1｜最终状态收口与封板候选修复

**状态：** ✅ 已完成 | **Commit：** `1dd20de`

**完成内容：**
- 修正 docs/08 M1.6.6 详细章节的历史状态冲突并统一为已完成
- 修正 docs/09 PydanticAI 错误描述（已从生产依赖移除）
- 删除恒真测试 test_no_stale_tag_for_current_version
- 加固 CI 工作区干净检查（git diff --check + git diff --exit-code + git status --porcelain）
- 版本同步至 M1.7.1

**远程 CI：** Run #30991136311，completed / success。

**本轮不创建 Tag、不进入 M2、不新增功能。**

---

### M1.7.2｜M0—M1 最终文档收口与封板

**状态：** ✅ 已完成 | **Commit：** `23d8ddb` | **Tag：** `m1.7.2-m0-m1正式封板`

**目标：** M0—M1 最后一个版本，只修正文档状态并建立封板流程，不新增功能、不修改业务逻辑、不进入 M2。

**计划内容：**
- 文档状态最终同步（docs/08、docs/09、README、CHANGELOG、Settings.version → M1.7.2）
- 历史 Commit 和 CI 事实回填（M1.7 → `e5d1740`、M1.7.1 → `1dd20de` 及 CI Run #30991136311）
- "文档先于 Commit"规则固化至 CLAUDE.md
- 封板 Tag `m1.7.2-m0-m1正式封板`（远程 CI 通过后创建）

**本轮限制：**
- 不修改生产业务逻辑（变化为 0）
- 不执行真实 LLM（调用次数为 0）
- 不修改 Intent/QueryPlan/DAX/Answer/ReportSpec
- 不修改 TurnPipeline/ToolGateway/Memory/Snapshot
- 不修改 API 契约
- 不新增或删除测试用例/测试文件
- 不新增依赖
- Tag 创建前不得声称 Tag 已存在

**M0—M1 开发完成。M2 尚未开始。**

---

### M1.8｜Codex接管准备与仓库上下文固化

**状态：** ✅ 已完成；M2 开发与验收正式封板

**完成内容：**
- `AGENTS.md` 仓库级 Agent 入口
- Codex 冷启动协议
- 架构铁律
- 防开发偏移边界
- `CLAUDE.md` 通用 Agent 化
- M2 开发前上下文基础

**下一阶段：** M2.0 官方证据复核、真实 Power BI MCP 接入设计与开发路线固化。

**本轮不开发 M2 业务代码，不修改生产业务逻辑，不创建 Tag。**

---

## M2 轮次详细路线

> M2 统一遵守 ADR-005、ADR-006 与 ADR-007：TurnPipeline 是唯一控制面，Power BI 只经 ToolGateway → PowerBIAdapter；Mock/Real 共用执行骨架，Generate Query 不使用，Real 失败不回退 Mock。当前 Demo 走 Local MCP + Power BI Desktop，Remote MCP 生产化延后到管理员条件具备且用户另行批准后恢复。实施细节与每轮门禁见 `docs/12_m2_powerbi_mcp_integration_plan.md`。

### M2.0｜官方证据复核、架构设计与路线固化

**状态：** ✅ 已完成候选

- 修复 Error Ledger 冷启动规则与 ADR-005 文档结构。
- 复核 Microsoft / MCP 官方证据，新增 ADR-006。
- 固化 M2.1—M2.5 轮次、测试和防偏移门禁。
- 生产业务实现为 0；真实 Power BI 仍未接入。

### M2.1｜Local MCP 最小真实连接验证

**状态：** ✅ 已完成候选

已真实证明官方 Local Server → stdio → initialize/协议协商 → `list_tools` → Power BI Desktop 发现与连接。使用只读模式；未读取完整 Schema、未执行 DAX、未接 Chat、未改 TurnPipeline。属于“连得上”。

### M2.2｜真实 Semantic Model Schema 接入

**状态：** ✅ 已完成候选

已通过既有 ToolGateway → `LocalMCPPowerBIAdapter` 从 Power BI Desktop 真实读取 tables、columns、measures、relationships 与 hierarchies，并在单次只读会话中用 `List` / `Get` 映射为兼容的 `SemanticModelSchema`。真实 Measure expression 与数据类型已保留；description 字段真实存在但当前测试模型为空；Local 未返回 Prep for AI 专用 metadata，故未实现。未执行 DAX，未调用 DeepSeek，未接 Chat，属于“看得懂模型”。

### M2.3｜真实 DAX 执行与 QueryResult 标准化

**状态：** ✅ 已完成候选

已完成 DAXRequest → ToolGateway → Local Adapter → Local MCP → Power BI Desktop → QueryResult。固定 ROW 值 1 与 `Total Sales` / `Total Quantity` 实际数值均通过真实 Smoke；有序 columns、二维 rows、实际 row_count、execution time、request_id、`source_mode=real` 与 truncated 已标准化，并覆盖 DAX、timeout、permission、connection、malformed、MCP protocol、oversized 及 Preview row-data missing。当前实机未复现仍为 Open 的 Issue #124；DeepSeek 尚不接 Chat。属于“查得到数据”。

### M2.4｜接入现有 TurnPipeline

**状态：** ✅ 已完成候选

已在现有 TurnPipeline 接通 DeepSeek + Local Real Power BI；Service 仍依赖 PowerBIAdapter 抽象，ToolGateway 仍是唯一业务工具入口，没有复制 Pipeline/Service。Layer 2/3 语义校验、Answer provenance、`source_mode=real` 的 Snapshot/Replay 传播与 Real 失败不回退均已验证；三个受控真实自然语言 Case 成功。属于“自然语言真的能查 Power BI”。

### M2.5｜真实全链路验收与 M2 封板候选

**状态：** ✅ 已完成候选

在不新增 Pipeline、Service、Provider、业务词典或完整 DAX Parser 的前提下，完成 7 个真实 Business Golden 和 20 类 Fake/Mock Bad Case 验收。真实 Case 覆盖 Measure、Dimension、Filter、Top N/Sort，并有 3 个 Prompt 未显式点名的对象/组合首次通过、0 repair；`gc_012` 已转为人工 Local Desktop 基线，通用 CI 保持纯 Mock/Fake。full pytest 1210 passed，Golden 11 passed / 1 manual-real skipped，Safety、Ledger 与 Architecture 门禁全部通过。M2 能力准确限定为当前 Local MCP + Power BI Desktop Demo 路线下的受控自然语言数据问答。

Remote MCP 生产化不纳入当前 M2.1—M2.5 Demo 路线；公司管理员条件具备后，按 ADR-006 并经用户另行批准恢复。

**M2.5 完成后的加固阶段：** M2.6；不在 M2.5 提前实现 M3。

### M2.6｜数据问答正确性契约与架构治理加固

**状态：** ✅ 已完成。

Real Filter 能力按真实性矩阵治理：`eq=SUPPORTED`，`ne/gt/gte/lt/lte/in/not_in/contains=NOT_VERIFIED` 并在 Layer 2 受控拒绝；Layer 3 对 eq 的 field/operator/value 与额外业务 Filter 做最小确定性检查。TopN selection 的 N/Measure/方向与 presentation ordering 的末尾 `ORDER BY` 分开验证，ties 不受 `row_count <= top_n` 约束。Architecture Gate 已覆盖 MCP SDK/raw call ownership、ToolGateway、平行生产控制面和 Provider 反向依赖；Health 明确 configuration-ready 不等于 Desktop live-connected。未新增 Pipeline、Service 或 Parser。

### M2.6.1｜Known-answer Oracle + Real Multi-turn Harness

**状态：** ✅ 已完成离线固化。

在 Harness/Test 层建立不依赖 LLM、当前 DAX、Answer 或 Actual QueryResult 反向生成 Expected 的独立 Oracle，支持 scalar/grouped/ordered 与 TopN ties，并以严格显式 numeric tolerance 比较。当前正式基线为 8 个 Known-answer Case（2 个 holdout）、6 个 Conversation / 16 Turn 及唯一离线 Runner；M2.6.3 经治理更正了欠指定 conversation_e：e1/e2 为 partial clarification，e3 补齐 Product 后才执行，禁止语义猜测。通过正式 Chat API 的 Fake/Mock 路径验证 Filter refinement、Dimension switch、Filter replacement、Metric switch、Clarification、失败 Turn Memory 完整性与严格 all-turn PASS 评分。

### M2.6.2｜Business Semantic Grounding Foundation

**状态：** ✅ 已完成。

已按 ADR-008 建立 model-scoped Business Glossary、runtime object/member grounding、结构化 TimeRange、semantic slot `NOT_MENTIONED / RESOLVED / AMBIGUOUS / UNRESOLVED / EXPLICIT_CLEAR` 契约及 deterministic StateTransition。Intent/QueryPlan LLM 只保留语言 weak signal；Grounding + StateTransition 是 Canonical QueryPlan semantic slots 的唯一 authority。Real member lookup 只经 ToolGateway → PowerBIAdapter，且 read-only、bounded、失败不回退 Mock。

验收边界固定为 `Natural Language → Canonical QueryPlan → Layer 2`。DeepSeek + Local MCP + Desktop 的 Real Semantic Matrix 已覆盖 Measure、Dimension、Filter Field、runtime member、TimeRange、TopN/Sort、多轮 KEEP/REPLACE/CLEAR、歧义与失败无污染；fresh `a1 → a2 → a3` semantic regression 5/5，`source_mode=real`、Real→Mock fallback=0。DAX 偶发加入未计划的 Filter group-by 或无法验证结构化时间 filter 时仍由 Layer 3 fail-closed，属于 M2.6.3 downstream entry condition，不计入 M2.6.2 semantic correctness。

### M2.6.3｜Deterministic Execution & Verified Facts

**状态：** ✅ 已完成开发分支验收候选，待远程审计。

按 ADR-009 将 Real canonical path 固定为 `Canonical QueryPlan → Deterministic DAX Builder → Independent Layer 3 → QueryResult → VerifiedFactSet → fact-bounded Answer / ReportSpec`。Real DAX LLM authority/call count 为 0；受限 grammar 只支持 Measure、Dimension、EQ Filter、resolved TimeRange、single-measure Sort/TopN，unsupported capability 继续 fail closed。`QueryPlan.dimensions` 是唯一 group-by 来源，EQ/time literal 使用固定 pattern，TopN selection 与 final ORDER BY 分别表达并独立验证。

Glossary 由 friendly model key + stable runtime schema SHA-256 fingerprint 共同绑定。PendingClarificationContext 与 committed Memory 分离，只保存已权威解析但尚不足执行的 slots；current explicit > pending > 合法 committed KEEP。conversation_e 正式更正为 e1 缺 measure/dimension、e2 仅补 Total Sales 仍缺 dimension、e3 补 Product 后执行，基线为 6 Conversation / 16 Turn。

VerifiedFactSet 从 Canonical QueryPlan + QueryResult 确定性构建 scalar/grouped/ranking/min-max（有直接证据时）、filter/time、row_count/truncation 与 provenance。Answer 使用 deterministic factual sentences；Report KPI/chart/table/insight 只能消费 FactSet/QueryResult，无法证明的 causal insight 省略。已知 `dax_unplanned_group_by_dimension` 与 `dax_filter_structure_not_verifiable` 在支持范围 Real acceptance 中均为 0。

Fresh production E2E 通过正式 `/api/v1/chat → TurnPipeline → actual committed Memory` 执行：exact Known-answer 8/8、holdout 2/2、6/6 Conversation、16/16 Turn、成功 Real query 51、deterministic failure-recovery 1/1、`a1 → a2 → a3` 10/10，fallback=0、pollution=0。Semantic Matrix 34/34 且专项 historical 5/5。

**后续边界：** M2.6.4 仅做 final hardened acceptance、docs consolidation 与 M0—M2 seal；不得把新的核心架构债或 M3 Renderer 提前带入。

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

*最后更新：2026-08-11 | M1.8 Codex 接管准备与仓库上下文固化*
