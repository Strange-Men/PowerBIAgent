# M5.8.3 — 实施与验收计划

状态：验收收口；正式 COMPLETE 以 fresh local/residual 与对应提交 CI success 为条件。规范：[ModelSemanticContext](../../specs/model_semantic_context.md)。fresh evidence 的唯一当前摘要见 [09 Handoff](../../09_context_handoff.md)。

1. Safety、Cold Start、A–E authority 审计及规范冻结：完成。
2. 原三个 P0 reproducer 与兼容迁移：完成；未恢复 glossary schema authority。
3. immutable context、runtime metadata、Catalog 和 strict optional override：完成。
4. 真正异构四域、unknown holdout、mutation/isolation/ambiguity 与 ZERO DAX：完成。
5. Rich 15、完整 Real Chat/Memory/facts、A→B→A 与 warm/4-way：完成。
6. fresh full gates 与文档同步：本地测试、Documentation Governance、compileall 和 diff check 全部 PASS。
7. 全轮 residual 按 FS 检查，版本同步后白名单 commit、push；对应新 exact-SHA CI success 后正式 COMPLETE。

## 当前完成条件审计（2026-08-31）

| 要求 | authoritative evidence | 状态 |
|---|---|---|
| typed immutable context、runtime structure authority | 同一 deterministic builder、隐藏/system 排除、ownership/metadata fingerprint、真实 schema audit | PASS |
| alias/date/month 三个原 P0 | explicit exact-model registry，旧结果断言不变；Rich scalar/bounded trend | PASS |
| optional override / stale fingerprint / no schema copy | v2 validator、runtime references、六类 mutation、真实 transient override 隔离 | PASS；生产默认 overrides=[] |
| Sales/Education/Inventory/unknown | 四种不同拓扑和字段结构，正式 Chat API 与 runtime-only candidates | PASS；受控 adapters，不冒充四份真实 Desktop |
| zero-config | 未注册 holdout fixture 五 shapes；无 override 的 Simple Desktop 四 shapes，缺失 month evidence 时 ZERO DAX | PASS |
| 六类 schema mutation | rename/remove/duplicate/relationship/description/temporal rebuild 与旧 override 拒绝 | PASS（fixture）；未修改用户 PBIX |
| A→B→A | schema/context/override/temporal、13 fields/122 members；完整 Chat/Memory 和异成员拒绝 | PASS；不 fallback 其他 PBIX |
| Rich 原 15 项 | 正式 HTTP、真实 Provider/Local MCP；原执行或最小澄清断言 | PASS；未降低原断言 |
| facts 不变 | exact baseline 对比 17/17 Plan/DAX/QueryResult/VerifiedFactSet 相同；成员隔离补充 3 个事实重建校验 | PASS；无真实行/数值落盘 |
| performance | warm、schema/context/catalog/grounding、4-way 与 LLM stage 观察 | 未见 context 构建明显退化；尾延迟限制见下 |
| Semantic Compatibility | 526 PASS / 111 production files 扫描 | PASS；含原 421 合同 |
| backend/frontend/Golden | 2168/1 skip；86 tests + typecheck/lint/build；11/1 manual-real skip | PASS |
| governance | Repository Safety337、Architecture128、Error Ledger45、Artifact Governance | PASS；Documentation/compileall/diff check 同步后也 PASS |
| residual | 两个旧目录不存在；新完整验证副本自动清理，四种受控 prefix 最终只读扫描无目录 | PASS，实际 residual=0；不是由 warning 状态推断 |
| commit/push/new-SHA remote CI | 使用本轮指定中文标题；当前提交 SHA 与 run 仅进入最终报告 | 新 exact SHA completed/success 才 COMPLETE |

## Real 运行与证据边界

用户明确授权应用通过 Pydantic Settings 正常加载根目录 .env。Agent 不查看、打印或修改文件，不把凭据送到聊天/文档。先前只检查 Process/User/Machine 环境变量而认定无 Provider 的结论已撤销；根目录 Real 后端已实际启动并完成验收，结束后关闭。

三个手工入口：`model_semantic_context_smoke.py --members` 消费实际只读 MCP metadata/member；`semantic_context_real_acceptance.py` 启动自有 uvicorn HTTP 后端、管理 owned SQLite/API teardown；`runtime_semantic_comparison.py` 在临时目录载入 exact committed baseline 与当前源码、使用相同真实 Provider/Desktop 比较内存中的规范化 Plan/结果/facts。所有入口都只能手工显式调用，不进入 CI Real 网络链。

正式 registry 不自动写入；验收仅在自有临时目录把用户指定的 Rich 模型与已审计的 inert profiles 按 exact key/identity/fingerprint 显式绑定。Simple 无任何 binding。opaque key 的每进程 HMAC secret 不变；比较器只观察原 identity 输入并返回原 key，在两个进程身份摘要相同后对齐验收投影，不改变生产模型 identity 或 cache。

性能有效比较：warm mean 5742.25→2433.50ms；4-way wall 5848.79→7193.27ms。当前尾部 Intent 5750ms/QueryPlan LLM 4750ms；此前曾有 33.64s LLM 长尾，不能隐去。另一组 warm 1812.50→1996.25ms，说明网络/Provider 抖动使少量样本不能当长期 SLO。独立 context 1.171/0.521ms、catalog 0.261/0.148ms，warm profiler catalog 0–16ms、context 低于现有分辨率，session reuse=1。没有为此改 worker/TTL/singleflight/concurrency，没有提前开展 M5.9。

## Real 集成修复

- ERR-583-004：ownership SQLite 只读 probe 显式 close；正常/异常释放 2 例及 artifact unit12 PASS，不改 Memory semantics。
- ERR-583-005：qualified runtime 名称的 GROUPED cue 与 language_terms；四域8 API +1 unit 正反回归。Router 是必要 integration exception，只修有界名称跨度，不改变 routes/shapes/slot authority。
- ERR-583-006：Router 已确定通用只读 shape 后，无效 Intent weak draft 仍应进入 runtime Grounding；缺失 temporal evidence 得到 clarification/ZERO DAX，不修改 Provider。
- ERR-583-007：完整 runtime 名称跨 Measure/Column 类型占有文本范围，避免内部子串产生假筛选字段；独立第二字段仍 ambiguous。4 个失败 reproducer → 6 PASS，完整 Compatibility526，Real member A→B→A PASS。

## 自动 temp 生命周期与 truthful residual

旧目录 `powerbiagent-m583-validation-1788105076049` 和 `powerbiagent-context-real-x9t8igaw` 均已人工清理且 Test-Path=False；指定两种前缀的首次只读扫描为零，不再作为 blocker。

`owned_acceptance_tempdir` 统一 Real、metadata audit、baseline comparison 和完整 validation 副本。受控 mkdtemp 新建私有目录，写入本项目/M5.8.3/run UUID/exact path/prefix marker；finally 在 PASS/FAIL/exception/cancellation 下核验 marker、路径及原目录身份，然后删除。拒绝未知前缀、ownership mismatch、reparse point；没有 shell wildcard 删除、权限改写或 GC 绕过。comparison/validation 的自有子进程与管道先退出关闭。

15 项永久回归覆盖：四种前缀正常 cleanup、validation exception、真正 stale-mutation failure、Real 入口 A→B→A 中途失败、async cancellation、正常/异常同时遇删除拒绝、三类 ownership mismatch、非法前缀及无法检查目录。模拟拒绝后的真实目录由测试外层 fixture 回收，不依赖用户手工删除。

cleanup failure 仅为明确 warning（路径/原因）和真实 residual，不覆盖原失败，不属于产品语义 P0；但存在或无法检查目录时绝不报告 residual=0。常规流程不再要求用户手工清理。只读 FS 扫描与每次 finally 的结果是 release residual evidence，不能以预计 cleanup 成功代替。强制 kill/断电的恢复不在本轮承诺，M5.9 未开始。

M5.8.1 architecture、M5.8.2 authority、deterministic DAX、QueryResult/VerifiedFactSet/Memory factual authority、Provider、Report 保持冻结。无 Redis/RAG/Fabric Ontology/Global Ontology/Vector DB；M5.9/M5.10 NOT STARTED，M5 FINAL=false。

## 2026-08-30 检查点：P0 FAIL 后停止

- 初始 421-case Semantic Compatibility PASS。
- 新 context 缺失的 failure reproducer 已复现；首轮 focused 为 37 PASS/4 FAIL，均是新测试把不含明确单项问法的 ranking 误期望为 Top1。按现有 `_extract_top_n` 合同改为明确“哪个”问法，未修改 M5.8.2 grammar，随后 41 PASS。
- 正式 Semantic Compatibility：459 PASS/3 FAIL。失败为既有绝对月份日期角色、订单别名及 Chat 月趋势；未对 FAIL 执行生产修复，按用户要求停止。
- 初稿的四 domain 参数共用相同结构，不是完整 cross-domain acceptance；Real、新字段协议证据、latency、full gates、人工验收、residual/CI 完成条件均不得声称已通过。
- 下一步须解决 default glossary 移除与已有显式 business language/date binding 的安全迁移，不得让旧 binding 跨 opaque PBIX 复用；禁止降低 frozen regression 的断言。
