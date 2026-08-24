# 12 — 多轮语义、会话与资源生命周期契约

> **状态：** M5.3.3 正式契约；实现与 fresh 验收进行中
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

Artifact Governance Gate 必须只读检查并在以下情况失败：

- active ownership registry 中的 test conversation/report/file 残留；
- test report HTML 残留或 metadata/file orphan/mismatch；
- unauthorized local_state root entry；
- runtime artifact 写进 source tree；
- cleanup failure/pending cleanup 未解决。

Gate 不自动删除、移动或修复用户数据。无法证明为 test-owned 的既有状态一律按用户数据处理；清理或归档需要显式、可审计的 ownership 与安全操作。

---

*创建日期：2026-08-24 | M5.3.3 多轮语义、会话与资源生命周期正式契约*
