# 12 — 多轮语义、会话与资源生命周期契约

> **状态：** M5.3.3 正式契约；M5.5 语义验收、M5.6 Resource UX truth 与 M5.7 Template Required 均已完成
> **边界：** 本契约只收口多轮省略项继承、只读 unsupported、会话 UI 异步一致性、归档/恢复/删除与本地 artifact 生命周期；不改变 M0–M5 Canonical QueryPlan、Deterministic DAX、VerifiedFactSet、Report factual authority。

## 一、语言理解与 canonical authority

自然语言理解采用两层职责：

1. LLM 负责灵活识别当前输入中的语言信号，包括指标、维度、筛选、时间表达、排序、TopN，以及 `fresh_question / follow_up / replace / unclear` 的受限会话关系草稿。
2. LLM 只能输出 typed、bounded semantic draft。对象 identity、成员值、日期字段、时间边界和最终 QueryPlan 仍由 runtime schema、model-scoped glossary、runtime members、注入 clock 与 deterministic validators 决定。

固定优先级为：

```text
当前用户明确表达
> 当前 LLM bounded semantic draft
> last successful committed Memory 的省略项继承
```

LLM draft 与当前输入冲突时不得覆盖当前输入；与 runtime authority 冲突、候选不唯一或无法确定时必须 clarification/fail closed。

## 二、TimeIntentDraft

LLM 可以输出结构化 `TimeIntentDraft`，但不能选择 Date field 或直接写入 `TimeRangeSpec`。允许形态至少包括：

- `absolute_month`：如 `2025年5月`；
- `absolute_year`：如 `2025年`；
- `relative_month`：如 `本月`、`上个月`；
- `relative_year`：如 `今年`、`去年`；
- `quarter`：如 `今年第一季度`；
- `recent_months`：如 `最近半年`；
- `bounded_range`：明确起止日期。

draft 必须保留当前原始短语和受限参数。deterministic resolver 必须先证明该短语确实属于当前输入，再绑定唯一 runtime Date field，并用固定 clock/calendar 规则生成 `TimeRangeSpec`。非法日期、越界月份、缺参数、当前输入不含该短语或多个 Date field 均不得继承旧时间冒充成功。

deterministic fast path 继续处理少量稳定表达；它是可靠地板，不承担穷举中文语言的职责。

## 三、fresh、follow-up 与 replace

同一 `conversation_id` 不等于自动 follow-up。每轮必须先形成 deterministic inheritance decision：

| 关系 | 语义 | 省略槽策略 |
|---|---|---|
| `fresh_question` | 当前输入形成新的、可独立理解的数据问题 | 清除未在当前轮表达的旧 time/filter/dimension/sort/top_n；当前明确槽重新 Ground |
| `follow_up` | 有明确指代/承接证据，如“那华东呢”“那只看华南呢” | 仅对当前未表达的兼容槽允许继承 |
| `replace` | 有明确修改证据，如“改成去年”“换成订单数” | 当前指定槽 REPLACE，其余兼容槽继承 |
| `unclear` | 无足够证据判断独立问题还是追问 | clarification，不得选择更方便执行的继承结果 |

LLM 的关系草稿不是事实 authority。deterministic policy 必须结合当前已 Ground 的槽、明确承接/替换语法和 committed state 验证草稿。一个自包含的新问题不能因为共享 conversation 就继承旧时间或旧 TopN。

示例：

- `2025年5月销售额多少`：`fresh_question`，measure=销售额，time REPLACE 为 2025-05；
- `销售额最高的前3个区域是什么`：`fresh_question`，measure=销售额、dimension=区域、sort=desc、top_n=3，旧时间/筛选清除；
- `那华东呢`：`follow_up`，当前成员筛选覆盖对应字段，其余兼容槽可继承；
- `改成去年`：`replace`，只替换时间；
- 证据不足：clarification。

新 M5.5 必须使用以下连续真实 follow-up 验收完整 slot transition：

```text
2025年5月销售额
→ 那南区呢
→ 换成去年
→ 前三个产品呢
```

第二轮只 REPLACE 区域 filter，第三轮只 REPLACE time，第四轮形成 Product Top3 ranking；当前轮未重述 measure 不得导致 measure 丢失。若“南区”不能由当前 runtime members 唯一证明，必须 clarification/no-match，旧 filter 或旧 Memory 不得把它变为可执行状态。

## 四、Memory 与 Pending 边界

- Memory 只继承 last successful committed state，且只服务当前轮真正省略的兼容槽。
- clarification、unsupported、validation/tool/DAX/Power BI/factual output 失败均不得提交新的 committed Memory。
- PendingClarificationContext 与 committed Memory 分离；fresh question、unsupported、模型切换或明确放弃必须清除不兼容 pending chain。
- semantic model key 变化时，旧模型业务槽不得输入 Intent/QueryPlan/Grounding；新模型不得继承旧模型对象、成员、时间或分析形态。历史记录保留，但上下文从空状态开始。
- LLM 输出的 `inherited_context` 永远只是 diagnostic，不参与状态变更。

## 五、readonly unsupported 前置门禁

以下当前请求必须在 committed Memory、Grounding、DAX 与 Power BI 之前 deterministic fail closed：

- 预测/外推未来销售或其他指标；
- 修改 PBIX、Measure、模型、表或字段；
- 删除/清空/写入数据或模型；
- 任意 Python、Shell、PowerShell、SQL、JavaScript 或代码执行；
- 通过自然语言删除报表资源。

存在 committed Memory 或 pending context 不是放行理由。只有当前输入本身属于已支持的只读数据问答/固定报表语言形态，LLM 的误判才可交给 Grounding 做 capability 判定。unsupported 终态必须满足：无 schema/member/DAX/Power BI/report delete 调用、无 pending、无 Memory commit。

能力近义表达不得依赖无限扩张的 regex；“大概多少”不能仅因含近似词被误判为 prediction。bounded language evidence 只能进入 deterministic capability policy，不能直接放行写入/预测，也不能把只读数据问题错误拒绝。explicit member/filter 一旦 UNRESOLVED 或 AMBIGUOUS，必须 clarification/no-match 且 ZERO DAX。

## 六、Report ownership

每个 report 必须唯一属于：

```text
(source_mode, conversation_id, request_id, report_id)
```

- report history 只能按 `(source_mode, conversation_id)` 返回该 conversation 的 metadata；
- Snapshot attachment 的 report_id 只有在同 namespace metadata 仍存在时才可恢复；
- 已独立删除的 report 不再出现在 recent reports 或 History attachment；
- archived conversation 的 report 不进入普通“最近报表”，只在归档 conversation 的 history/report view 中出现；
- B conversation 永远不得展示 A conversation 的 report。

## 七、archive、restore 与 delete

### 归档

- 只设置逻辑 `archived_at`；
- conversation、History/Snapshot、Memory、report metadata 与 managed HTML 全部保留；
- 从普通最近/搜索列表隐藏；
- 在“已归档”入口可见，可打开 history/report，可恢复；
- 不删除 HTML。

### 恢复

- 清除 exact `(runtime_mode, conversation_id)` 的 `archived_at`；
- conversation 返回普通最近列表；
- 不重建、不复制、不改写其 Memory/Snapshot/report。

### 删除 conversation

- 用户确认后永久删除 exact namespace 的 conversation、Snapshot/History、Memory、Pending、linked report metadata 与 managed HTML；
- 继续使用 durable delete intent 处理 DB/文件系统窗口；
- 另一 runtime namespace 不受影响。

三种操作不得共用含糊的“移除”语义。

M5.6 必须让 failed conversation 作为正式、持久化 presentation/resource 状态可管理：Settings 可见，并支持 rename、archive、restore、delete；reload/restart 后状态一致。processing 可暂时禁止 destructive mutation，但 terminal failure 不得变成只有内存中存在的幽灵 session。该展示与管理能力不得把 failed turn 提升为 committed Memory，也不得改变 archive/delete 语义。

conversation/report 的单项 action menu 必须共享 Portal/floating layer 与 viewport-aware above/below positioning，不得被列表 overflow、scrollbar 或 stacking context 裁切。Settings 二级资源页面必须有 nested scroll contract 与 sticky 或 scrollable action toolbar；在首/中/末行、滚动 top/middle/bottom、100%/125% zoom、768/1080/1440 viewport height 下，archive/delete/restore 等关键操作均须可访问。该 M5.6 UI 合同不得改变资源 API、durable delete intent 或 Grounding/DAX/MCP authority。

Recent resource truth 固定如下：Settings 使用完整 namespace-scoped conversation/report pagination；Sidebar 只从同一正式 source 读取 bounded recent projection。Report projection 只包含 active report，并按正式 resource time + stable ID newest-first；rename 后同步，archive 后消失，restore 后重新出现，delete 后仅保留既有 history tombstone 边界。Conversation 固定按 `updated_at DESC, created_at DESC, stable_id DESC`，local pending/failed 也必须保存稳定 timestamps 并与 reload 后服务端顺序一致。

## 八、独立 report delete

独立 report delete 是显式资源管理 API，不是 Agent tool：

- 入口：用户在前端 report 菜单点击并确认；
- API：`DELETE /api/reports/{report_id}`；
- 不注册到 ToolGateway，不接受自然语言触发，LLM 无调用权限；
- 删除 exact report metadata、managed HTML 与进程内 cache；conversation 保留；
- Snapshot/History 的旧 attachment 在读取投影时因 metadata 不存在而隐藏；不篡改业务事实或伪造新 Snapshot；
- HTML 删除失败必须返回受控错误，不得报告成功；目标路径只能由 repository-owned metadata 推导并保持严格 containment；
- metadata/HTML 跨介质窗口采用可重试的 durable report delete intent；成功 cleanup 后才 finalize intent。

前端确认文案：

> 删除“销售分析报告”？此操作不可撤销，但不会删除所属对话。

## 九、前端异步一致性

history 请求必须同时持有 request generation 和目标 conversation identity。响应返回时必须再次验证：

```text
response.conversation_id == current activeConversationId
&& response.generation == current generation
```

否则丢弃，禁止修改 messages、title、report attachment 或 loading state。open conversation、new chat、delete、archive、restore、semantic model switch 和再次切换 conversation 必须 abort/失效旧 history 请求。错误响应同样不得跨 conversation 覆盖 UI。

## 十、local_state 与 Artifact Governance

允许的长期目录固定为：

```text
local_state/persistence/
local_state/reports/
local_state/runtime/
local_state/archive/
```

根目录不得散落 log/json/txt/html/sqlite 或运行脚本。生产 managed report 只在 reports；SQLite 只在 persistence；临时 runtime registry/ownership 信息只在 runtime；需保留但不再活跃的历史材料进入 archive。

自动化测试 artifact 生命周期固定为：

```text
Create → register ownership → use → teardown → verify cleanup
```

M5.4.1 起，`register ownership` 不得只登记临时文件路径。任何会写入正式 SQLite/report filesystem 的 Codex acceptance、pytest integration、browser、Real Smoke、MCP 或 report test，必须至少记录：

- 唯一 `test_run_id`；
- `test_owner=automation`（或等价受控枚举）；
- exact runtime/source namespace；
- conversation ID、report ID、managed HTML linkage 与创建时间；
- cleanup 状态与失败原因。

teardown 必须位于 `finally`，优先调用正式 conversation/report API；直接运行 repository integration 时只能调用同一 production repository lifecycle，不得执行无 namespace SQL 或按标题猜测删除。cleanup 完成后必须重新查询并证明 test-owned conversation/report metadata/HTML/SQLite namespace/delete intent/orphan residual 全部为 0。

Artifact Governance Gate 必须只读检查并在以下情况失败：

- active ownership registry 中的 test conversation/report/file 残留；
- test report HTML 残留或 metadata/file orphan/mismatch；
- unauthorized local_state root entry；
- runtime artifact 写进 source tree；
- cleanup failure/pending cleanup 未解决。
- 本轮 test-owned conversation、report metadata、managed HTML、SQLite namespace 或 pending delete intent 残留；
- ownership registry 声称已清理但正式 repository/filesystem 仍存在 exact linked resource。

Gate 不自动删除、移动或修复用户数据。无法证明为 test-owned 的既有状态一律按用户数据处理；标题、问题文本或“看起来像测试”不构成 ownership。历史清理或归档必须有 metadata、known test namespace/ID、fixture 或 report linkage 的显式证据，并通过正式资源生命周期操作。

## 十一、M5.7 Template Required 失败资源语义

- missing/invalid/stale `report_template_key` 是 report request 的受控 clarification/template-required 终态，不得创建 ReportData、ReportSpec、ReportArtifact metadata 或 HTML。
- 失败 turn 继续遵守既有 lifecycle：不得提交 Memory；conversation presentation/resource 可按 M5.6 正式 metadata 保留并可 rename/archive/restore/delete。
- 用户选择有效“简易模板”后可以用新 request 重试；既有失败 request 不得被改写为成功 artifact，也不得绕过 request/replay identity。
- 自动化验收创建的 conversation/report/HTML 必须登记 ownership，在 `finally` 中经正式生命周期清理并证明 residual=0；模板缺失失败本身必须证明 artifact residual 为 0。

---

*创建日期：2026-08-24 | 最后更新：2026-08-26 M5.7 COMPLETE — Template Required failure lifecycle*
