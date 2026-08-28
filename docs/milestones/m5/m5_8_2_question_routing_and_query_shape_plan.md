# M5.8.2 — Question Routing 与通用 Query Shape 实施计划

> 状态：COMPLETE
> 基线：`m5/rebuild` / `c1df1fabde56b2d271dbedf0315399301614b6f7`
> 范围：自然语言能力路由、领域无关 Query Shape、最小必要澄清、基础算术、产品帮助、公开模型信息，以及受限 DAX shape 扩展。

## 1. 目标

在正式 Semantic Grounding 前建立确定性、可测试的 Question Router，使非业务问题不会进入业务指标或筛选字段澄清；对业务问题以 Query Shape 决定必需槽位，删除“所有数据问题都必须有 measure”的错误假设。

## 2. 权威边界

Question Router 只输出能力类别和非业务安全响应，不选择 measure、dimension、member、date field 或 canonical QueryPlan。Query Shape 只描述查询结构及所需槽位；对象身份仍由 runtime schema、model-scoped glossary、runtime members 与 Grounding 唯一确定。数值、顺序、筛选、时间与 provenance 继续仅来自 QueryResult/VerifiedFactSet。

固定路由类别：

- `BUSINESS_DATA_QUERY`
- `REPORT_REQUEST`
- `PRODUCT_HELP`
- `SYSTEM_INFO`
- `DETERMINISTIC_CALC`
- `UNSUPPORTED_GENERAL`

固定 Query Shape：

- `SCALAR`
- `ENTITY_LIST`
- `GROUPED`
- `RANKING`
- `MEMBER_SET`
- `FILTERED_AGGREGATION`
- `TREND`
- `BOUNDED_TREND`

## 3. Required-slot contract

| Shape | 必需槽位 |
|---|---|
| SCALAR | measure |
| ENTITY_LIST | dimension |
| GROUPED | measure + dimension |
| RANKING | measure + ranking dimension + sort；未显式 N 的极值问法取 `top_n=1` |
| MEMBER_SET | measure + one grounded field + two or more runtime-validated members；结果按该 field 分组 |
| FILTERED_AGGREGATION | measure + one grounded field + two or more runtime-validated members；结果为 scalar aggregation |
| TREND | measure + uniquely supported temporal grouping |
| BOUNDED_TREND | TREND + deterministic valid time range |

澄清只询问当前 shape 缺失且会改变结果的槽位；已经唯一解析的槽位不得重复询问。

## 4. 安全合同

- PRODUCT_HELP、SYSTEM_INFO、DETERMINISTIC_CALC、UNSUPPORTED_GENERAL：ZERO schema/member/DAX、ZERO semantic Memory mutation。
- Calculator 只接受有限长度、有限深度的 decimal/integer、`+ - * / × ÷` 与括号；使用受限递归下降 parser，不使用 `eval`、`exec`、变量、函数或 Python 任意语法。
- SYSTEM_INFO 只读当前 turn 的公开 `LLMModelProfile.display_name`，不返回 key、endpoint、Authorization 或 Secret。
- REPORT_REQUEST 继续在 Intent 后立即通过既有 Report Template Gate；本轮不改 ReportData/ReportSpec/Renderer/template。
- MEMBER_SET 必须先唯一 ground field，再逐个以 bounded runtime member lookup 验证；任一 unknown/ambiguous 均 fail closed 且 ZERO DAX。
- `IN_SET` 只允许非空、去重后的 runtime canonical members；DAX builder 与独立 verifier 必须同时证明同一集合。
- 绝对月区间由普通代码形成包含首尾月份的 `TimeRangeSpec`；`start > end` 必须澄清并 ZERO DAX。

## 5. 固定实施顺序

1. 写 production-path failure reproducers，并记录失败归属。
2. 实现 Router 与安全 calculator/help/system response。
3. 引入 QueryShape，按 shape 重构 Grounding、Pending Clarification 与 StateTransition。
4. 扩展 dimension-only、IN_SET、Top1、bounded trend 的 deterministic DAX 与独立 verifier。
5. 扩展 Sales/Education/Inventory/unknown holdout、schema mutation 与 benchmark leakage Gate。
6. 运行 focused、Semantic Compatibility、backend/frontend/Golden/governance 全门禁。
7. Rich PBIX Real Browser/manual acceptance、latency 与 automation-owned residual=0。
8. 最终文档、白名单 commit、push，并等待 exact-HEAD `PowerBIAgent Validation` success。

## 6. 完成证据

- Question Router 六类能力与八类 Query Shape 已接入共享 TurnPipeline；Router 不选择业务对象、成员、日期字段或事实。
- shape-specific required slots、minimal clarification、dimension-only distinct、Top1、runtime-validated member set/`IN_SET`、filtered aggregation、bounded month trend 与多轮 shape 继承已通过正式生产入口回归。
- Sales/Education/Inventory/unknown holdout 的 SCALAR、ENTITY_LIST、GROUPED、RANKING、MEMBER_SET、TREND 全部通过；unknown member、反向时间、unresolved explicit slot 均 ZERO DAX。
- Rich PBIX 15 项 Real acceptance 全部通过，模型中不存在的手机/电脑/笔记本保持 runtime no-match/clarification；non-business 六项 ZERO schema/DAX/Memory，residual=0。
- Fresh gates：Semantic Compatibility `421 passed`；backend `2046 passed, 1 skipped`；frontend `86 passed` 且 typecheck/lint/build PASS；Golden `11 passed, 1 manual-real skipped`；全部治理、compileall 与 diff check PASS。

## 7. 明确不做

不实现 MCP-driven `ModelSemanticContext`、自动 PBIX business binding、ontology、RAG、embedding、vector DB、knowledge graph；不修改 M5.8.1 session/cache/singleflight/concurrency；不修改 Provider；不修改 report renderer/template；不开发 M5.9/M5.10；不声明 M5 FINAL。
