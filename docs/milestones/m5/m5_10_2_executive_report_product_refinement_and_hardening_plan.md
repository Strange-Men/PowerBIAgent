# M5.10.2 — Executive Report Product Refinement & Hardening

## 状态与基线

- 状态：COMPLETE（本地产品收口；发布以本提交 exact-SHA CI success 为证据）
- 起始基线：`main@070a35e230ba7d52bd39ed150c144c5dc3aae5b2`
- M5.10：Complex report foundation COMPLETE
- M5.10.1：Professional Renderer implementation COMPLETE
- M5.10.3：NOT STARTED
- M5 FINAL：false

## 本轮目标

M5.10.2 只收口四个相邻领域：明确报表请求的产品路由、`FULL_AVAILABLE` 确定性覆盖、专业报表 presentation-only projection 与 executive HTML 产品视觉，以及不改变既有持久化架构的 report-specific hardening。

唯一事实链保持为：

```text
QuestionRouter → runtime schema → ModelSemanticContext / Grounding
→ CanonicalQueryPlan → deterministic DAX → Power BI → QueryResult
→ Result Inspection → VerifiedFactSet → ReportDataSnapshot
→ ReportReadingContext → ReportSpec → fixed Renderer → ReportArtifact
```

LLM 对模板事实选择、DAX、业务值、指标定义、异常、刷新时间、HTML、CSS、SVG、排名和聚合的 authority 均为 0。

## 失败复现与根因假设

1. `QuestionRouter` 的中文 report verb/noun 正则把中间跨度限制为 8 个字符，导致“生成一份完整的销售经营分析报表”与“给我一份销售经营分析报告”落入 `BUSINESS_DATA_QUERY`，随后可能进入指标澄清。
2. Report intent 已有“完整”触发词，但没有显式 coverage type，audit 不能区分用户请求完整覆盖与普通请求；弱 LLM 的行为边界也不够自解释。
3. Real report planning 使用 `max_tool_calls - 2`，默认只允许 6 个 report queries；Rich schema 即使 9 项均 available，也会因通用工具预算被静默记入 unavailable。
4. Executive Renderer 直接输出 canonical model/source/status/unit/timestamp，因此把 `local_desktop:*`、`local_mcp · real`、`cannot_determine`、`UNKNOWN`、`semantic_measure` 和 ISO microseconds 提升成主报表语言。
5. production snapshot 的 `queried_at`、`snapshot_at` 均复制 `SalesReportData.generated_at`，无法表达查询取得、不可变快照和 artifact 生成三个不同事件。

## 确定性合同

### Report routing

同一语句中存在 report generation verb 与 report noun 时，Router 输出 `REPORT_REQUEST`；只有 report noun、且问题询问报表中某项业务数据时仍为 `BUSINESS_DATA_QUERY`。显式选择模板不单独构成 report intent。

### Coverage

`ReportCoverageMode` 仅有：

- `REQUESTED`：用户明确请求的 registry-owned sections；
- `FULL_AVAILABLE`：selected template ∩ runtime capability ∩ registered section catalog ∩ non-empty VerifiedFactSet evidence 的全部可用 sections。

明确“完整/全面/全部/完整经营分析/完整销售分析/全部经营模块”的 report request 必须为 `FULL_AVAILABLE`。该模式的 requested set 固定为全部 registry section IDs，bounded LLM weak draft 不能缩减或扩展它。缺能力不生成 placeholder、fake zero 或 fallback section。

Execution audit 固定记录 `requested_coverage`、`requested_sections`、`resolved_sections`、`unavailable_sections`（含原因）与 `dropped_after_facts`（含原因）。

### Professional presentation projection

新增 presentation-only projection。它只把 canonical context 映射为安全的用户显示 label、friendly model/source、状态文本、单位文本和带明确时区的时间文本；不得修改 canonical identity、值、scope、timestamp meaning 或 provenance。exact identity/source enums/canonical timestamps 仅保留在低权重 audit footer。

无用户/application timezone authority 时，aware datetime 统一显示 UTC；naive datetime 明确显示“时区未声明”，禁止暗自加 8 小时。runtime model display name 可用时优先使用，否则显示“当前 Power BI Desktop 模型”。

### Timestamp provenance

- `queried_at`：本轮 report query results 全部取得时的 application clock evidence；
- `snapshot_at`：VerifiedFactSet 完成并构建 immutable snapshot 时的 application clock evidence；
- `generated_at`：ReportData/ReportSpec/artifact generation 阶段的 application clock evidence；
- `data_updated_at`：仅来自 runtime refresh metadata，缺失保持 UNKNOWN。

四者不得互相冒充。

## Product Visual Acceptance

保留 18 × 4 geometry matrix，并对真实 full professional report 的 1440 desktop 与 430 mobile 增加产品检查：

- Header、compact context、KPI、hero trend 的层级和首屏位置；
- desktop context 不占满第一屏，KPI 位于首屏，hero trend 具有主要视觉权重；
- 主阅读区不出现 opaque identity、canonical enum、raw status 或 ISO microseconds；
- full fixture 包含 Region、Category、Top Products、Top Customers；
- section 间距、密度、长名称与 audit footer 可读。

截图只写入调用者显式提供的 automation-owned 临时目录；验收后删除。

## Hardening 范围

- 两模板 template identity 贯穿 selection → plan → data → spec → renderer → artifact → metadata → recovery；禁止 executive → simple fallback。
- 复用既有 ReportRepository transaction/compensation；对 memory commit 失败补 report artifact compensation，不建立第二持久化管线。
- unknown/stale template、PBIX identity/schema drift 继续 fail closed；前端 catalog 删除选项后清空选择，不自动改选。
- report-specific Simple/Executive 并发、query/assembly/render/persist cancellation 与 shutdown 只验证后果，不修改 M5.9 worker pool。
- `REMOTE_MCP` 仅完善 friendly metadata/source projection contract，不实现 endpoint、auth、request schema 或 transport。

## 交付顺序

1. Spec / plan 与 failure evidence。
2. Router positive/negative regressions。
3. `ReportCoverageMode`、FULL_AVAILABLE planner/audit regressions。
4. Presentation projection、timestamp provenance 与 renderer regressions。
5. Executive layout/CSS 与 product visual checklist。
6. Lifecycle、stale、concurrency、failure atomicity、安全测试。
7. Focused、Semantic、backend、Golden、frontend、治理与 compile/diff gates。
8. Rich/Simple Real PBIX、1440/430 人工视觉与 residual=0。
9. 文档/版本同步、白名单 commit、push main、exact-SHA CI。

## 禁止范围

不实现 YoY、MoM、Forecast、Budget、Target、Map、AI Insight、统计异常、任意 dashboard/field report、PDF、JavaScript、Remote MCP、Entra、PostgreSQL、Deployment；不修改 M5.9 worker-pool 架构，不启动 M5.10.3。

## 完成语义

只有正常产品功能无已知 P0/P1、全部 fresh gates/Real/Browser/mutation/residual/exact-SHA CI 通过后，M5.10.2 才可标记 COMPLETE。M5.10.3 只保留 Final Real E2E、stress、mutation、historical closure verification 与 exact-SHA final closure；M5 FINAL 保持 false。

## Fresh Evidence

- Failure reproducer：明确中文完整报表短语在旧 8-character gap grammar 下误路由；Rich 9-section capability 在旧六查询预算下被静默裁减；旧 lifecycle time 三字段复用；Memory commit/cancellation 后 artifact orphan 均已稳定复现并进入永久回归。
- Focused：report domain 209 PASS；M5.10.2 product 22 PASS；双模板 lifecycle/failure/cancellation/restart 补强矩阵 27 PASS；三类并发 3 PASS；browser mutation 4 PASS；presentation/fixture 回归 49 PASS。
- Full：Semantic Compatibility 775 PASS / 122 production backend files；backend 2706 PASS / 1 manual-real SKIP；Golden 11 PASS / 1 manual-real SKIP；frontend 91 PASS + typecheck/lint/build。
- Governance：Repository Safety 395、AI Error Ledger 84、Architecture 139、Documentation Governance、Artifact Governance 全部 PASS；targeted compileall 与 `git diff --check` PASS。
- Real：Rich PBIX exact-phrase TurnService 9/9；Simple PBIX 4 available + 5 unavailable-with-reason；两者均 DeepSeek-only、DAX LLM authority=0、Renderer LLM authority=0、artifact/session/worker residual=0。双模板 Real parity=true。
- Browser/manual：TEST_FIXTURE 18×4 = 72/72；真实 Rich report 1440/1024/768/430 = 4/4；人工检查 1440 desktop 与 430 mobile 的 header、compact context、first-viewport KPI、hero trend、完整可用业务区和低权重 audit footer通过。
- Mutation：raw technical token、oversized Reading Context、FULL_AVAILABLE section omission 三类永久 mutation gate 以及 M5.10.1 既有 P0/overflow/renderer identity/fact mapping 均能先红后绿；破坏实现未保留。
- Residual/security：所有 automation-owned HTML/screenshot/temp resource 精确清理；无用户资源删除；`.env` 未读取、未打印、未修改。无已知 P0/P1；Remote MCP/Entra/PostgreSQL/Deployment 仍在授权范围外。
- CI forward-fix：首个 implementation SHA 的远端 Full pytest 单次失败，而当前 checkout 与不含 `.env`/`local_state` 的 clean clone 都以 CI 同构命令 2706 PASS / 1 SKIP。新增 report Event/barrier 测试的 3 秒同步阈值仅属于 runner scheduling guard，现提高到 bounded 15 秒；不改变任何产品 deadline、runtime worker 或 cancellation 语义。发布仍只接受最终 forward-fix SHA 的 completed/success。
