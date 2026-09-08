# ADR-018 — Deterministic Semantic Expression Normalization

- **状态：** accepted
- **日期：** 2026-09-08
- **决策者：** 用户明确批准 M5.9.3
- **适用阶段：** M5.9.3；M5.9.2 runtime 与 M5.10 report scope 冻结

## 背景

M5.8.5 已建立 obligation coverage 与 canonical shape completeness，但自然语言进入这些 Gate 之前仍可能发生两类静默语义损失：通用分组措辞被 Router 误判为 MEMBER_SET/filter，以及明确时间区间只保留起点。两者都会让后续 Gate 检查一个已被错误缩窄的 weak draft，而不是检查用户原始显式义务。

## 决策

1. Query Shape 继续是 code-owned analysis structure，不拥有 measure、dimension、filter field、member 或 date field identity。
2. `各X`、`每个X`、`按X`、`X分别` 是通用 grouping evidence；“分别是多少”本身不是 MEMBER_SET evidence。MEMBER_SET 必须有多个显式 member literal 的独立证据，并逐项通过同一 runtime field validation。
3. 明确、可确定的月范围由无业务对象知识的代码做 NFKC normalization，形成闭区间 `start/end` 与 `grain=month`。LLM time draft 只保留 weak linguistic signal，不拥有 canonical date range 或 date-field authority。
4. Grounding 后的 obligation 必须直接覆盖原始显式语义：TIME_RANGE=`start+end+grain`，RANKING=`measure+dimension+sort+N`，FILTER=`field+member/value`，GROUPING=`dimension`。任何组成部分未闭合都必须 clarification，并保持 ZERO DAX、ZERO QueryResult、ZERO factual Memory commit。
5. grouping cue 对应的 runtime field 不得仅因 weak LLM filter draft 进入 filter candidate；真正 filter 仍须 field resolution、完整 runtime member validation 和 canonical binding。known+unknown member set 整体 fail closed，禁止 partial execute。
6. clarification 文案只映射 deterministic failure reason，至少区分 dimension unresolved/ambiguous、filter field ambiguous、member no-match、incomplete member set、incomplete time range 与 ranking information incomplete。
7. M5.9.3 只做相关 deterministic regression 与 DeepSeek-only Real acceptance。M5.9.4 才负责 covering-array/property/metamorphic 大型业务语言压力 harness；Kimi 只保留 provider abstraction/mock/contract，不重复 Real token 压力测试。
8. M5.9.2 worker pool、retry、cancellation、singleflight，M5.8.5 factual authority，以及 M5.10 template/renderer 全部冻结。

## 后果与验收

更严格的显式义务可能增加澄清，但不会扩大查询范围。实现必须先保留 production-path failure reproducer，再做通用最小修复；跨 Sales/Retail、Education、Inventory/Operations 与未知 holdout 验证不得写死具体业务字段或 member。M5.9.3 只有在 Semantic Compatibility、全量 gates、DeepSeek Real、residual=0 与 exact-SHA CI success 后才可 COMPLETE；M5.9.4/M5.10 保持 NOT STARTED，M5 FINAL=false。
