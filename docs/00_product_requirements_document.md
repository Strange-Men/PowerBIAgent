# 00 — 产品需求文档 (PRD)

> **原始 PRD 历史路径：** `docs/archive/original/PRD.md`；本文件是正式唯一 PRD。
> **修订版本：** v1.7
> **修订日期：** 2026-08-24
> **需求来源：** 用户原始 PRD + M0.1 开发准备 Prompt
> **本轮修订范围：** 固化 M5.3.3 多轮省略项继承、readonly unsupported、archive/restore/delete、独立 report delete、异步 conversation 隔离与 artifact lifecycle；North Star 与 factual authority 不变
> **当前确认状态：** 正式唯一 PRD；实现状态以 accepted ADR、08/09 与 fresh 验证为准

---

## 一、项目名称

Power BI 数据分析 Agent MVP（PowerBIAgent）

## 二、项目背景

公司内部 Power BI 已沉淀部分语义模型，但普通业务人员仍需要通过 Power BI 页面、固定报表或数据人员获取数据。

本项目希望通过 LLM、Power BI MCP 和 Web 对话页面，让用户直接使用自然语言查询 Power BI 数据，并生成固定模板的静态 HTML 报表。

## 三、项目目标

完成一套可运行、可验证的 MVP，证明以下链路可行：

当前 M0—M5 已验证的主链为：

```text
Natural Language
→ Intent（语言 weak signal）
→ Runtime Schema / Semantic Catalog
→ Semantic Grounding
→ deterministic StateTransition
→ Canonical QueryPlan
→ Deterministic DAX
→ Independent Layer 3
→ Power BI
→ QueryResult
→ VerifiedFactSet
→ fact-bounded Answer / ReportSpec
→ successful Memory commit
```

固定模板静态 HTML 报表已在 M3 完成并封板；M4 已完成本地持久化、恢复、history/search 与 restart/crash acceptance。M4.4.2 最终关闭 committed Memory 完整 payload、mandatory namespace、terminal Snapshot integrity 等 fail-closed 边界，不改变上述事实链。

MVP 主要供公司内部少量人员使用，暂不处理复杂客户权限和多租户问题。

## 四、目标用户

公司内部需要查看业务数据，但不熟悉 Power BI、DAX 或数据模型的业务人员。

## 五、核心使用场景

### 5.1 数据问答

用户从后端发现的当前可连接 Power BI Desktop / PBIX 对应语义模型中选择一个模型后，输入自然语言问题。浏览器不直接读取 `.pbix`；Local MCP / PowerBIAdapter 安全枚举所有当前 Desktop 实例，为每个实例生成不泄露连接属性、当前后端进程内确定的 opaque key。schema、member lookup 与 DAX 每次都重新执行 `ListLocalInstances`，只允许该 key 对应的稳定 identity 唯一匹配后 Connect；目标消失、identity 变化、找不到或匹配不唯一均 fail closed，不按顺序或 display name 猜测模型。

- "本月销售额是多少？"
- "各区域销售额排名如何？"
- "最近六个月销售趋势怎么样？"

Agent 查询真实数据，返回文字结论和数据表格。

> **当前已封板的数据问答能力边界：** 已验证 grammar 仅包含 Measure、Dimension、`EQ` Filter、可确定解析的 TimeRange、single-measure Sort/TopN。系统可安全处理“总销售额是多少”“按 Category 看销售额”“销售额最高的前 3 个 Product”等受限问题；TopN 只表达 QueryResult 顺序，不制造严格 business rank。“同比/环比”“哪个区域下降最多”、非 `EQ` Filter、任意 DAX、因果分析与通用趋势推断仍未实现。

### 5.2 多轮追问

用户可以继续输入：

- "只看华南。"
- "改成今年的数据。"
- "哪个区域下降最多？"（未来 comparison/trend 能力，M2 不宣称支持）

系统只对真正省略的兼容槽继承 last successful committed state。同一 conversation 不等于自动 follow-up；必须区分 fresh question、follow-up 与 replace。当前用户明确表达优先于 bounded LLM semantic draft，二者均优先于 Memory。fresh question 清除未在当前轮表达的旧 time/filter/dimension/sort/top_n；证据不足时 clarification，禁止为方便执行而机械继承。

自然时间理解允许 LLM 输出受限 `TimeIntentDraft`（absolute month/year、relative month/year、quarter、recent months、bounded range），但最终 Date field 和 `TimeRangeSpec` 仍由 runtime schema、固定 clock/calendar 与 deterministic resolver 决定。LLM 不拥有 canonical 时间或对象 identity。

### 5.3 报表生成

普通问答、多轮分析和报表生成由后端 intent 自动识别，前端不预先决定“问答还是报表”。用户可以主动选择一个已登记固定模板作为可选 `report_template_key` override；未选择只表示不传 override，不代表“禁止生成报表”。当 intent 为报表生成时，后端仍可按业务规则选择默认模板并生成静态 HTML 报表。当前 production catalog 只有 `sales_report`（“销售分析报告”），未来可扩展多个已登记模板。

## 六、前端设计

### 技术栈

React + Vite

### 页面形态

极简白色对话页面，整体交互参考 GPT 网页版。桌面端包含固定窄左侧栏（约占 15% 宽度）和主对话区。

**未开始对话时：** 输入框显示在页面中间，同时展示欢迎语。
**开始对话后：** 消息内容在页面中展示，输入框固定在页面底部。

### 左侧栏

- PowerBIAgent 标识
- 新聊天入口
- 搜索聊天（M4 后端搜索能力，M5 前端界面）
- 项目分区
- 最近报表（M3 后端报表资源能力，M5 前端界面）
- 最近对话（M4 后端会话持久化能力，M5 前端界面）
- 展示型 transcript、自动标题与 namespace-scoped 重命名、归档、删除
- “已归档”入口与恢复；归档保留 History/Memory/report/HTML，删除才永久清理
- 最近报表的显式人工删除；只删除 report，不删除所属 conversation
- 用户信息和菜单

> **M3/M4/M5 边界：** M3 完成报表渲染、资源 ID、查看/下载等后端能力；M4 完成会话历史、搜索和持久化等后端能力；左侧栏 React UI、最近报表/对话、搜索和会话管理已在 M5 实现。展示型 transcript/title 不进入 Memory 或业务事实链。

### 输入框组件

1. **"+"按钮** — 点击弹出选择菜单，分为"数据模型"和"报表模板"两个分组
2. **模型选择菜单** — 圆角框设计。MVP 阶段仅 DeepSeek 为正式用户模型。Mock 仅用于开发和测试，不作为正式用户模型展示。GPT-5.6 等未来模型未真实接入前应隐藏或明确禁用
3. **文本输入区域** — 用户输入自然语言问题
4. **发送按钮** — 黑色圆形，提交问题

### AI 回答展示形式

AI 回答不是只能返回纯文本。同一条 AI 消息现在可以按实际后端产物组合：

- 自然语言文字结论
- 关键指标摘要（metrics）
- 简单数据表格（table）
- 基础图表（chart，当前只支持柱状图/折线图）
- 报表附件卡片（report_attachment）

表格直接嵌入 AI 回答，白色背景，浅灰横向分隔线。图表直接嵌入 AI 回答，颜色克制优先单一蓝色，不使用 3D 图表。报表附件以轻量横向卡片展示，包含文件图标、标题、类型、"查看报表"和"下载 HTML"操作。

> **重要：** M5.3 已实现只读 `PresentationEnvelope`。metric/table/chart block 只引用由 QueryResult 与 VerifiedFactSet 直接投影的一份 dataset；额外的未验证 QueryResult 字段不会进入 presentation。系统不从 answer/audit 反解析数据，也不允许 LLM 或前端造数。饼图、散点图、任意 ChartSpec、前端聚合与通用趋势推断仍未实现。

### 前端开发策略

前端已在 M5 完成 React 实现、Real 联调、结构化结果、responsive、accessibility 与状态视觉收口；后续不扩展新前端能力，除非另有明确里程碑批准。

## 七、后端设计

### 技术栈

FastAPI

### Agent 架构

**使用成熟框架支持的单 Agent。**
- **不使用 LangGraph**
- **不使用多 Agent**
- **不从零手写复杂 Agent Runtime**
- Agent 必须包含明确、独立、可测试的意图识别

### 主要模块

1. **API 层** — 接收前端请求和返回结果
2. **Agent 编排层** — TurnPipeline 控制状态读取、Intent、authoritative Grounding、确定性执行、事实构建、输出与成功提交
3. **LLM Provider 层** — 通过统一接口封装模型调用。**当前正式用户模型只有 DeepSeek**。Intent/语言草稿是 weak signal；bounded selector 只能在 Catalog-owned、metadata-backed candidate ID 中受限选择。LLM 不拥有 canonical business semantics、Real DAX 或外部事实。Mock LLM 仅用于开发和测试，不作为正式用户模型展示
4. **Power BI MCP Adapter** — 连接 Power BI MCP，获取语义模型结构，执行 DAX 查询，处理异常
5. **Memory 模块** — 只在 Grounding、DAX、Layer 3、Power BI、FactSet 与 factual output 全链成功后提交当前分析状态；PendingClarificationContext 与 committed Memory 分离
6. **报表生成模块** — M3 已实现受 VerifiedFactSet / QueryResult 约束的固定模板静态 HTML 渲染与资源契约；M4 persistence 只保存状态/metadata，filesystem 继续拥有 HTML authority
7. **展示投影模块** — M5.3 已实现 QueryResult/VerifiedFactSet 直接来源的 `presentation` contract，以及 text/metric/table/bar/line/report attachment 动态块；只拥有 UI projection 权限
8. **资源生命周期模块** — M5.3.3 将 archive/restore/conversation delete 与独立 report delete 分离；report delete 是用户显式资源 API，不是 Agent tool，LLM 无调用权限

### 单 Agent 执行流程

```
接收用户请求并读取 last successful committed state
→ Intent 分类与语言 weak signal
→ ToolGateway 获取 runtime schema / bounded members
→ Semantic Grounding；歧义或未解析时 clarification / fail closed
→ deterministic StateTransition 形成 Canonical QueryPlan
→ Deterministic DAX + Independent Layer 3
→ ToolGateway → PowerBIAdapter → Power BI
→ QueryResult → VerifiedFactSet
→ fact-bounded Answer / ReportSpec
→ 仅完整成功后提交 Memory / Snapshot
→ 返回 API
```

## 八、Agent 工具

MVP 只开放以下工具：

| 工具 | 功能 |
|------|------|
| `get_semantic_model_schema` | 获取 Power BI 语义模型中的表、字段、度量值和关系 |
| `execute_dax` | 执行经过校验的 DAX 查询 |
| `render_report` | 根据校验后的 ReportSpec 和查询数据生成静态 HTML 报表 |

Agent 不允许调用系统命令，不允许执行任意 Python、Shell、SQL 或 JavaScript。

## 九、Harness 设计

MVP Harness 用于限制 Agent 行为、防止开发偏移，并持续验证数据结果。

### 9.1 结构化输出约束

跨阶段产物必须符合固定 Pydantic 结构。Intent/语言草稿可以来自受控 LLM；Real Canonical QueryPlan 由 Grounding/StateTransition 确定，DAX 由普通代码确定性构造，VerifiedFactSet 与 factual Answer/ReportSpec 不接受 LLM 虚构数值、排名、因果或外部事实。Real DAX LLM authority/call count 为 0。

### 9.2 工具白名单

Agent 只能调用预先登记的 Power BI 和报表工具。

### 9.3 查询限制

- 查询超时时间
- 最大返回行数
- 校验 MCP 实际 columns/rows/rowCount shape；显式 limit metadata 映射为 `truncated`，协议无法证明完整时保守标记 truncated，禁止声称全量排名或极值完整性
- 最大重试次数
- 禁止危险或无关查询
- 禁止访问未选择的语义模型

### 9.4 Golden Cases

当前仓库保留 12 个 Golden 定义案例（11 个离线可运行，1 个 Real-only 按设计跳过），并有 8 个 Known-answer Case（含 2 个 holdout）与 6 Conversation / 16 Turn 多轮契约。未实现的 comparison、通用趋势或正式 Renderer 场景只能作为未来验收目标，不能计入 M2 PASS。

每次修改 Prompt、Agent、MCP Adapter 或报表模块后执行回归测试。

### 9.5 Trace

每次请求记录：用户问题、语义模型、模板、意图识别结果、查询计划、DAX、MCP 返回数据摘要、最终答案、ReportSpec、错误信息、各阶段耗时。

## 十、MVP 接口

| 接口 | 说明 |
|------|------|
| `GET /health` | 检查当前运行模式的配置就绪状态；不把它描述为 Desktop 实时在线探测 |
| `GET /api/v1/semantic-models` | ✅ M5.3.2 多模型只读 discovery；逐实例返回 safe catalog 与 compatibility，不返回 connection string、PID、端口、raw fingerprint 或 MCP payload |
| `GET /api/report-templates` | **未实现** — M5.1 只集中登记 production `sales_report` |
| `POST /api/v1/chat` | ✅ 已实现；Mock+Mock、DeepSeek+Mock、DeepSeek+Local MCP 共用正式 TurnPipeline |
| `GET /api/reports/{report_id}` | ✅ 已实现；查看 repository-owned 静态 HTML |
| `GET /api/reports/{report_id}/download` | ✅ 已实现；下载 UTF-8 HTML 报表 |
| `DELETE /api/reports/{report_id}` | ✅ M5.3.3；显式人工删除 report metadata + managed HTML，conversation 保留；不属于 ToolGateway，LLM 无权限 |
| `GET /api/v1/conversations` | ✅ 已实现（SQLite 必填 runtime_mode） |
| `GET /api/v1/conversations/search` | ✅ 已实现 |
| `GET /api/v1/conversations/{id}/history` | ✅ 已实现 |
| `GET /api/v1/conversations/{id}/reports` | ✅ 已实现（必填 source_mode） |
| `PATCH /api/v1/conversations/{id}` | ✅ 已实现；仅在 runtime namespace 内修改展示型标题 |
| `POST /api/v1/conversations/{id}/archive` | ✅ 已实现 |
| `GET /api/v1/conversations/archived` | ✅ M5.3.3；列出 exact runtime namespace 的 archived conversations |
| `POST /api/v1/conversations/{id}/restore` | ✅ M5.3.3；恢复逻辑归档，不重建业务状态 |
| `DELETE /api/v1/conversations/{id}` | ✅ 已实现 |

## 十一、MVP 开发阶段

1. **M0 开发准备** ✅ 已完成 — 仓库、文档、Agent 架构设计、数据接入验证、项目骨架
2. **M1 真实 DeepSeek 接入** ✅ 已完成并封板 — LLM Provider、Intent/QueryPlan 与统一 TurnPipeline；历史 LLM DAX/Answer 保留 Mock compatibility
3. **M2 真实 Power BI MCP 与数据问答** ✅ 已由 `m2.6.4-m0-m2-final-seal` 正式封板；Local MCP、Business Semantic Grounding、Deterministic DAX、VerifiedFactSet 与 hardened acceptance 已完成；Remote Deferred
4. **M3 报表生成闭环** ✅ 已完成并随 M0—M3 正式封板 — `sales_report`、adaptive report planning、固定 HTML、报表资源 ID、查看/下载
5. **M4 多轮记忆完善** ✅ M4 FINAL PASS；M4.4.2 truth/persistence boundary final closure FINAL PASS — SQLite 会话持久化、恢复、history/search/archive/delete、restart/crash acceptance、完整 committed payload 与 mandatory namespace fail-closed
6. **M5.0 前端设计与契约固化** ✅ 已完成 — 文档校准、页面结构、交互边界、动态回答原则、UI ↔ 后端能力映射；不创建 React 项目
7. **M5.1 React 前端实现与核心联调** ✅ 已完成 — React + Vite + TypeScript、Sidebar/Welcome/Chat/Composer、Chat/History/Search/Reports 联调、动态 terminal-state/report 渲染
8. **M5.2 真实业务链路与前端逻辑收口** ✅ 已完成 — Real 模式、Desktop 模型 discovery、SQLite 会话配置、intent/template/model 逻辑、真实多轮 Chat/report 与最小用户可理解错误态
9. **M5.3 结构化结果与前端最终收口** ✅ 已完成 — structured presentation、展示型 transcript/title、重命名/归档/删除、metric/table/bar/line/report attachment、responsive/accessibility/状态视觉与 Rich PBIX Real 浏览器验收
10. **M5.3.1 Final Hardening** ✅ 已完成 — Local MCP 多 Desktop 在 Connect 前 fail closed，presentation 只投影 VerifiedFactSet 数据事实覆盖字段；无新产品能力或后续里程碑扩展
11. **M5.3.2 Local MCP 多模型选择与协议稳定性加固** ✅ 已完成 — 多 PBIX 安全枚举、前端单选/刷新、opaque 精确实例绑定、只读 capability probe、stale fail-closed 与 row-limit/truncation 防腐；Remote MCP 继续 Deferred
12. **M5.3.3 多轮语义、会话资源生命周期与仓库治理最终收口** ✅ 已完成 — LLM flexible draft + deterministic canonical resolution、fresh/follow-up/replace inheritance、unsupported preflight、archive/restore/report delete、conversation stale-response protection 与 Artifact Governance

## 十二、MVP 暂不包含

- 多 Agent
- LangGraph
- 多租户
- 复杂用户权限
- 不同客户的数据隔离
- Power BI RLS 打通
- 跨语义模型查询
- 用户自定义 HTML 模板
- 动态 Power BI 报表发布
- 任意代码执行
- 复杂后台管理页面
- Docker（延后到真实后端链路跑通后）

## 十三、修正与固化

基于 M0.1 Prompt，以下内容已在本正式 PRD 中修正和固化：

| 项目 | 修正/固化内容 |
|------|--------------|
| Agent 架构 | 使用成熟框架支持的单 Agent（非 LangGraph、非多 Agent、非手写 Runtime）|
| 意图识别 | Agent 必须包含独立可测试的意图识别模块 |
| LLM | 真实 LLM 只有 DeepSeek；必须提供 Mock LLM |
| 记忆系统 | 核心卖点，必须包含结构化工作记忆和可靠提交机制 |
| Power BI MCP | 后端统一接入，网页用户不配置 MCP |
| 报表 | M2 ReportSpec 不得越过 VerifiedFactSet；M3 再实现固定模板 HTML 正式渲染 |
| Harness | MVP 轻量控制面 |
| 前端 | 等待后端跑通后正式开发 |
| Conda | `D:\Conda`，环境名 `PBIAgent`，Python 3.11 |

## 十四、验收标准

以下是完整 MVP 的跨阶段成功标准。M0—M3 已封板，M4 backend 已 FINAL PASS，M4.4.2 truth/persistence boundary final closure 已完成；M5.0—M5.3.3 已完成。M5.3.3 Rich PBIX Real 浏览器验证覆盖八轮语义、unsupported、报表 ownership、archive/restore、独立 report delete、conversation delete 与 A/B 快速切换；CI 只验证 Mock/Fake 边界，真实 Power BI Desktop 继续由本地人工 Smoke 验证。

MVP 达到以下条件即可视为成功：

1. 后端可以稳定连接 Power BI MCP
2. 可以读取指定语义模型的结构
3. 用户可以通过自然语言查询真实 Power BI 数据
4. 返回的核心数值与 Power BI 中的数据一致
5. 支持基本多轮追问和筛选条件继承
6. 可以使用固定模板生成静态 HTML 报表
7. LLM 无法执行任意代码或绕过工具白名单
8. 关键请求具备完整 Trace
9. Golden Cases 可以重复执行并输出测试结果
10. React 页面可以完成模型选择、模板选择、提问和结果展示

## 十五、后续扩展方向

当 MVP 验证成功并出现正式客户需求后，再考虑：

- 多个 LLM 模型切换
- Microsoft 用户登录
- Power BI 用户权限和 RLS
- 多租户隔离
- 更多语义模型和报表模板
- 报表分享和定时发送
- 更完整的 Harness 和评测平台
- 更复杂的 Agent 编排

---

*修订日期：2026-08-24 | M5.3.3 COMPLETE；North Star 与 factual authority 不变*
