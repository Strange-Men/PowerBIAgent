# 08 — 开发路线

> **状态：** M5.7 — 简易报表视觉与模板必选（COMPLETE）
> **用途：** 只记录当前路线、阶段边界和已封板摘要；逐版本历史见 `CHANGELOG.md`、Git 与 archive。

## 路线总览

| Milestone | 目标 | 状态 |
|---|---|---|
| M0—M1 | Foundation、DeepSeek、统一 TurnPipeline、Harness 与安全治理 | ✅ 已封板 |
| M2 | Local MCP + Power BI Desktop 真实数据问答与 Truth Boundary | ✅ `m2.6.4-m0-m2-final-seal` 正式封板 |
| M3.0 | Report Architecture + Template/DataPlan Contract | ✅ 完成、远程审计 PASS、已合入 main |
| M3.1 | Sales Report Full Generation + Static HTML + Report Resource | ✅ 远程审计 PASS、已合入 main，CI success |
| M3.2 | Hardened visual acceptance / M3 收口阶段 | ✅ 完成，无 Tag |
| M3.3 | Report Template V2 / Non-redundant Business Information Architecture | ✅ 已完成 |
| **M3.4** | **Adaptive Report Planning + Visualization/Layout Policy** | ✅ **已完成** |
| **M4.0** | **本地持久化架构与存储基础** | ✅ **已完成** |
| **M4.1** | **Memory/Snapshot SQLite 实现 + 并发提交 invariant** | ✅ **已完成** |
| **M4.1.1** | **会话创建竞态与数据库错误语义加固** | **✅ 已完成** |
| **M4.1.2** | **SQLite Transaction Failure & Error Semantics Hardening** | **✅ 已完成** |
| **M4.1.3** | **SQLite Lock Transaction Exit Final Hardening** | **✅ 已完成** |
| **M4.2** | **Conversation/Report recovery（会话与报表元数据恢复）** | **✅ 已完成** |
| **M4.2.1** | **Report metadata authority & linkage hardening** | **✅ 已完成** |
| **M4.2.2** | **路径与元数据一致性最终加固** | **✅ 已完成** |
| **M4.2.3** | **持久化资源身份与元数据权威最终收口** | **✅ FINAL PASS** |
| **M4.3** | **Namespace-first recent/history/search/archive/delete API** | **✅ 已完成** |
| **M4.4** | **Restart/crash acceptance + M4 backend final closure** | **✅ M4 FINAL PASS** |
| **M4.4.1** | **Committed Memory corruption fail-closed + README/document closure** | **✅ FINAL PASS** |
| **M4.4.2** | **M0–M4 truth / persistence boundary final closure** | **✅ FINAL PASS** |
| **M5.0** | **前端设计与契约固化（文档校准、页面结构、交互边界、动态回答原则、UI↔后端能力映射）** | **✅ 已完成** |
| **M5.1** | **React + Vite 前端实现与核心联调** | **✅ 已完成** |
| **M5.2** | **真实业务链路与前端逻辑收口** | **✅ 已完成** |
| **M5.2.1** | **模型能力边界与真实模式说明收口** | **✅ 已完成** |
| **M5.3** | **结构化结果、历史/标题/资源管理与视觉交互最终收口** | **✅ 已完成** |
| **M5.3.1** | **Local Desktop 单实例安全 + presentation verified-field projection** | **✅ 已完成** |
| **M5.3.2** | **Local MCP 多 PBIX 选择、opaque binding 与 beta 协议稳定性** | **✅ 已完成** |
| **M5.3.3** | **多轮语义、conversation/report 生命周期与 Artifact Governance 最终收口** | **✅ 已完成** |
| **M5.4** | **多会话并发、用户设置与资源管理最终收口** | **✅ 已完成** |
| **M5.4.1** | **Settings 全量资源分页、选择/批量语义与 automation ownership cleanup** | **✅ 已完成** |
| **M5.4.2** | **M5 重建基线、旧实验线审计保留与后续阶段治理** | **✅ COMPLETE** |
| **M5.5** | **Semantic correctness 与 capability boundary** | **✅ COMPLETE** |
| **M5.6** | **Presentation、Localization 与 Resource UX truth** | **✅ COMPLETE** |
| **M5.7** | **简易报表视觉 + Report Template Required** | **✅ COMPLETE** |
| **M5.8** | **多 LLM Provider 抽象 + DeepSeek/Kimi 最小双模型** | **⏳ NOT STARTED** |
| **M5.9** | **MCP performance、resilience、并发与压力验证** | **⏳ NOT STARTED** |
| **M5.10** | **固定专业销售报表模板与两模板选择** | **⏳ NOT STARTED** |

### M5.4.2 — M5 重建基线与规划固化（已完成）

- 新开发线 `m5/rebuild` 从 M5.4.1 commit `cab40b076f054a3ebdab0bf6d2b0354f4b2d49db` 建立；M5.4.1 及以前能力不可回退。
- 旧 `m5/frontend` 的 `a197db3`（原 M5.5）与 `6d1620a`（原 M5.5.1）保留为研究/失败经验/审计记录，不删除、不重写、不 revert、不整体 cherry-pick。
- 旧实验实现与 PASS 不能作为新线完成证据；后续只可参考单项思想，并在所属阶段重新实现、重新回归、重新 Real Acceptance。
- 本轮只修改文档和治理，不改生产代码、测试代码、schema 或 migration；完成后停止并等待 M5.5 指令。

### 新 M5.5 — Semantic correctness and capability boundary

只开发 semantic grounding、runtime member validation、ambiguity/no-match、multi-turn KEEP/REPLACE、ranking/TopN、temporal semantic contract 与 capability boundary。核心 Gate：explicit unresolved semantic requirement → clarification/no-match → ZERO DAX。

必须覆盖“火星区”无匹配不得 fallback 全国、“华南/华南区/南区”由 runtime member authority 证明、“大概多少”不误判 prediction、readonly capability 近义表达不依赖无限 regex、TopN 不因非必要 LLM failure 失效，以及 `2025年5月销售额 → 那南区呢 → 换成去年 → 前三个产品呢` 的 slot 继承/替换。禁止 Localization、Report Visual、MCP performance optimization 与 Resource UI 大改。

状态为 COMPLETE。S1 docs/contracts → S2 failure reproducers → S3 capability → S4 object/member → S5 multi-turn → S6 ranking → S7 temporal → S8 cross-domain/schema mutation → S9 focused → S10 full gates → S11 Real/manual 已顺序通过；S12 只执行最终文档、白名单 commit 与 push。M5.6 与 M5.7 已完成；M5.8—M5.10 未开始。

### 新 M5.6 — Presentation, localization and resource UX truth

状态为 COMPLETE。P1 docs/contracts → P2 formatter/localization → P3 presentation density → P4 recent resource truth/sorting → P5 failed lifecycle → P6 floating menus → P7 Settings layout → P8 cross-domain → P9 focused tests → P10 full/governance → P11 Real Browser/manual → P12 final docs/full gates/residual/commit/push 已顺序通过。

Localization 必须以 runtime object 为输入，按 `metadata → model-scoped glossary → persisted registry → bounded display translation → safe fallback` 解析 model/object/schema-scoped display binding；canonical identity 与 facts 永不改变。Presentation fixed policy 为 scalar 纯文本、grouped 简短结论 + table（必要时 chart）、trend 简短趋势结论 + table + line，display formatter 覆盖数字、百分比、金额、日期、月份与 null，并禁止 raw timestamp 可见泄漏。

Resource UX 使用同一正式 truth：Settings 全量查询，Sidebar bounded recent projection；reports 仅 active newest-first，conversation 固定 `updated_at DESC, created_at DESC, stable_id DESC`。failed conversation 是持久化可管理资源。conversation/report 共用 Portal floating menu，Settings shell/content/list/toolbar 建立独立 scroll responsibility。

只开发 canonical/display separation、model/object/schema-scoped Localization、数字/日期/月格式、Answer/Table/Chart 信息密度、Settings/Recent truth、newest-first、failed resource lifecycle、sticky/scroll/responsive toolbar 与不被 overflow clipping 的 floating menus。

conversation/report action menu 必须共用同一 Portal/floating layer，采用 viewport-aware above/below positioning，不能被 scroll container、scrollbar 或 stacking context 裁切；禁止两套脆弱定位逻辑。Settings Resource Manager 必须定义 nested scroll contract，并以 sticky 或 scrollable action toolbar 处理 responsive overflow，保证 destructive actions 始终可访问。

正式 Layout Gate 覆盖 first/middle/last row、scroll top/middle/bottom、100%/125% zoom、768/1080/1440 viewport height、Sidebar scroll、Settings nested scroll、destructive action 可达与 floating menu 无裁切。

`Answer = 洞察`、`Table = 明细`、`Chart = 趋势/关系`；Answer 不得完整重复 table。内部 canonical time representation 不得原样暴露。禁止修改 Grounding authority、DAX authority 与 MCP architecture。

Fresh final evidence：backend `1849 passed, 1 skipped`；frontend typecheck/lint/build PASS、Vitest `79 passed`；Golden `11 passed, 1 manual-real skipped`；Architecture `120`、Repository Safety `302`、Error Ledger `34`、Documentation/Artifact Governance、compileall、Alembic fresh/head-idempotent 与 `git diff --check` PASS。Rich PBIX 四类问题、failed resource lifecycle、floating menu、Settings Layout Gate 与 automation-owned residual=0 均通过。

### 新 M5.7 — 简易报表视觉 + Report Template Required

状态为 COMPLETE。只开发现有 `sales_report.html` 的简易模板 information architecture、responsive layout、plot geometry、axis/tick density、accessibility、visual hierarchy 与 readability，以及永久 `Report Template Required` Gate。任何 report intent/request 必须显式携带有效 `report_template_key`；missing/invalid/stale template 在 ReportData assembly、ReportSpec、Renderer 与 HTML artifact 前 fail closed，禁止默认、猜测或 fallback 第一模板。前端只选择模板，不判断 report intent、不增加 Chat/Report 模式切换。正式视觉 Gate 已按“普通用户必须能读懂报表”通过，而非仅证明 SVG 未越界。Semantic/DAX/VerifiedFactSet authority、M5.6 Presentation authority、MCP、LLM Provider 与 resource lifecycle 均未修改。

完成证据：template-required unit/API/Real spy 覆盖 missing/invalid/stale、retry 与 ZERO downstream；Browser visual matrix 覆盖 7 种点数 × 6 种宽度共 42 组；Rich PBIX Real Browser 完成无模板拒绝、显式简易模板生成、15 点跨年月度趋势、donut/legend、区域对比及结构化表格人工检查；automation-owned conversation/report/HTML/SQLite/delete-intent residual=0。Fresh backend `1866 passed, 1 skipped`，frontend `80 passed` 且 typecheck/lint/build PASS，Golden `11 passed, 1 manual-real skipped`，全部治理门禁 PASS。M5 FINAL 尚未成立。

### 新 M5.8 — 多 LLM Provider 抽象 + DeepSeek/Kimi 最小双模型

M5.7 冻结后才允许开发 `OpenAICompatibleLLMProvider`、`LLMModelProfile`、DeepSeek + Kimi-K2.6、request/conversation-scoped model selection 与同一 authority/regression contract。禁止 MCP profiling、cache、session reuse 或并发优化。

### 新 M5.9 — MCP performance and resilience

M5.8 冻结后才允许开发 profiling、MCP session reuse/cache、bounded concurrency、bounded queue/backpressure、20/50/100 concurrency、PBIX/backend restart、fault injection 与 long soak。不得通过降低 factual validation 换性能；不得修改 Semantic/DAX/VerifiedFactSet authority；warm latency 不得冒充 cold latency。

### 新 M5.10 — 固定专业销售报表模板与两模板选择

M5.10 必须晚于 M5.9，状态为 NOT STARTED。“简易模板”定义为当前 `sales_report.html` 经 M5.7 可读性优化后的稳定模板；新增“销售模板”，按已确认 Power BI 参考报表版式固定实现专业 sales report HTML，并允许用户显式选择两者。

固定架构为 `VerifiedFactSet → ReportData / ReportSpec → template_key → deterministic fixed HTML renderer`。LLM 不拥有 HTML layout、factual 或 query authority，不得每次临场生成 HTML/CSS/SVG。专业模板规划包含深色 Header/title/navigation、KPI cards、左侧阶段/漏斗区、中部横向对比、右侧状态/异常/明细、下部区域/业务表格、地域视觉、明细表及 footer 指标口径 + Last Refresh。runtime schema 不支持 Forecast/Goal/Pipeline 时不得伪造，只能将真实可支持的 sales-specific section 放入相同版位；Agent 主链继续保持跨领域通用。只有 M5.10 完成全部 Gate 后才允许 `M5 FINAL`。

### Generalization Gate 与永久开发顺序

- 项目不是 Sales Agent。M5.5+ 至少验证 Sales/Retail、Education、Inventory/Operations，最终使用开发期间未知的业务模型 holdout。
- 生产代码不得在正式 model-scoped glossary/fixture 外写死业务字段、member 或答案；测试答案不得放入 LLM Prompt。
- 新字段、多相似字段、display rename、table rename、member change、glossary missing 必须 `resolve / clarify / no-match`，禁止猜测。
- acceptance 从 runtime schema + semantic metadata + runtime members + user question 进入正式 Agent 链，并用独立 deterministic oracle 校验。
- 一个 milestone 禁止同时大规模修改 Semantic、MCP、Presentation、Report、Resource lifecycle。
- 每轮固定为 Spec → Failure reproducer → Regression tests → Minimal implementation → Focused Real → Cross-domain → Full gates → User manual acceptance → commit；自动化通过数不能替代 Real Browser/人工验收。

### M5.4.1 — 全量资源生命周期与测试产物治理（已完成）

- 根因验证必须覆盖 recent/archived conversation API、conversation-scoped report history、Settings ResourceManager 与 Sidebar refresh；禁止只放大默认 12/20/50 的 page size 掩盖第一页耦合。
- Settings 建立独立 resource-query state，按 runtime/source namespace 分页访问全部 active/archived conversation 与 report；Sidebar 继续只显示 Recent subset。
- 正式列表合同返回 deterministic ordered page、opaque cursor、`total_count` 与 `has_more`。首屏一页、按需继续加载，滚动容器避免一次渲染无限 DOM。
- selection 明确区分“全选当前已加载”与“选择全部匹配项”；最低交付为全部历史可浏览、多选任意项、selected/loaded/total 可见。
- 浏览/选择数量与 destructive execution wave 分离：一次确认可超过 20 项，前端内部按最多 20 项一组协调正式单资源 API，逐项汇总 partial failure，不新增 bulk delete shortcut。
- Codex acceptance、pytest integration、browser、Real Smoke、MCP 与 report tests 使用 explicit automation ownership；`finally` cleanup 必须经正式 API/repository，随后验证 conversation/report/HTML/SQLite namespace/pending intent/orphan residual 为 0。
- Artifact Governance 只读 fail closed；仅清理可证明 test-owned 的 exact IDs/namespaces。无法确认 ownership 的历史资源视为用户数据并保留。
- report rename 仍只改 `display_title`；archive 隐藏 recent 并可 restore；delete 清理 managed HTML/factual metadata，history 保留最后 title 的 tombstone。M0–M5 authority 不变；M5.5 Deferred。
- Fresh evidence：Real Browser 25 conversations/10 reports 完整分页、20+5 bounded archive/restore、report rename/archive/restore/delete/tombstone/restart 全部通过，automation teardown exact residual=0；backend `1797 passed, 1 skipped`，Vitest `69 passed`，Golden `11 passed, 1 manual-real skipped`；全部治理 Gate 与 `git diff --check` PASS。

### M5.4 — 最终收口（已完成）

- 前端从单一全局 `messages/sending/loading/error` 重构为 `conversation_id → ConversationSession`；`activeConversationId` 只选择可见 session。
- 新会话首次发送由前端生成 UUID 并直接传给现有 Chat API；发送后立即合并到 Sidebar local pending list。
- A/B/C 可同时执行；同 conversation 保持串行。history/navigation 可 Abort，business chat 切窗不取消，完成不自动跳窗。
- 用户卡片作为设置/已归档/资源管理入口；Sidebar 最近会话/报表独立滚动并可折叠。
- 资源面板支持最近对话批量删除、已归档批量恢复/删除、最近报表批量删除/单项重命名；一次最多 20 项，只协调正式单资源 API。
- report delete 删除 HTML/metadata 但保留 presentation tombstone；report `display_title` 仅是可变 UI metadata，不改 report_id/HTML/content_hash/ReportSpec/VerifiedFactSet。
- rename/delete 不进 ToolGateway/LLM tools；archive 不等于 delete；M0–M5 factual authority 不变。
- M5.5 的语义增强、Localization Registry、单指标策略、HTML 视觉重构、profiling/cache 继续 Deferred。
- Alembic revision `a4f6b8c2d190` 新增 report presentation metadata/tombstone；Rich PBIX A/B/C 并发、归档恢复、rename/delete/history tombstone 与测试资源精确清理通过。
- Fresh evidence：backend `1790 passed, 1 skipped`；frontend Vitest `61 passed` 且 typecheck/lint/build PASS；Golden `11 passed, 1 manual-real skipped`；全部治理门禁与 `git diff --check` PASS。

### M5.3.3 — 最终收口边界（已完成）

- LLM 负责 flexible、typed、bounded semantic draft；runtime schema/glossary/members、固定 clock 与 deterministic validators 继续拥有 canonical identity/time authority。
- 当前明确表达 > 当前 bounded draft > committed Memory；区分 fresh question、follow-up、replace，Memory 只继承真正省略的兼容槽。
- 预测、写入、PBIX/Measure 修改、删除数据、任意代码与自然语言 report delete 在 Memory/Grounding/DAX 前 readonly fail closed。
- archive 保留并可恢复；conversation delete 永久清理 exact namespace；独立 report delete 只由用户显式资源管理 UI/API 触发，LLM/ToolGateway 无权限。
- history response 使用 abort/generation + active conversation identity，禁止 A 响应覆盖 B。
- local_state 固定 persistence/reports/runtime/archive；测试 artifact 必须 register ownership、teardown 并验证，Artifact Governance Gate 只读 fail closed，不自动删除用户数据。
- 新增 `e7a9c2d4f631` report delete intent migration；Rich PBIX 八轮真实浏览器、archive/restore、独立 report delete、conversation cascade delete 与 A/B 快速切换已通过。
- 不修改 M0–M5 factual authority，不开发 Remote MCP 或后续里程碑。

## M5.2 / M5.3 正式边界

### M5.2 — 真实业务链路与前端逻辑收口

- Real 模式 startup/health 与真实 DeepSeek + Local MCP + Power BI Desktop 主链
- 通过最小只读 endpoint 发现当前可连接 Desktop/PBIX 语义模型；前端动态选择并传 `semantic_model_key`
- SQLite conversation persistence 启用、namespace 配置与 recent/search/history/restart 联调
- intent / template / model 产品逻辑修正：模板仅是显式可选 override，未选择仍由后端判断 report intent/default template
- 真实多轮 Chat、report、view/download 与 Desktop/persistence 故障态验收
- 结构化表格/图表只做事实契约审计和必要的最小 read-only adapter 决策，不从 answer 反解析、不改 M0–M4 authority

### M5.3 — 视觉与交互最终收口

- QueryResult/VerifiedFactSet 直接来源的只读 `presentation` contract；dataset 是唯一数据副本，metric/table/chart block 只保存引用
- Snapshot presentation transcript 与 conversation title 只作为 UI metadata；默认标题、重命名、搜索、完整历史恢复不进入 Memory truth
- 复用现有 archive/delete API 与 M4 durable delete intent；报表按所属 conversation 管理，不新增独立 report delete
- ChatGPT 风格白色主区/浅灰 Sidebar、尺寸间距、表格横向溢出、柱状图/折线图与报表附件视觉
- responsive、accessibility、键盘/焦点、loading/error/empty、菜单/搜索/删除交互
- 自动化门禁与 Desktop Real 浏览器验收；测试资源使用唯一前缀并经正式 delete/teardown 精确清理

M5.2 不提前进行大规模 CSS/响应式/无障碍 polish；M5.3 不反向修改 M5.2 已固化的 runtime、model、intent、template 或 persistence 业务语义。

### M5.3.1 — Final Hardening（已完成）

- Local MCP 的 discovery、schema、member lookup 与 DAX 虽使用独立 session，但每个 session 都只允许 `ListLocalInstances` 返回唯一 Desktop 实例；0 个保持未连接，多个在 `Connect` 前返回 `powerbi_multiple_desktop_instances`，禁止顺序选择或名称猜测。
- `PresentationDataset` 只按 scalar/grouped/ranking/min/max VerifiedFact 的 `source_fields` 投影 QueryResult；额外未验证列不进入前端，metric/table/chart 继续只引用同一 verified dataset。
- 不新增 instance registry、Remote MCP 或新图表/分析能力；TurnPipeline、Memory、QueryResult、VerifiedFactSet 与 Report authority 不变。

### M5.3.2 — Local MCP 多模型选择与协议稳定性（已完成）

- `ListLocalInstances` 经 beta.12 防腐层映射为内部 typed identity；后端对 PID、local data source 与 start time 的规范化组合使用进程内密钥 HMAC-SHA-256 生成 opaque key。API/前端不暴露 PID、端口、connection string、raw fingerprint 或 MCP payload。
- discovery 可返回多个安全 option；前端按 display name 单选和刷新，重名只显示“实例 1/2”。schema/member/DAX 的每个新 stdio session 都重新枚举并按 opaque key 精确匹配一个实例，再用本 session 的 `connectionName` 执行；无首项 fallback、名称猜测或跨模型重连。
- Desktop 关闭/重启、后端进程重启或 identity 改变会使旧 key stale；请求 deterministic fail closed，前端清空选择并要求刷新后重选，不引入持久化 instance registry。
- 固定 `@microsoft/powerbi-modeling-mcp@0.5.0-beta.12`；逐 option 只读 probe 验证 server/protocol/required tools/Connect/schema，以及 `EVALUATE ROW("__pbiagent_probe", 1)` 的列、一行和值。
- DAX 校验实际 columns/rows/rowCount 与 wire limit；显式 limit metadata 映射到 `QueryResult.truncated`，无完整性证明且触及上限时保守 truncated。VerifiedFactSet 现有 truncated 事实语义不变，不做任意 DAX 分页。
- `sales_report` registry 逻辑 binding 与 opaque resource identity 显式分层；模板 contract/query/layout/fact authority 不变。Remote MCP 继续 Deferred，无 schema/migration、无 M0–M4 authority 变化。

### M5.2.1 — 模型能力边界与真实模式说明收口（已完成）

- 固化 `discovered ≠ selectable ≠ fully supported`：Mock fixture 的 schema 可读性不再自动升级为正式 Chat capability。
- Mock discovery 只返回当前正式支持的 `mock_sales_model`；`mock_satisfaction_model` 继续保留为测试 fixture，不作为前端正常可选项。
- Real Local MCP 仍只返回当前已连接 Desktop 模型，不改变 Adapter、API 或前端类型合同。
- 根 README 醒目标明默认 Mock 与本地 PBIX Real 启动步骤，并与 `frontend/README.md` 统一中文标题和普通叙述。
- 无 M5.3 视觉调整，无 DB schema 或 migration，无 M0–M4 核心链修改。

M0—M2 Final Seal 为 `70748daabfa5d3dd250f17fe22f0c892c7a30b74`。M3.0 commit `e4b5c6c6a759cdf22c74c4d87902482563e27cad`、M3.1 commit `fa4cc0c97a10bcc0867c414dc3fa2d7fa9b35e57` 已纯 fast-forward 合入 main，对应 main CI 均 success。M3.2 / M3.3 / M3.4 直接在 main 完成。M0—M3 已正式封板（Tag: `m3.4-m0-m3-final-seal`）。M4.0 已在 main 完成本地持久化架构：SQLite + SQLAlchemy Async + Alembic；MemoryRepository/SnapshotRepository ABC；settings 扩展；26 新增 tests（1503 total）。M4.0 后续 corrective hardening：pytest-asyncio CI 兼容修复、conversation 复合 PK/FK 命名空间隔离、PRAGMA 每连接事件修正；corrective migration `01dc0d90d920`；40 持久化 tests + 全仓 1517 total。

## 永久 M2 事实链

```text
Canonical QueryPlan
→ Deterministic DAX
→ Independent Layer 3
→ ToolGateway → PowerBIAdapter → Power BI
→ QueryResult
→ VerifiedFactSet
```

Real DAX/factual authority 不回到 LLM，Real failure 不回退 Mock。

## M5.1 — React 前端实现与核心联调（已完成）

- 在 `frontend/` 创建 React 19 + Vite 8 + TypeScript 6 工程；使用 React hooks、普通 CSS 与轻量 lucide icons，不引入路由器、重型 Dashboard 框架或全局状态库。
- 实现 GPT 式 AppShell、可折叠 Sidebar、欢迎/已有对话态、底部 Composer、"+"分组菜单与 DeepSeek-only 单选卡片；项目和账户只展示。
- typed API client 显式传入 conversation `runtime_mode` 与 report `source_mode`，接入 Chat、recent、search、structured history 与 reports；最近报表由最近会话的严格 report history 组合，不新增后端 sidebar/workspace 字段。
- Chat adapter 动态处理 answer/clarification/unsupported/error/empty/report；report view/download 只接受与 `report_id` 一致的后端 canonical reference。Trace、DAX、Memory、usage 与 execution audit 不进入 UI。
- 无 discovery endpoint 时，`semantic_model_key` 与 `sales_report` 在 `src/config.ts` 集中登记并明确为本地配置，不伪装为服务器列表。
- 已确认最小契约缺口：Chat/History 不暴露 QueryResult `columns/rows`、独立 metrics 或 ChartSpec。M5.1 不反解析 answer/audit、不修改 M4 Snapshot/Persistence、不伪造表格或图表。
- Fresh acceptance：frontend typecheck/lint/build PASS，Vitest `13 passed`；Chrome 1600×1000 欢迎态实际渲染检查 PASS；backend `1700 passed, 1 skipped`；Golden `11 passed, 1 manual-real skipped`；Architecture/Repository Safety/Error Ledger PASS。无 migration。

## M4.4.2 — M0–M4 Truth / Persistence Boundary Final Closure（FINAL PASS）

- SQLite committed WorkMemory 不再从 dedicated columns 做 partial reconstruction。Modern `payload_json` 必须完整覆盖 domain contract；NULL/empty/malformed/incomplete/domain-invalid 及 row/payload integrity mismatch 均在 Intent、DAX、Power BI、新 Memory commit 与 fake terminal Snapshot 前 fail closed。
- `MemoryRepository.get_latest_committed()` / `list_by_conversation()` 的 runtime namespace 在 ABC、InMemory 与 SQLite 中 mandatory；production callers 全部显式传入，跨 Mock/Real aggregate 默认行为删除。InMemory conversation store 使用 `(runtime_mode, request_id)`，同 conversation/request ID 可在两种模式完全隔离共存。
- Audit corrective closure：非 legacy committed time corruption 不再被 StateTransition 静默解释为空；terminal Snapshot row/payload request/conversation/fingerprint/terminal integrity mismatch 不得重放。legacy time string contract 保持不变。
- Semantic Grounding、Deterministic DAX + Layer 3、VerifiedFactSet、deterministic Report、terminal Snapshot replay、filesystem HTML 与 durable delete intent 的既有 authority 不变。无产品功能、schema 或 migration；M5 NOT STARTED。
- Fresh acceptance：targeted/adjacent `607 passed`；backend `1700 passed, 1 skipped`；Golden `11 passed, 1 manual-real skipped`；四个治理门 PASS；Alembic head 保持 `c8d4e6f2a109`，fresh DB → head 与幂等 head → head PASS。

## M4.4.1 — Memory Corruption Fail-Closed、README 重构与文档状态同步（FINAL PASS）

- `StructuredWorkMemory.filters` 仍保持既有 `list[dict]` storage/legacy contract，但 domain validation 会逐项按 canonical `StructuredFilter` 校验；SQLite payload 的 malformed filter 在 fresh repository load 时 deterministic fail closed。
- StateTransition 不再捕获 malformed committed filter 后 `continue`；进程内出现绕过初始 validation 的损坏状态时抛出稳定 `committed_memory_filter_invalid:<index>`，不得降级为空 filter 或扩大查询范围。
- 真实临时 SQLite restart regression 同时覆盖 Mock/Real namespace：损坏 namespace 在 LLM、schema、DAX、Power BI 与新 Memory commit 前失败；合法 sibling namespace 正常恢复。legacy time string contract 保持不变。
- 根 README 已重构为稳定 Landing Page，并在 `AGENTS.md` 固化 maintenance contract；正式 PRD、07/08/09 与 CHANGELOG 状态同步。无 schema change、无 migration；M5 NOT STARTED。

## M4.4 — Restart / Crash Acceptance & M4 Final Closure（FINAL PASS）

- Acceptance 使用临时真实 SQLite 文件与 report filesystem：runtime A 写入后 dispose engine，runtime B 使用全新 engine/session/repository/service 恢复；没有用同一 Python repository 对象冒充 restart。
- committed Memory 及 version、terminal Snapshot replay/fingerprint conflict、recent/history/search/reports、archive/delete 与 Mock/Real 同 conversation ID 隔离均通过 restart 验收。Pending/Failed 不进入 committed context。
- Snapshot completion boundary：durable terminal Snapshot 即使尚未 complete process-local tracker，重启后仍可 replay；只有 in-flight claim 而无 Snapshot 时不产生 completed。Memory 存在但 Snapshot 缺失表示无法安全确认外部副作用，TurnPipeline 以 `IdempotencyCoordinationError` fail closed，不重执行、不生成 terminal duplicate。
- Report recovery boundary：新 persistent report Snapshot 只存 ID/reference/hash metadata，不存 HTML；replay 必须经 ReportRepository 从 filesystem 读取，并验证 metadata、linkage、namespace 与 content hash。验收修复了 adaptive Real report 错传未带 conversation/request context 的原 `ReportSpec`；missing/tampered HTML、corrupt metadata 或 linkage mismatch fail closed。
- Delete recovery boundary：migration `c8d4e6f2a109` 新增 `conversation_delete_intents`。DB 删除 transaction 同时保存 exact namespace 的 report IDs/counts；HTML cleanup 成功后才 finalize。unlink/finalize failure 或中间 crash 后，全新实例可按同 namespace 重试；pending intent 阻止 namespace 复活。SQLite transaction 不被描述为可原子覆盖 filesystem。
- Bounded guarantee：report create 的常规 metadata-save failure 会 best-effort unlink 已写 HTML；本轮未增加 durable create journal，因此不保证进程恰在 HTML rename 后、metadata commit 前退出时自动回收无引用文件。该窗口没有 metadata/Snapshot 成功态，读取仍 fail closed。
- Fresh DB → head、M4.3 `f4c3a2b1907d` → head、backend `1681 passed, 1 skipped` 均通过。M4 FINAL PASS；M5 NOT STARTED；不创建 Tag。

## M4.3 — Conversation History / Search API（已完成）

- 新增 `ConversationHistoryRepository` 抽象、SQLite 实现与 application query service；API/router 不直接访问 SQLAlchemy。SQLite 仍只是 persistence provider，不是 business/result/report factual authority。
- Conversation identity 为 `(runtime_mode, conversation_id)`；recent/history/search/archive/delete repository 方法的 `runtime_mode` 均为必填。Report history identity 为 `(source_mode, conversation_id)`，不得只按 `conversation_id` lookup/cascade。
- recent 只返回 unarchived conversations，排序固定为 `updated_at DESC, conversation_id ASC`；terminal snapshot 在同一 transaction touch exact conversation root。所有列表 page size 为 1—50，opaque keyset cursor 绑定 endpoint、namespace、search query 与 resource。
- history 是结构化 persisted view：`result_snapshots` 是 terminal turn ledger，同 request committed `work_memories` 只补充 analysis/model/version fields；report history 复用 M4.2.3 strict reconstruction。DB 没有逐字 message transcript，因此 API 不生成 transcript，也不暴露 HTML/ORM/payload JSON。
- search 不引入 FTS5；只对 committed `analysis_goal` 和 snapshot `answer` / `clarification_question` / `unsupported_reason` 做 deterministic SQLite contains query。Report HTML、DAX、任意 JSON 全文、未存储 prompt 均不在 search scope。
- archive 为幂等逻辑隐藏：从 recent/search 排除，但 direct history/reports 继续可读。delete 为物理删除：transaction 内清理同 namespace work memory/snapshot/pending clarification/report metadata/conversation root，随后由 report repository 删除同 source_mode 的精确 HTML 文件；另一 namespace 不受影响。Unknown conversation 一致 404。
- Migration `f4c3a2b1907d` 新增 nullable `conversations.archived_at` 与 recent/history/report namespace 复合索引；fresh DB 与 M4.2.3 schema upgrade 均通过。其 restart/crash 行为已由 M4.4 验收。

## M4.2.3 — Persistence Invariant Final Closure（已完成）

- `payload_json` 是 modern metadata reconstruction authority，DB dedicated columns 是 immutable integrity witness。payload 必须显式包含 `report_id`、`template_key`、`semantic_model_key`、`schema_fingerprint`、`source_mode`、`content_hash`、`relative_path`，且与 columns 严格一致；缺失或冲突均 `ReportStorageError` fail closed，不使用默认业务值或 derived path。
- `conversation_id` / `request_id` nullable；DB 有值时 payload 必须显式存在且一致。
- `report_id` 是 immutable resource identity；SQLite 与 InMemory repository 语义一致：完整 metadata 相同为幂等 no-op，任一 metadata/provenance/linkage 不同为 collision，禁止 overwrite。
- `source_mode` 仅允许 `mock | real`；M4.3 的 conversation → reports 查询必须使用 `(source_mode, conversation_id)` namespace，禁止 Mock/Real 串历史。
- 现有 report table 的 `source_mode` 与 `conversation_id` 已由 M4.3 report history/delete 查询直接作为 namespace predicate；未引入 FTS5。

## M3.4 — Adaptive Report Planning + Visualization/Layout Policy（已完成）

根因修复：M3.3 之前"固定四查询、固定两种横条、无法根据自然语言和语义模型能力生成不同报表"。M3.4 修复的是**报表规划能力**，不是 HTML/CSS。ADR-011 supersede ADR-010 的"一个 template 永久绑定一个 fingerprint + 固定四 queries"限制；ADR-010 的固定事实安全边界继续有效。

- 固定模板新定义：固定设计规则 + 允许能力目录（Design System / Allowed Section Catalog / Visualization Policy / Layout Policy / Theme Policy / Security Rules），不是固定输出内容。
- 最终 section 由"用户自然语言需求 ∩ runtime semantic capability ∩ sales_report allowed catalog"确定；"只看销售额"→ 单 KPI 报表，"生成完整销售分析报表"→ 能力驱动 dashboard。
- 新增 schema-aware capability engine（9 个 registry-owned sales capabilities：SALES_KPI / QUANTITY_KPI / ORDERS_KPI / AOV_KPI / TIME_TREND / CATEGORY_CONTRIBUTION / REGION_COMPARISON / TOP_PRODUCTS / TOP_CUSTOMERS）；缺能力 fail closed，绝不 Mock/占位。
- 新增受控 Report Intent weak signal：LLM 只输出 registry-owned section ID，未知 ID 丢弃，确定性匹配器是地板，"只看…"忽略 LLM 增量；单独计数 `llm_report_intent_call_count`。
- 新增 deterministic ReportPlan（requested / resolved / unavailable sections、去重 query requirements、provenance）→ 查询子集 → 复用 M2 密封链。
- 新增 VisualizationPolicy（KPI Card / Line / Donut≤8 / Column / HBar，禁止所有 grouped→hbar）、LayoutPolicy（KPI 行 → 全宽趋势 → 2 列对比/排行对）、ThemePolicy（dataviz 验证调色板）。
- `SalesReportRenderer`（原 FixedSalesReportRenderer 更名）支持 charts：inline SVG line/donut、CSS column/hbar、KPI cards；无 JS/CDN/外部资源。
- 时间趋势来自 Power BI query → QueryResult → VerifiedFactSet；Renderer 不聚合；只对已验证时间点做确定性显示排序。
- 最小通用扩展：`CanonicalQueryPlan.dimension_tables` / `dimension_order`（star-schema 重名列消歧；None 时 M2 行为不变）；ChartSpec 增加结构化 `visual_type` / `business_role` / `series` / `layout_hint`。
- 双模型 Real acceptance：Simple PBIX 保持 M3 基线四查询行为；Rich PBIX（fingerprint `31505f79...`）解析 9 sections / 9 查询，4 种 visual，全部真实事实；事实类 LLM counters 全 0。

## M3.3 — Report Template V2 / Non-redundant Information Architecture（已完成）

M3.3 未新增业务查询、DAX、filter、template、LLM authority 或事实来源；重构 sales_report 信息架构，引入 capability-aware section 设计。

- 新增 `backend/app/report/capability.py`：SectionCapability 概念（M3.4 已重构为 schema-aware capability engine，见上）。
- `FixedSalesReportRenderer` 改为 section-capability 感知渲染：每 section 只保留一种主要视觉表达（horizontal bar），移除与 bars 重复的同源明细 table。
- `sales_report.html` 模板重写：双列 KPI → 品类 bars → 产品 bars → metadata footer；响应式窄屏 Flex 换行；无 JS/CDN/外部资源。
- 多语义模型防伪测试：Model A 当前 schema 所有 section 正常；Model B 多 Date/Region/Customer 字段不自动生成 section；Model C 缺 Category/Product 时 contract validation fail closed。

## M3.2 — 已完成 hardened visual acceptance

M3.2 未新增模板、查询、DAX、业务语义、图表类型、资源 API、前端或持久化能力；只把 M3.1 已有 Category / Top Product `ChartSpec` 与同源 table rows 以固定 CSS 横条呈现，并完成静态安全、Real PBIX、桌面/430px 视觉、文档与 CI 收口。

## M3.0 — 已完成合同基线

- 唯一 production template 为 `sales_report`；legacy keys 仅历史 Mock compatibility，production unavailable。
- TemplateContract 绑定 `local_desktop_model` 与 M3 PBIX fingerprint（M3.4 起 fingerprint 不再是 contract gate，见 ADR-011）。
- ReportDataPlan 固定四查询（M3.4 起由 capability 解析决定查询子集）。
- 缺对象、类型、model mismatch 时不生成 partial plan。

## M3.1 — 已完成正式生成链

### 唯一正式链（M3.4 更新）

```text
Natural Language / Template Grounding
→ Bounded Report Intent weak signal
→ deterministic ReportPlanner → Canonical ReportPlan
→ N × CanonicalQueryPlan → N × Deterministic DAX + Independent Layer 3
→ N × ToolGateway → PowerBIAdapter → Power BI
→ N × QueryResult → N × VerifiedFactSet
→ deterministic SalesReportData
→ deterministic ReportSpec（VisualizationPolicy 选 visual）
→ SalesReportRenderer（design system）→ static UTF-8 HTML
→ ReportArtifact / ReportRepository
→ report_id / view / download
→ Memory / Snapshot
```

### Fixed sales content（M3.4 更新）

- 标题：销售分析报表。
- Section 由用户需求 ∩ runtime capability 决定；完整能力时：4 KPI（总销售额/总销量/总订单数/平均订单金额）→ 月度销售趋势 → 品类销售贡献 → 区域销售对比 → Top 5 产品 → Top 5 客户。
- Metadata：数据来源、source_mode、contract version、generated_at。
- TopN 仅显示 `result_position`；不制造严格业务名次、趋势或原因分析。

### Resource contract

- `ReportArtifact` 固定 report_id、template/contract/model/fingerprint、N 组 QueryResult/FactSet IDs、source_mode、content type/hash 与 created_at。
- 正式 HTML 原子保存于 `local_state/reports/<report_id>.html`；验收副本只能复制同一 Renderer 输出到 `m3_sales_report.html`。
- `GET /api/reports/{report_id}` 查看；`GET /api/reports/{report_id}/download` 下载。
- 同 request_id 重放只读 Snapshot，复用同一 report_id，不重新执行 Power BI 或生成第二 artifact。

### Truth Boundary（M3.4 更新）

LLM 对 template canonical authority、查询集合、CanonicalQueryPlan factual slots、DAX、KPI/rows、结果顺序、趋势、因果、Report factual truth、HTML/CSS、chart data 和 report reference 的 authority 均为 0。LLM 唯一新增：Report Intent weak-signal draft（registry-owned section ID），单独计数。

## 永久阶段边界

- 不使用 LangGraph、多 Agent 或 PydanticAI。
- 不复制 Pipeline/Service，不绕过 TurnPipeline、ToolGateway、PowerBIAdapter、Independent Layer 3、VerifiedFactSet 或 Memory/Snapshot。
- M5.5 与 M5.6 已完成并冻结；M5.7 只允许简易报表视觉与模板必选；M5.8—M5.10 仍不得进入。
- 一个 milestone 不得同时大规模修改 Semantic、MCP、LLM Provider、Presentation、Report、Resource lifecycle；只有 M5.10 全部门禁完成后才允许宣告 M5 FINAL。
- 当前报表针对各 PBIX 全量数据；不新增动态月份、Category filter、comparison、用户自由 ReportDataPlan 或任意 DAX。
- M3 不做 PDF、自由 HTML、用户模板、JavaScript、复杂图表框架、React UI 或 Remote MCP。
- M0—M3 已正式封板（Tag: `m3.4-m0-m3-final-seal`）；M4 backend 已在 M4.4 FINAL PASS，M4.4.2 truth/persistence boundary final closure FINAL PASS；M5.0—M5.3.3 已完成；禁止 force push。

---

### M5.5 completion evidence

- explicit unresolved → clarification/no-match → ZERO DAX/QueryResult/Memory commit；`火星区` fail closed，`华南/华南区/南区` 由 runtime members 解析。
- Real Rich PBIX 四轮 slot inheritance、TopN、temporal filter/grouping、prediction/delete unsupported 与 READ_ANALYSIS 问法通过。
- Sales/Education/Inventory、未知 holdout、schema mutation、backend/frontend/golden/governance、Local MCP readonly smoke 与 Real Browser/manual acceptance 全部通过；acceptance residual=0。
- 无 Localization、Presentation redesign、Resource UX、Report Visual、MCP performance/cache/session worker、M5.10 或 Remote MCP 实现。

*最后更新：2026-08-26 | M5.7 COMPLETE — M5.8—M5.10 NOT STARTED；M5 FINAL 尚未成立*
