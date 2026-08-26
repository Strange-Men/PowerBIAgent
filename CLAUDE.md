# CLAUDE.md — PowerBIAgent 通用代码 Agent 开发协议

> **Claude / Codex / 其他代码 Agent 均必须遵守本协议。每个新会话修改任何文件前，必须执行冷启动协议。**

---

## 一、冷启动协议

每个新的代码 Agent 会话开始后，修改任何文件前必须：

### 1. 环境检查

```bash
git status
git branch
git rev-parse HEAD
```

### 2. 必须阅读的文件（按顺序）

1. `AGENTS.md`（仓库级入口）
2. `PROJECT_CHARTER.md`
3. `CLAUDE.md`（本文件）
4. `docs/09_context_handoff.md`
5. `docs/08_development_roadmap.md` 当前阶段
6. `docs/ai_development_error_ledger.yaml`：读取结构、当前有效治理规则及与当前轮相关条目；不要求完整复盘所有历史错误
7. `docs/adr/README.md` 及当前阶段涉及的 ADR
8. 当前轮 Prompt 指定文档
9. 当前轮涉及的生产代码

不要默认读取完整 CHANGELOG、`docs/archive/`、全部测试、全仓源码或历史 Commit diff；需要时再局部读取。

### 3. 状态核实

- 检查上一轮固定 Commit 是否存在
- 检查 `docs/09_context_handoff.md` 是否标记上一轮完成
- 检查 Git 工作区是否干净
- 检查 `D:\Conda` 和 `PBIAgent` 环境状态

### 4. 复述（不超过200字）

- 项目目标
- 当前进度
- 本轮允许范围
- 本轮禁止范围
- 当前本地开发环境

### 5. 防偏移检查（不超过200字）

开始开发前必须输出：

- 本轮命中了哪些历史错误 ID
- 哪些 ADR 限制本轮修改
- 本轮可能产生的架构偏移
- 本轮禁止触碰的边界

### 6. 阻塞条件

- 上一轮未完成、Commit 不存在或交接文档冲突 → 停止
- 无法读取错题本或格式错误 → 停止
- **注意：不得将"没有上一轮 Tag"视为阻塞，因为普通轮次本来不创建 Tag。**

---

## 二、Commit 规则

### 格式

- 正常轮次：`Mx.y_中文描述`
- 专项修复（仅限用户明确批准）：`Mx.y.z_中文描述`
- 代码 Agent 不得自行增加修复版本号
- 使用一个下划线连接版本号和中文描述
- 当前轮 Commit 标题必须与当前轮固定名称一致

### 提交前检查清单

1. 明确文件白名单暂存（禁止 `git add .` 和 `git add -A`）
2. 检查 `git diff --cached`，确认无 `.env` 等 Secret 文件
3. 检查 `git diff` 和新增文件
4. 执行 `python scripts/check_repository_safety.py`
5. 检查 docs 文件名全部为英文
6. 检查没有提前实现后续轮次内容
7. 更新 `CHANGELOG.md`
8. 更新 `docs/09_context_handoff.md`
9. 检查 Commit 标题准确
10. 检查本轮没有新增 Tag

### 提交前文档先行规则（硬规则）

1. README、CHANGELOG、docs/08、docs/09 和版本号必须在 Commit 前全部同步完成
2. Commit 前必须搜索并清除以下失效内容：
   - `本轮提交`
   - `待回填`
   - `等待Push`
   - `等待CI`
   - 错误旧版本状态
3. 已知历史 Commit SHA 和 CI Run ID 必须在 Commit 前验证并回填
4. 当前 Commit 自身 SHA 不得使用占位符，也不得手工推测
5. 当前 Commit SHA 和当前 CI Run ID 只记录在最终报告与 Annotated Tag 中
6. Commit 完成后不得再为回填文档追加 Commit
7. Commit 后只允许 Push、CI 验证、Tag 创建和 Tag Push
8. Commit 后发现文档错误必须停止，由用户决定是否新开修复版本

---

## 三、Tag 规则

- Tag 仅用于大版本封板（M0 封板、MVP 封板、正式可发布版本等）
- Tag 名称描述部分全部使用中文
- 禁止：为小轮自动创建 Tag、创建临时/测试 Tag、删除或重写历史 Tag

---

## 四、Git 安全规则

禁止执行：
- `git push --force` / `git push -f`
- `git reset --hard`
- `git clean -fd`
- 删除或重写历史 Tag
- 未经说明的大规模重构

禁止提交：
- 真实 Secret、API Key、Token
- 真实业务数据
- `.env` 文件

---

## 五、Secret 与 API Key 绝对规则

### 1. Secret 永不进入仓库

永远禁止提交或上传：

- `.env`、`.env.local`、`.env.development`、`.env.production` 等真实环境文件
- API Key、Token、密码、Client Secret
- OAuth Refresh Token、Authorization Header、Bearer Token
- Cookie 和 Session、证书私钥、云服务凭据
- `.har` 文件、网络抓包、HTTP Dump、Debug 响应转储
- Smok 输出、Trace 日志、真实 Prompt 全文、真实模型原始响应
- 真实业务数据、Power BI 导出文件（.pbix）、数据库文件、生成报表
- 用户私人工作资料、截图包含的 Secret

`.env.example` 是唯一允许提交的环境模板，只能包含空值、公开默认值或明显占位符。

### 2. 代码 Agent 不得读取 Secret

Claude / Codex / 其他代码 Agent **只能**检查 `.env` 是否存在/被忽略/被跟踪；**不得**打开、读取、搜索 `.env` 文件内容或输出任何环境变量真实值。

### 3. API Key 只能后端运行时使用

DeepSeek API Key 只能由后端 `Settings` 以 `SecretStr` 类型读取，通过 HTTPS Authorization Header 发送给 DeepSeek 官方 API。不得进入 GitHub、CI 日志、前端、日志、Trace、测试 Fixture。

### 4. 前端禁止持有 Provider Secret

以下名称或同类形式禁止在前端出现：
```
VITE_DEEPSEEK_API_KEY / REACT_APP_DEEPSEEK_API_KEY / NEXT_PUBLIC_DEEPSEEK_API_KEY
PUBLIC_DEEPSEEK_API_KEY / NUXT_PUBLIC_DEEPSEEK_API_KEY
```

### 5. 日志与测试禁止泄漏

禁止将 API Key、Authorization Header、完整 Prompt、真实模型原始响应写入日志/Trace/测试。只允许脱敏元数据（provider、model、status_code、token 计数、error_type）。

### 6. 提交前安全检查

- 禁止 `git add .` 或 `git add -A`
- 必须使用明确文件白名单暂存
- Commit 前必须执行 `scripts/check_repository_safety.py`

---

## 六、外部证据修复门禁

任何 Bug 修复，修改代码前必须：

1. **查官方最新文档、官方源码或维护者 Issue** — 第一优先级为官方 API 文档/错误码说明/GitHub Issue；第二优先级为框架维护者确认的解决方案
2. **保存本地错误证据**
3. **建立最小复现**
4. **说明官方方案为何适用于当前项目**
5. **只做最小修改** — 不趁修复之机扩大重构范围
6. **用回归测试验证**

**没有找到可信权威依据时：** 立即停止，不猜测修改。

---

## 七、两次修复上限

同一错误最多两次代码修改：

- 同一根因/堆栈/失败测试不得改名为新错误以重置次数
- 第一次修改后验证失败，计为第 1 次失败
- 第二次修改后仍失败，必须立即停止
- **第一次失败后，第二次修复前必须：** 重新检查根因、查找额外官方资料、说明第一次方案为何无效、提出有证据支持的不同方案
- **第二次仍失败后禁止：** 第三次修复、继续重构、扩大修改范围、创建新错误 ID 规避限制、Commit 和 Push

---

## 八、开发核心原则

- 每个新代码 Agent 会话开始前必须执行冷启动复习
- 必须阅读固定入口文件后才能修改代码
- 当前轮未验收不得进入下一轮
- **小步迭代** — 每轮只完成一个明确目标
- **模块拆分** — 每个文件职责单一
- **状态摘要** — 每轮结束更新交接文档
- **安全底线** — 不提交 Secret、不执行危险命令、不绕过 Harness
- **检查报错** — 不压制错误、不跳过失败测试、不掩盖异常
- 不得根据聊天记忆替代仓库文档
- 重大变更必须新增 ADR（`docs/adr/`）
- 每轮结束必须更新 `docs/09_context_handoff.md`
- 每轮有效开发必须有 Commit
- Tag 只在大版本封板时创建

---

## 九、文档来源优先级

当文档内容存在冲突时，严格按 `AGENTS.md` 的权威文档顺序处理。不得自行选择方便开发的版本；无法判断时停止并核实，不得静默改变产品方向。产品方向按文档优先级判断，代码是否真的实现必须以真实代码和测试结果验证。

---

## 十、Conda 开发环境

- Conda 安装目录：`D:\Conda`
- 项目环境名称：`PBIAgent`（Python 3.11）
- 不在 base 环境安装项目依赖
- 不在业务代码中硬编码 Conda 路径

---

## 十一、项目目录结构

```
PowerBIAgent/
├── AGENTS.md
├── PROJECT_CHARTER.md
├── README.md
├── CLAUDE.md
├── CHANGELOG.md
├── .gitignore
├── .env.example
├── environment.yml
├── pyproject.toml
├── docs/                       # 英文文件名，中文正文
│   ├── 00_product_requirements_document.md
│   ├── 01_product_scope_and_frontend_skeleton.md
│   ├── 02_technology_selection_and_system_architecture.md
│   ├── 03_intent_recognition_and_memory_system.md
│   ├── 04_powerbi_mcp_and_api_contracts.md
│   ├── 05_harness_test_and_acceptance.md
│   ├── 06_security_git_and_development_standards.md
│   ├── 07_milestones_status_and_open_questions.md
│   ├── 08_development_roadmap.md
│   ├── 09_context_handoff.md
│   ├── index.md
│   ├── ai_development_error_ledger.yaml
│   ├── adr/
│   ├── specs/
│   │   ├── 10_frontend_visual_and_interaction_spec.md
│   │   └── 11_structured_answer_contract.md
│   ├── milestones/
│   │   └── m2/12_m2_powerbi_mcp_integration_plan.md
│   ├── archive/
│   └── assets/
├── frontend/
├── backend/
│   ├── app/
│   │   ├── agent/
│   │   ├── intent/
│   │   ├── llm/
│   │   ├── memory/
│   │   ├── powerbi/
│   │   ├── report/
│   │   ├── harness/
│   │   ├── schemas/
│   │   ├── core/
│   │   └── application/
│   └── tests/
│       ├── unit/
│       ├── integration/
│       ├── api/
│       └── fixtures/
└── scripts/
    └── manual_smoke/
```

---

## 十二、文档治理规则

- `docs/00`—`09` 与 `docs/index.md` 是全局主干；`docs/08_development_roadmap.md` 和 `docs/09_context_handoff.md` 路径固定。
- 专项规范进入 `docs/specs/`；阶段计划进入 `docs/milestones/<milestone>/`；长期架构决策永远进入 `docs/adr/`；历史资料进入 `docs/archive/` 且默认不读。
- 禁止新增 `docs/13_xxx.md`、`14_xxx.md` 等根层编号文件，除非用户明确扩充 00—09 主体系。
- 原始 PRD 只在 `docs/archive/original/PRD.md`；正式唯一 PRD 是 `docs/00_product_requirements_document.md`。
- 提交前执行 `python scripts/check_documentation_governance.py`。

---

## 十三、阶段边界规则

- 当前轮只能开发用户明确批准的 Milestone。
- M2 不得提前开发 M3 报表正式渲染、M4 持久化会话或 M5 React 前端。
- M2 可以在方案确认后接入 Power BI、OAuth 与必要生产依赖。
- 不得借 M2 名义重构已封板的 Intent → QueryPlan → DAX → Answer / ReportSpec 主链。
- 不得绕过 TurnPipeline、ToolGateway、Harness 或既定 Memory/Snapshot 控制面。
- 未经用户明确批准，不得创建 Tag 或 Release。
- 任何阶段均禁止 force push。

### M5.3.3 多轮与资源生命周期硬规则

- 当前输入明确表达 > 当前 bounded LLM semantic draft > committed Memory；Memory 仅补省略项，不得覆盖当前 turn。
- 同 conversation 必须区分 fresh question、follow-up、replace；证据不足 clarification。不得默认继承全部旧 slot。
- 预测、写入、PBIX/Measure 修改、删除数据、任意代码与自然语言 report delete 在 Memory/Grounding/DAX 前 fail closed；committed/pending 不得改变该结论。
- archive 是可恢复的逻辑隐藏；delete 是永久清理；独立 report delete 只属于显式人工资源 API，不进入 ToolGateway，LLM 无权限。
- 前端 history response 必须验证 active conversation 与 generation；open/new/delete/archive/restore/model switch 必须使旧请求失效。
- local_state 只允许 persistence/reports/runtime/archive。测试 artifact 必须 Create → register ownership → use → teardown → verify cleanup；Artifact Gate 只读检测，不自动删除用户数据。

### M5.4 多会话并发与资源管理硬规则

- 会话 UI/runtime state 必须按 conversation 隔离；不同 conversation 可并发，同一 conversation 串行。`activeConversationId` 不得兼任全局请求状态。
- 首次发送使用前端 UUID 作为正式 Chat `conversation_id`，Sidebar 立即显示 pending session，不新增 provisional backend entity。
- history/navigation 可 Abort 并校验 generation/active identity；business chat 归属 conversation，切换窗口不取消、不自动跳转。
- 用户卡片承载设置、已归档和资源管理入口；Sidebar 仅导航，最近会话/报表独立滚动或折叠。
- 批量操作每个 destructive execution wave 最多 20 项，只协调现有单资源 API；成功项移除、失败项保留并显示原因，不绕过 durable delete，archive 不等于 delete。该上限不得限制历史浏览或用户一次确认的选择总量。
- report tombstone 只是历史展示，不重建 ReportArtifact。`display_title` 只是 presentation metadata；report_id/HTML/content_hash/ReportSpec/VerifiedFactSet 不变。
- report/conversation rename/delete/restore 只能由明确 UI 用户操作发起，不进 ToolGateway/LLM allowed tools；自然语言不得执行资源变更。
- M5.5 的语言理解、中文字段、性能/cache、单指标策略与 report HTML 视觉继续 Deferred。

### M5.4.1 全量资源与测试 ownership 硬规则

- Sidebar Recent 与 Settings Resource Manager 必须分离：前者只加载 bounded recent subset，后者独立使用 namespace-scoped cursor pagination 访问全部 active/archived conversation 与 report，并显示 `total_count`、已加载数量和是否还有更多。
- “全选当前已加载”不得简称“全选全部”。只有完整解析后端查询条件并取得全部匹配 ID 时才允许“选择全部匹配项”；否则用户可继续加载并多选任意已浏览资源。
- 一次确认可包含超过 20 项；前端内部按最多 20 项一组、bounded concurrency 调用正式单资源 mutation API，并逐项汇总成功/失败。禁止新增 bulk delete backend shortcut 或绕过 durable intent。
- 自动化创建的 conversation/report/HTML/SQLite namespace 必须在创建时记录 `test_run_id` 与 automation ownership；teardown 必须位于 `finally`，通过正式 API/repository cleanup 后验证 residual=0。
- Artifact Governance 对 test-owned conversation、report metadata、HTML、SQLite namespace、pending delete intent、orphan 和 cleanup failure 任一残留 fail closed；Gate 只读，不自动清理用户数据。
- 历史资源清理必须有 ownership metadata、已知 test namespace/ID、fixture 或 report linkage 证据。仅凭标题或内容猜测为测试资源时必须保留。M5.5 继续 Deferred。

### M5.4.2 重建线与后续开发治理硬规则

- 新开发线固定从 M5.4.1 commit `cab40b076f054a3ebdab0bf6d2b0354f4b2d49db` 开始。`m5/frontend`、`a197db3`（原 M5.5）和 `6d1620a`（原 M5.5.1）是必须保留的实验/审计历史；不得 force push、revert、删除、重写或整体 cherry-pick。
- M5.4.2 只允许 Git 基线和文档/治理变化。若完成本轮必须修改 `backend/app/**`、`frontend/src/**`、backend/frontend tests、schema 或 migration，立即停止并汇报。
- 新 M5.5—M5.9 按 Semantic → Presentation/Localization/Resource UX → Report → MCP performance/resilience → 专业销售模板分阶段推进；一个 milestone 禁止同时大规模修改 Semantic、MCP、Presentation、Report、Resource lifecycle 多个域。
- explicit unresolved semantic requirement 必须 clarification/no-match 且 ZERO DAX；不得静默移除筛选后执行更宽查询。
- Generalization Gate 至少覆盖 Sales/Retail、Education、Inventory/Operations，并在最终阶段使用开发期未知业务模型 holdout。测试答案不得写入 LLM Prompt，生产代码不得在正式 model-scoped glossary/test fixture 外写死业务字段、member 或答案。
- 每轮证据顺序固定为 `Spec → Failure reproducer → Regression tests → Minimal implementation → Focused Real → Cross-domain → Full gates → User manual acceptance → commit`。单独的全量测试通过数不足以宣告 COMPLETE；Real Browser/人工验收是正式 Gate。
- 新增 M5.9 后，只有 M5.9 完成后才允许宣告 `M5 FINAL`。长期合同见 `docs/specs/13_m5_generalization_and_acceptance_contract.md`。

### M5.5 Semantic correctness 硬规则

- 当前明确证据 > 当前 bounded semantic draft > compatible committed Memory。explicit unresolved/ambiguous object 或 member 必须 clarification/no-match，并证明 DAX、QueryResult 与 Memory commit 均为零。
- canonical object/member identity 只来自 runtime schema、model-scoped glossary、runtime members 与 deterministic rules；bounded LLM 只能选择代码给出的候选 ID。
- measure、dimensions、filters、time、ranking、sort 必须独立 KEEP/REPLACE/CLEAR；fresh self-contained query 不机械继承旧槽，当前 no-match/ambiguity 不得被 Memory 掩盖。
- 本轮禁止 Localization、Presentation/Resource UX、Report visual/template、MCP performance/cache/session worker、Remote MCP、prediction、write-back 与 arbitrary DAX。
- M5.6 action menu 与 Settings nested-scroll 修复、M5.9 专业销售模板均只在路线与合同中固化，M5.5 不实现。

### M5.6 Presentation、Localization 与 Resource UX 硬规则

- M5.5 semantic authority 已冻结。本轮不得修改 TurnPipeline、Grounding/StateTransition、runtime member authority、Deterministic DAX、VerifiedFactSet factual authority、Local MCP readonly/stale fail-closed 或 report renderer。
- `canonical_name` 与 `display_name` 严格分离；display localization 只能绑定 runtime 已存在的 model/object/schema identity。优先级固定为 Power BI metadata → model-scoped glossary → persisted registry → bounded display translation → safe humanized fallback；schema/object identity 变化使缓存失效。
- deterministic formatter 只产生 presentation value，支持 integer、decimal、percentage、currency/general amount、date、month 与 null；不得改写 QueryResult/VerifiedFactSet 原值、顺序或 provenance。
- 展示职责为 Answer 洞察、Table 明细、Chart 趋势/关系。scalar 不再附 KPI card；grouped/trend 的 Answer 不得逐行复述 table，raw ISO timestamp 不得进入可见文本。
- Recent Reports 与 Settings 使用同一正式 report source；Recent conversation 固定 `updated_at DESC, created_at DESC, stable_id DESC`。failed conversation 必须持久化并可 rename/archive/restore/delete，不得用标题或内容猜状态。
- conversation/report 共用 Portal-based `FloatingActionMenu`；Settings 使用 fixed shell + independent content/list scroll + 始终可达的 resource toolbar。正式 Gate 覆盖首中末行、滚动三位置、100%/125% zoom 与规定 viewport。
- checkpoint 固定为 P1 docs/contracts → P2 formatter/localization → P3 presentation density → P4 resource truth/sorting → P5 failed lifecycle → P6 floating menus → P7 Settings layout → P8 cross-domain → P9 focused → P10 full/governance → P11 Real/manual → P12 final docs/commit/push。任一 FAIL 不进入下一项。

---

*最后更新：2026-08-26 | M5.6 COMPLETE — M5.7—M5.9 NOT STARTED*
