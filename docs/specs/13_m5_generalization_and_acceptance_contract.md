# 13 — M5 重建、泛化与验收契约

> **状态：** M5.5 COMPLETE；M5.6—M5.9 NOT STARTED
> **适用范围：** `m5/rebuild` 开发线及 M5.5—M5.9
> **基线：** M5.4.1 commit `cab40b076f054a3ebdab0bf6d2b0354f4b2d49db`
> **性质：** 长期工程与验收合同；M5.5 已按此合同完成，后续阶段继续受本合同约束

## 一、重建基线与历史真实性

新开发线必须从 M5.4.1 稳定基线 `cab40b076f054a3ebdab0bf6d2b0354f4b2d49db` 开始。以下旧实验线作为研究和失败经验永久保留：

```text
m5/frontend
├─ a197db3ecfe8959f3f8bb79e18d7ee02834fedd3 — 原 M5.5
└─ 6d1620a7a7aa04e65692371436d90756fdf5bcc8 — 原 M5.5.1
```

它们不得删除、revert、rebase 或重写，不得整体 cherry-pick 到新线。后续可以参考单项设计思想，但每项能力都必须在所属新里程碑中重新实现、重新建立回归证据并重新完成 Real Acceptance。正式记录不得把这段实验历史伪装成“从未发生”，也不得把旧 PASS 数字冒充新线证据。

M5.4.1 及以前的以下能力不可回退：

- Agent-first 前端、Local MCP readonly；
- 多 PBIX opaque identity、exact selection 与 stale fail closed；
- TurnPipeline、Memory、Deterministic DAX、QueryResult / VerifiedFactSet factual authority；
- M5.3.3 多轮基础语义；
- conversation-scoped state、异 conversation 并发、同 conversation 串行；
- Settings 全量 cursor pagination 与 conversation/report resource lifecycle；
- archive ≠ delete、report tombstone；
- automation ownership、residual=0、unknown ownership 用户资源不得自动删除。

## 二、真实用户测试问题账本

### 2.1 Semantic / capability

- “火星区销售额”不得因 member 无匹配而降级为全国销售额。任何 explicit member/filter 无法权威解析时，必须 clarification 或 no-match，并且 **ZERO DAX**。
- “华南”“华南区”“南区”不能由代码猜同义，必须以当前模型的 runtime member authority 和受控语义证据解析；不能唯一证明时 clarification。
- prediction、write、delete、modify 等能力边界近义词不能依赖无限扩张的 regex；“大概多少”不得被误判为 prediction。最终 capability 结论必须由 bounded evidence + deterministic policy 决定。
- TopN/ranking 不得因不必要的 LLM failure 完全失效；canonical ranking slots 与执行必须继续遵守 deterministic authority。
- 生产代码不得为 Sales 写死答案、字段或 member。

核心 Gate：

```text
explicit unresolved semantic requirement
→ clarification / no-match
→ ZERO DAX
```

### 2.2 Multi-turn / temporal

以下真实 follow-up 必须按当前明确表达正确 KEEP/REPLACE slot：

```text
2025年5月销售额
→ 那南区呢
→ 换成去年
→ 前三个产品呢
```

- 第二轮替换区域筛选，保留 measure 与时间；
- 第三轮只替换时间，保留 measure 与兼容筛选；
- 第四轮增加/替换 ranking dimension、sort、top_n，不能因当前轮未重述 measure 就丢失 measure；
- 任何成员歧义或 no-match 都不得借旧 Memory 继续执行。

canonical 时间值可继续作为内部权威表示，但 UI 不得直接展示类似 `Year Month=2025-01-01T00:00:00 ...` 的内部 representation。

### 2.3 Presentation / resource UX

职责固定为：

```text
Answer = 洞察
Table = 明细
Chart = 趋势 / 关系
```

Answer 不得完整重复 table。展示层必须保持 canonical/display separation，不得用本地化或格式化改写 QueryPlan、DAX、QueryResult 或 VerifiedFactSet。

后续必须分别解决：

- Settings 有 report 时 Recent Reports 必须同步反映同一资源 truth；
- Recent conversation 必须 newest-first；
- failed conversation 必须作为正式资源可查看、重试或删除；
- toolbar 空间不足时不得隐藏 destructive actions，必须采用 sticky、scroll 或 responsive toolbar；
- conversation/report action menu 不得被 overflow clipping。

### 2.4 Report readability

“技术不裁切”不等于“产品可读”。报表必须合理利用 card width/height，时间轴可识别且跨年份清晰，plot area 比例合理，不出现巨大无意义空白，donut/legend 信息密度合理，并通过 Real Browser 人工视觉 Gate。

### 2.5 Performance / MCP lifecycle

旧实验线曾观测到 Real latency 从几十秒到数分钟；schema/member/DAX 重复 session 有明显成本。persistent worker 是可参考思路，但 queue、backpressure、TTL、stale、异常恢复必须在 M5.8 独立压力验证。必须分别报告 cold 与 warm latency，禁止用 warm latency 冒充 cold latency。

## 三、M5.5—M5.9 分阶段边界

### M5.5 — Semantic correctness and capability boundary

只允许开发：

- semantic grounding；
- runtime member validation；
- ambiguity / no-match；
- multi-turn KEEP/REPLACE；
- ranking / TopN；
- temporal semantic contract；
- capability boundary。

禁止：Localization、Report Visual、MCP performance optimization、Resource UI 大改。M5.5 的首要验收是 explicit unresolved semantic requirement 必须 clarification/no-match 且 ZERO DAX。

#### M5.5 canonical semantic contract

- object role 固定为 `measure / dimension / filter_field / date_field / ranking_dimension`；解析顺序为 runtime canonical exact → approved model-scoped alias exact → metadata evidence → bounded candidate-ID selection → ambiguous/no-match。
- business member 与 object grounding 分离：user literal → target field candidate → deterministic alias/morphology candidate → optional bounded language candidate → runtime `ColumnMembers` exact validation → canonical runtime member。无匹配、多个 field 命中或多个 member 候选都不得执行。
- slot 独立决策 `measure / dimensions / filters / time / ranking / sort`，优先级为 current explicit evidence > current bounded semantic draft > compatible committed Memory。fresh query 清除无关旧槽；follow-up/replace 只继承真正省略的兼容槽。
- 高置信 ranking grammar 确定性提取“前N个/Top N/最高的N个/最低的N个”的 `top_n`、direction 与 ranking intent；ranking dimension/measure 仍由 runtime grounding 决定，不能由 grammar 猜对象。
- temporal contract 区分 time filter 与 temporal grouping，首批 registry 支持 explicit month/year、relative month/year、recent N months、bounded range、month/year grouping。runtime 不支持 requested grouping 时 controlled unsupported/clarification，禁止 HTTP 500。
- capability 使用三层：deterministic safety floor；只输出 `READ_ANALYSIS / FUTURE_PREDICTION / MODEL_WRITE / DATA_DELETE / ARBITRARY_CODE / UNKNOWN` 的 bounded classification；deterministic policy 终审 supported/clarification/unsupported。“大概多少”不得因单一词误判为 prediction。
- semantic trace 至少记录 request/conversation ID、current explicit slots、inherited slots、object/member grounding status、capability decision、canonical plan summary/hash、DAX executed 与 Memory committed；不得记录 Secret 或 raw full prompt。

### M5.6 — Presentation, localization and resource UX truth

只允许开发：

- canonical/display separation；
- model/object/schema-scoped Localization；
- number/date/month formatting；
- Answer/Table/Chart 信息密度；
- Settings/Recent resource truth、newest-first；
- failed resource lifecycle；
- sticky/scroll/responsive toolbar 与 floating menus。

conversation 与 report 必须共用同一 Portal/floating layer action menu，按 viewport 在目标行上方或下方定位；禁止分别维护两套易漂移逻辑，且不得被 scroll container、scrollbar 或 stacking context 裁切。Settings Resource Manager 必须有 nested scroll contract 与 sticky 或 scrollable action toolbar，responsive overflow 不得吞掉 destructive actions。

正式 Layout Gate 至少覆盖：first/middle/last row、scroll top/middle/bottom、100%/125% zoom、768/1080/1440 viewport height、Sidebar scroll、Settings nested scroll、destructive action 始终可访问、floating menu 永不裁切。

禁止修改 Grounding authority、DAX authority 与 MCP architecture。

### M5.7 — Report readability and visual acceptance

只允许开发：

- report information architecture；
- responsive layout；
- plot geometry、axis/tick density；
- accessibility、visual hierarchy 与 report readability。

禁止修改 Semantic logic、MCP optimization 与 resource lifecycle。正式 Gate 是“普通用户必须能读懂报表”，不能只证明 SVG 未越界。

### M5.8 — MCP performance and resilience

仅在 M5.5—M5.7 分别冻结后开始：

- profiling；
- schema/member/discovery/probe cache；
- session reuse、persistent worker；
- bounded concurrency、bounded queue/backpressure；
- cold/warm performance；
- 20/50/100 concurrency；
- PBIX restart、backend restart、fault injection 与 long soak。

任何优化不得降低 schema/member/instance/factual validation，不得绕过 Grounding、Layer 3、VerifiedFactSet 或 stale fail-closed。

### M5.9 — 固定专业销售报表模板与模板选择

M5.9 必须晚于 M5.8，状态为 NOT STARTED：

- “简易模板”= 当前 `sales_report.html` 经 M5.7 可读性优化后的稳定模板；
- “销售模板”= 按已确认 Power BI 参考报表版式固定制作的专业 sales report HTML；
- 用户生成报表时可明确选择“简易模板”或“销售模板”。

固定链为：

```text
VerifiedFactSet
→ ReportData / ReportSpec
→ template_key
→ deterministic fixed HTML renderer
```

LLM 不拥有 HTML layout、factual 或 query authority，不得临场生成 HTML/CSS/SVG。专业销售模板规划包含深色 Header/title/navigation、KPI cards、左侧阶段/漏斗业务区、中部横向业务对比、右侧状态/异常/明细区、下部区域/业务表格、地域视觉、明细表、footer 指标口径与 Last Refresh。若 runtime schema 没有 Forecast/Goal/Pipeline 等事实，必须以真实可支持的 sales-specific section 替代到相同版位，禁止伪造；Agent 主链仍保持跨领域通用。只有 M5.9 完成全部正式 Gate 后才允许声明 `M5 FINAL`。

## 四、Generalization Gate

PowerBIAgent 的目标不是 Sales Agent。M5.5 及以后每个影响语义或展示泛化的版本，至少使用三个不同业务域验证：

```text
Sales / Retail
Education
Inventory / Operations
```

生产代码不得写死下列名称或对应答案，除非位于正式 model-scoped glossary 或明确 test fixture：

```text
Total Sales
Region
Product
StudentCount
AttendanceRate
InventoryTurnover
Warehouse
```

测试答案不得放入 LLM Prompt。正确 acceptance 输入链固定为：

```text
runtime schema
+ semantic metadata
+ runtime members
+ user question
→ Agent
→ QueryPlan
→ DAX
→ QueryResult
→ VerifiedFactSet
```

随后由独立 deterministic oracle 校验结果。开发期覆盖三个已知业务域；最终还必须使用主要模型之外、开发期间未知的 holdout 业务模型。至少覆盖：新字段、多相似字段、display rename、table rename、member change、glossary missing。Agent 只能 `resolve`、`clarify` 或 `no-match`，禁止猜测或 silent semantic downgrade。

## 五、里程碑隔离与完成门禁

一个 milestone 禁止同时大规模修改以下多个域：

```text
Semantic
MCP
Presentation
Report
Resource lifecycle
```

每轮固定顺序：

```text
Spec
→ Failure reproducer
→ Regression tests
→ Minimal implementation
→ Focused Real
→ Cross-domain
→ Full gates
→ User manual acceptance
→ commit
```

`1900 tests passed` 或任何单一自动化数字都不能独立支持 COMPLETE。Real Browser / 人工验收是正式 Gate；测试、Real 数据、人工视觉与用户 acceptance 必须分别记录，不能互相替代。

## 六、M5.4.2 边界

M5.4.2 只建立 `m5/rebuild` Git 基线并固化本文档及相关治理入口，不修改生产业务逻辑、不改 schema/migration、不开始新版 M5.5。完成后必须停止并等待下一轮明确指令。

## 七、M5.5 checkpoint 与完成边界

M5.5 固定顺序为 S1 docs/contracts、S2 semantic failure reproducers、S3 capability、S4 object/member、S5 multi-turn、S6 ranking/TopN、S7 temporal、S8 cross-domain/schema mutation、S9 focused regression、S10 full backend/golden/governance、S11 Real Browser/manual、S12 final docs/commit/push。任一 checkpoint FAIL 不进入下一项。

完成必须同时证明：explicit unresolved 全部 ZERO DAX/QueryResult/Memory commit；四轮 slot transition、TopN、time filter/grouping、readonly unsupported 正确；Sales/Education/Inventory、未知 holdout 与 schema mutation 全部通过；无 sales-specific production hardcode；full gates 与 Real/manual acceptance 均 PASS。

M5.5 完成证据：

- `火星区` clarification 且 ZERO DAX/QueryResult/Memory commit；`华南/华南区/南区` 通过 runtime members canonicalize 为 `South`；
- Real Rich PBIX 四轮正确完成 measure/time/filter KEEP/REPLACE 与 Product Top3 descending；
- Sales、Education、Inventory、未知 opaque holdout、schema mutation 与 capability/temporal gates 通过 deterministic oracle；
- backend `1823 passed, 1 skipped`，frontend `69 passed` 且 typecheck/lint/build PASS，Golden `11 passed, 1 manual-real skipped`，全部治理门禁与 Real Browser/manual acceptance PASS；
- acceptance automation-owned residual=0；未修改 Presentation、Resource UX、Report、MCP performance 或 M5.9 实现。

---

*创建日期：2026-08-26 | 最后更新：2026-08-26 M5.5 COMPLETE — M5.6 Resource UX 与 M5.9 模板规划未开始*
