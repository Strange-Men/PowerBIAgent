# M5.8.3 — MCP 驱动模型语义上下文

状态：验收收口；对应提交 CI success 后 COMPLETE。2026-08-30 用户批准。基线：`m5/rebuild` / `3b811dec214679bb556d4c96506e5e8f536fc5fc`。

## 验收临时目录生命周期（2026-08-31 收口补充）

验收辅助代码统一使用 `scripts.acceptance_tempdir.owned_acceptance_tempdir`：受控 `mkdtemp` + contextmanager/finally，在新建目录写 project/milestone/run token/exact path/prefix marker；删除前核验原目录身份、绝对路径和 marker，拒绝 reparse point、ownership 不匹配及未知前缀。只处理本次创建的路径，没有扫描式删除或 GC 隐式删除。验证副本和 Real comparison 的自有子进程先退出、句柄先关闭，再尝试目录清理。

正常、异常、mutation failure、A→B→A 中途失败和取消均进入 cleanup。OS/执行策略拒绝时只记录路径与原因的 cleanup warning，保留原异常，输出真实 `temporary_residual`；无法检查目录也不能报告 0。warning 不属于产品功能 P0，但 release residual Gate 仍要求实际为零，不通过换工具或权限绕过。标准流程不要求用户手工删除；测试中的模拟残留由外层 fixture 回收。强制杀进程/机器断电无法保证 finally 执行，不声称覆盖 M5.9 crash/soak。

## 修改前审计

| 来源 | 当前职责与发现 | 本轮合同 |
|---|---|---|
| A MCP runtime schema | Adapter 已通过 List/Get 获取表、列、度量、关系、层级；保留 column/measure description、displayName、formatString。层级只保留 level name；schema 未显式携带 generation。 | 模型结构唯一 authority；只适配实际读取的 metadata。 |
| B local glossary | 单个 production YAML 含 Sales 的对象引用、table ownership、alias、member alias、日期角色和月份 binding。Real service/discovery 将不同 opaque key 映射到同一个 friendly scope；fingerprint drift 只作诊断。 | optional、exact identity + metadata fingerprint 绑定的业务语言补充；不得作为 schema 清单或跨 PBIX 默认配置。 |
| C runtime members | MemberGrounder 经 ToolGateway → Adapter 有界读取 distinct values。 | 筛选值唯一 authority；alias 仍须 runtime member validation。 |
| D LLM weak signal | Intent/QueryPlan 为语言草稿；bounded selector 只回传 catalog candidate ID，并受唯一 metadata evidence 限制。 | 不创建对象、alias binding、relationship 或事实。 |
| E committed Memory | StateTransition 仅继承兼容且省略的槽；model switch 清除业务上下文；pending 独立保存。 | 不变，不能覆盖当前 ambiguity/no-match。 |

原 `compute_schema_fingerprint` 不包含 description/display，供历史 report/presentation 合同使用。本轮增加 context metadata fingerprint，覆盖全部适配的语义证据；不借机改变 Report/DAX/fact 合同。日期角色的单字段 cardinality 不再作为新 runtime context 的默认 authority。

## 冻结的 authority hierarchy

```text
Power BI MCP Runtime Semantic Model = model structure authority
  → immutable ModelSemanticContext = runtime metadata adaptation layer
  + optional validated model override = business language supplement
  → SemanticCatalog → Grounding → M5.8.2 Query Shape → StateTransition
  → Canonical QueryPlan → frozen deterministic DAX → QueryResult/VerifiedFactSet
```

对象匹配顺序：runtime canonical exact（含明确 qualified ownership）→ runtime display → runtime description evidence → validated override alias → runtime-owned bounded selector。零候选 unresolved；多候选无唯一证据 clarification。relationship 仅证明结构路径或明确日期角色，不猜业务含义。不因只有一个 measure/date 或列表位置自动选择。

Context 使用 frozen typed records 和 tuple，绑定 semantic_model_key、exact opaque runtime identity、schema metadata fingerprint 与可用的 session generation。保留可见表/列/度量的 ownership、description、display、type、format、flags、关系与层级证据；隐藏/system 对象不进入候选。无 QueryResult、FactSet、question mapping 或跨 PBIX 数据。未读取的 AI instructions/synonyms/linguistic schema/annotations 留空。

生产 override registry 默认可为空。每条补充必须精确指定 model identity、schema fingerprint 和一个已经存在的 object reference，仅允许 aliases/member aliases、明确 temporal role/binding、preferred phrasing；不能声明 schema、修改 ownership/type 或增加对象。fingerprint 改变必须重新验证/重新批准绑定，旧 alias 不静默复用；其他 PBIX 的 override 不参与选择。不得自动写 override。

上下文在每次获准 schema snapshot 后确定性构建；本轮优先不加 context cache。继续复用既有 Adapter identity validation、generation、TTL/singleflight；不修改 worker、缓存架构或 concurrency。

## 接口证据与边界

### 兼容迁移修正（2026-08-30）

三个 P0 的断点都在 optional override 输入：runtime schema 仍有对象，但清空 registry 丢失合法 alias/default date/month grouping，导致 Catalog 缺少 business metadata，Grounding clarification，未产生 CanonicalQueryPlan。不能用 runtime 中一个 Date 字段弥补这一缺失。

保留原 Desktop 的语言/日期补充为 inert profiles；这些 profile 仅含 runtime object reference 和 alias/member/temporal metadata，没有对象定义、type、table schema 或 relationships。profile 名不是 domain router，没有默认继承；必须由独立的 exact semantic_model_key/runtime_identity/schema_fingerprint binding 显式激活，再逐对象 runtime validation。schema mutation 后旧 binding 拒绝加载，其他 PBIX 无条件不继承。生产不自动批准/写入 fingerprint。

三个旧回归只把 fixture 的隐式 global glossary 配置迁移为显式 exact-model registry，结果、DAX、日期边界及 presentation 断言保留不变；synthetic identity 的 activation 仅位于 tests。真实 PBIX 的 explicit activation 需经真实 metadata 审计后单独登记。

当前正式 provider 的 `SCHEMA_READ_OPERATION_WHITELIST` 是 runtime 能力边界。新增适配字段必须同时具备协议证据和缺失时为空的回归；不能用 TOM 文档暗示 beta MCP 已暴露某字段。

2026-08-30 已通过正式 discovery/gateway/Local Adapter 对两份打开的 PBIX 做只读 metadata 审计。实际 columns 含 `description/isKey/expression/sortByColumn/formatString`，hierarchy levels 含 `name/columnName/ordinal/description`；初稿误读 `column` 已由 fixture reproducer 和真实属性名证据修正。两份模型均无非空对象 description/display，未观测到 `displayName` property，故保留为原 schema contract 的 optional metadata，不声称当前 beta 提供该字段。raw schema 存在 annotations property，但本轮不消费其任意内容，不宣称 AI Instructions、synonyms 或 linguistic schema 支持。

审计可见对象规模分别为 5 tables/20 columns/4 measures/4 relationships 和 1 table/7 columns/2 measures/0 relationships；两者都可无 override 建立 context。A→B→A 重新 exact validation 后 context 相同，未创建 conversation/report，临时目录 residual=0。这只证明 metadata 隔离，不替代 member/Memory/Real Chat 切换验收。

`--members` 扩展审计通过当前模型所有可见 text field 的有界 runtime lookup，并在切回模型后复核同 model/table/field/source-mode 与成员快照；两份模型共验证 13 个字段、122 个成员，2 个同名字段有不同成员集合。每个 measure 单独用一条 transient、exact-model/fingerprint 的语言补充检查 override 不跨模型；共 6 次通过，未写 production registry。每次重新建立 Catalog 后时间角色一致，未知成员保持 unresolved。这些是实际 MCP 的组件验收，仍不等同于 full Chat/Memory 或完整 warm/4-way performance Gate。

组件审计的 schema fetch 257.496/252.092ms、context build 1.171/0.521ms、catalog build 0.261/0.148ms；单次观察不是 full-turn 性能回归结论。后续 Rich 15 项和真实前后 facts/latency 比较已完成，证据见下方 2026-08-31 检查点。未新增 cache 或更改 MCP performance architecture。

2026-08-31 最终 mutation 审计补充：实际 MCP 提供的 relationship name、crossFilteringBehavior、securityFilteringBehavior、joinOnDateBehavior 作为 typed metadata 保留并参与 fingerprint。month projection 只在确定性的现有表达式结构中取证，不能删除 runtime identifier 内的空格；多个 source proof 不得按列表顺序覆盖 binding。六类 mutation 的 temporal 用例实际重命名日期字段，旧 override fail closed。

可用 `Settings.powerbi_semantic_override_path`（环境变量 `POWERBI_SEMANTIC_OVERRIDE_PATH`）指定独立 YAML registry。配置文件的 `version: 2`、`profiles` 与 `overrides` 经严格 typed validation；binding 必须含当前 exact `semantic_model_key`、`runtime_identity` 和 context fingerprint，`profile_keys` 只能引用显式列出的 inert profiles。也可只提供极薄的 `objects` alias 映射。未配置时使用默认空绑定；不自动写 registry，不根据 schema 相似度绑定 profile。legacy `build_from_data(version=1)` 仅保留离线兼容测试入口，正式 service/discovery 无调用，不得成为 fallback。

- [Microsoft Power BI Modeling MCP](https://github.com/microsoft/powerbi-modeling-mcp)：提供结构对象操作；本项目只用既有只读 List/Get。
- [Microsoft relationship semantics](https://learn.microsoft.com/en-us/analysis-services/tabular-models/relationships-ssas-tabular)：active/inactive relationship 影响过滤路径，不等同于业务词义。
- [Microsoft TMDL object references](https://github.com/MicrosoftDocs/bi-shared-docs/blob/main/docs/analysis-services/tmdl/tmdl-overview.md)：level.column 与 sortByColumn 是对象引用，level name 本身不能伪装成 column identity。

## Gate 与完成条件

### 2026-08-31 Real 集成证据

应用已按用户授权从根目录正常使用 Pydantic Settings；Agent 未查看、打印或修改 .env。Rich 15 项、完整 HTTP Chat/committed Memory、Simple 零配置四形态及 missing-temporal ZERO DAX、真实成员 A→B→A 均通过。相同 Desktop 与 exact baseline 的 17 个回合 Plan/DAX/QueryResult/VerifiedFactSet 一致，另有成员切换 3 个成功回合事实重建校验。未注册 holdout 的五形态与六类 mutation 是 fixture 验收，不声称修改或创建了现场 PBIX。

三处必要 integration 修复保持 authority：Router grouped cue 支持有界长 runtime 标识符，Catalog language_terms 保留 qualified ownership；Router 已确定的 read shape 在无效 weak intent 后仍进入 Grounding，metadata 不足澄清；find_mentions 在所有 runtime 对象类型间比较完整名称 span，不能把 Measure 名内部的 Column 子串另当显式筛选字段，独立第二字段仍保留歧义。未改变 DAX、Provider 或 QueryShape 合同。

正式 Semantic Compatibility 为 526 PASS，backend 2168 PASS/1 SKIP，frontend86 + typecheck/lint/build PASS，Golden11/1 manual-real SKIP。schema/context/catalog/grounding/warm/4-way 均有记录；少量样本存在 Provider 长尾，只证明未发现 context 重建造成明显退化，不外推长期 SLO。M5.8.1 架构和缓存策略没有变化。详细性能与整体 residual blocker 见 [验收计划](../milestones/m5/m5_8_3_model_semantic_context_plan.md)。旧 residual 已解除，temp lifecycle 已自动化；仍须 fresh local/residual 与新 exact-SHA CI success 才 COMPLETE。

保持 M5.8.2 的 421-case 基线、six routes/eight shapes、Top1/IN_SET/minimal clarification；扩展 deterministic context、metadata priority、optional override/stale fingerprint、zero-config、duplicate/relationship ambiguity、六类 schema mutation、PBIX isolation、unresolved ZERO DAX 与泄漏扫描。Sales/Education/Inventory/unknown holdout 均使用同一 builder，不新增 global domain ontology。

Rich PBIX 先做 15 项 regression，再查 context、ownership/date/member/Top1/entity/trend/multi-turn；若有多 PBIX，执行 A→B→A exact validation。记录 schema/context/catalog/grounding/turn timing；与基线比较相同 QueryResult/facts。所有自动化资源登记 ownership、finally cleanup、residual=0。

fresh Semantic Compatibility、backend、Golden、frontend tests/typecheck/lint/build、Repository Safety、Architecture、Error Ledger、Documentation/Artifact Governance、compileall、diff check、用户人工验收及 exact-HEAD remote CI 全通过后才可 COMPLETE。M5.9/M5.10 NOT STARTED，M5 FINAL=false。
