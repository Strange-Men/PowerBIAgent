# M6.5.1 — Chinese / English Localization Platform

## Baseline 与状态

2026-10-21：M6.5.1 Chinese / English Localization Platform FINAL COMPLETE。
发布判定以本提交自身 exact-SHA Full Validation、Remote Audit、HEAD=origin/main、clean/shutdown
全部成立后生效；不继承旧 SHA CI，自身提交/CI 回执置仓库外 Governance，避免循环自引用。
独立 PHASE 0：`bac2f33b093fc436615bdadb4670eb950ec1fdc0`，自身
[Full Validation 39403675734](https://github.com/Strange-Men/PowerBIAgent/actions/runs/39403675734)
SUCCESS；Remote Audit PASS；fresh fetch/main/HEAD=origin/main/worktree/staging clean。
M6.5 功能 Final SHA/CI 仍为 8e63f0b / 39400357886，不继承为本轮 CI。

## Design audit（编码前）

前端 AST 盘点：14 个生产文件共 340 个含中文字符串候选；另查 JSX text、title、aria-label、
placeholder、alt 的英文可见文本，仅品牌 PowerBIAgent 可保留。候选包含需排除的历史前缀解析；
最终 gate 针对展示边界，不扫描 logs/tests/technical IDs。外部完整 inventory 位于
PBIAgentTest/M6.5.1/Research，不能将候选数冒充最终 user-facing key 数。

| 边界 | 候选数 |
|---|---:|
| App / CloudWorkspace | 13 / 29 |
| Composer / Sidebar / ConversationView | 33 / 60 / 6 |
| Account / ResourceManager / ReportAttachment / StructuredBlocks | 19 / 69 / 8 / 8 |
| failure / API adapters / API client | 27 / 9 / 12 |
| useAuth / usePowerBIAgent | 1 / 46 |

后端 presentation/answer/report AST 共 299 个候选，包含内部 prompt、diagnostic 和 intent
匹配词，不能一律翻译。明确展示边界为 FactBoundedAnswerBuilder、StructuredPresentationBuilder、
QueryScopeDescriptor、ProfessionalReportPresenter、两个现有 Renderer 与模板、公开 API 投影。
assembly/policy/reading_context 固定文本保留 canonical ReportSpec 合同，在 Renderer 展示阶段本地化。

现有 DisplayLocalizationService 已有 runtime identity/schema-bound binding、metadata/glossary/
JsonDisplayLocalizationRegistry/bounded translation 优先级及 member display projection；必须扩展。
PresentationFormatter 现有 locale 参数但 startswith(zh) 和手写日期需要 exact locale/Babel。
StructuredPresentationBuilder 已从同一 Result/Facts 投影，必须复用，不能复制 planner。

TurnResultSnapshot 目前只保存 answer/presentation/报告引用；报告文件元数据没有完整 ReportSpec，
无法可靠从历史文本重建两语言。允许在现有 snapshot JSON 中增加 typed presentation recipe，
仅复制已验证 Plan/Result/Facts/availability/display bindings 或最终 ReportSpec；不新增 DB migration。
Decimal/date 等必须带类型往返，hash 与原始值一致；不从 answer text 解析事实，不重新计算指标。

## Locale 与 authority contract

唯一 SupportedLocale = zh-CN / en-US（BCP-47 exact）。显式用户选择优先，本地 preference
持久化；首次读取 browser language，unsupported → zh-CN。无账号 DB preference。
locale 仅 Presentation Context，不能进入 SemanticFrame/Grounding/Plan/DAX/Result/Inspection/
VerifiedFactSet/business Memory/resource authorization/model selection。

一次 factual analysis → immutable recipe → 两语言 Answer/Envelope/Report。切换不创建对话、
不改变 generation/model binding、不执行 Understanding/Grounding/DAX/Fabric IQ。投影必须通过
现有事实 validator；扩展英文 claim 检查和 locale-aware trusted fragment，不降低校验。
历史缺少 recipe 明确不可重投影，不能从展示文本反解析或静默重查。

投影 API 复用既有 owner/session/policy/generation/exact binding 的存储边界；无 locale 授权分支。
current session-bound access witness 不足时 fail closed，不为语言切换重做 IQ schema/query。
同一 ReportSpec/Facts 使用同一 Renderer，locale/resources 只改变显示；原 artifact 保持历史身份。

## Microsoft 能力与 P0 适用边界（2026-10-20 fresh）

重读 [Fabric IQ MCP 官方合同](https://learn.microsoft.com/en-us/fabric/iq/connectors/fabric-iq-mcp)
与 [Power BI RLS 官方说明](https://learn.microsoft.com/en-us/fabric/security/service-admin-row-level-security)。
既有 delegated caller、read-only tools、runtime tools/list 与既有 RLS/OLS 权限合同保持；本轮不新增
Provider、token 路径、权限、数据平面或 query capability。locale 无权授予资源访问，也不得为切换
重做 metadata/ExecuteQuery。官方服务可能返回 CSV/截断或限流，不改变本项目更保守的
12-row/N+1/8-column 边界。Admin 最小展示验收不替代独立 Test B OLS 或 Enterprise Production Seal。

## Dependencies 与 gates

2026-10-20 fresh npm registry：i18next 26.5.3（TS ^5/^6/^7）；react-i18next 17.1.0
（React >=16.8，i18next >=26.2，TS ^5/^6/^7）。pin 后用当前 React19.2.8/TS6.0.3/Vite8.2.2
实际 typecheck/lint/test/build 证明兼容。Babel 2.18.0（fresh PyPI），只格式化数字/百分比/日期；
GBP 不转换为 USD/CNY。资源全部 bundled，无远程翻译服务。

官方依据：[i18next typing](https://www.i18next.com/overview/typescript)、
[react-i18next typing](https://react.i18next.com/latest/typescript)、
[Babel numbers](https://babel.pocoo.org/en/latest/numbers.html)、
[Babel dates](https://babel.pocoo.org/en/latest/dates.html)。

Localization Completeness：双语言 key equality、duplicate JSON/semantic key、placeholder/plural/
context parity、UTF-8、unsupported fail-safe、展示边界 hardcode audit；test-only pseudo locale
不进入产品 SupportedLocale。全 UI 双语言 parity，重点验证切换不改变 auth/CSRF/generation/
conversation/model/owner/RLS/query permission。Cloud Real 仅 1 scalar + 1 grouped/trend + 1 report。

## 实施与验收

全局偏好入口固定为“设置 → 常规 → 语言”，侧栏不直接显示语言控件。复用现有设置 modal
及账户/模型/资源分类；常规页仅语言行，登录前同样可进入。切换不请求 auth、目录或 Facts。
桌面/手机中英与 test-only en-XA 扩展布局已核对，截图仅 PBIAgentTest/M6.5.1/Screenshots。

最终 local automated：Backend 10b01f6d=3839PASS/1SKIP/15既有warnings；Semantic
127a316e=819PASS；Golden e4ad24b9=11PASS/1manualSKIP；Frontend 9db4fcee=173PASS；
Typecheck/Build 3e28ff9c、Lint bc3b3bb1 PASS。Repository Safety、Architecture、Documentation、
Error Ledger、Artifact Governance、Localization Completeness 与 diff check PASS。
跳过项沿用既有手工/平台边界，不冒充 PASS；所有失败原件保留。

native Cloud Real 与 local automated 分层：

| 代表链 | 原始事实分析 | 双语不变量 |
|---|---|---|
| SCALAR m651-scalar-f5acbd3a | 1 ExecuteQuery，completed/Memory commit | zh/en/zh hash 与 raw rows 相同，ZERO IQ/ExecuteQuery/Facts build 增量 |
| GROUPED m651-grouped-49737563 | 1 ExecuteQuery，completed/Memory commit | 同上，完整 FactSet hash 列表不变 |
| Report m651-report-a6777a23 | 1 KPI、1 query、1 ExecuteQuery | 同一 ReportSpec/factual hash；zh/en/zh 与双语 view/download 分别一致，ZERO 新事实调用 |

Report 原始 Assembly 的 FactSet 一致性复核保留（同 hash），语言投影不进入构建或复核。
仓库外 minimal-proof-summary.json 只选择原生 PASS 且报告 kpi_count=report_query_count=1，
包含原件 SHA、计数与 hash，不含业务数值/行、prompt/response/token。381d4ee7 汇总 PASS。

失败与合同分类不隐藏：GROUPED 的 display hints 曾包含非最终 Plan 成员键，导致
user_facing_filter_values_invalid；4d88f665 双语言 RED → 最终逐成员 exact key 交集 →
10b375f0 邻近64PASS → native GROUPED PASS。validator/canonical state/业务事实不变。
最初测试 fixture 误用 IN 枚举，按既有 IN_SET 修正；7d2ed3a0/6d1c4345 原件保留。
Report 初始语言草稿缺 shape，被既有合同拒绝且 ZERO ExecuteQuery/Memory；补“单值”后进入
工具阶段遇 RATE_LIMITED，冷却后恢复。其“仅展示 Total Sales”未匹配既有限定词/中文 section
trigger，按旧默认覆盖生成四 KPI；aa9c9aef 仅作补充双语证明，不能称为单 KPI 验收。
最终使用既有“只看销售额”限定词并增加严格单 KPI/单 query 断言通过；不改 Interpreter、
ReportPlanner、registry 或模板，也不扩展自然语言 parser。原有输入合同不因 UI locale 改变。

前端 b4fddbef worker startup timeout 原件保留，相同配置在重型回归结束后 d08c854e、
最终9db4fcee 全量通过。Backend df4de00e=3838PASS/1FAIL（09标题定位）；恢复当前阶段标题，
79e28b50版本/本地化58PASS，最终10b01f6d全量通过，未修改检查规则或 expected。
Decimal roundtrip fixture 使用明确 synthetic 数值，不提交真实业务聚合。
typed Decimal/date、完整资源句信任、display/identity、fingerprint 同合同与资源 lease 修复见
ERR-651-001..008 / GOV-651-009，negative tests 全部保留，不降低 validator。

历史资源投影沿用资源自身 exact owner/model/schema/source/policy/current session-bound access
witness；当前 UI 选别的模型不自动切回，不取新权限，不重查 IQ metadata，失去 witness 仍拒绝。
旧历史缺 recipe 明示不可切换，保留原记录，不解析 answer 或重查事实。

2026-10-21 fresh fetch main/HEAD=origin/main=bac2f33，初始100个授权文件 hash 全匹配，新增
Settings.version 路径属本轮明确授权。只 whitelist staging，中文独立提交
M6.5.1_中英双语本地化平台；自身 SHA/CI/Audit/clean 回执单独记录，不继承 PHASE 0。
owned 5173/5174 已 graceful shutdown，宿主6caed4e4 exit0/temp cleanup成立；未移动、读取、
复制或 hash 用户 DB。owned empty fixture 仅 schema preflight d5884be7 PASS，测试资产全在仓库外。

## 严格范围与 Final

M5 Frozen Core、12-row/N+1/8-column、relationship cardinality CONTRACT_GAP、Test B
DEFERRED_BY_TEST_PRINCIPAL → M6.6 保留。不增加 cache/reuse/Provider/Shape/template/部署架构。
不进入 M6.5.2 Web / SSO Productization、M6.5.3 VM Remote Deployment & Internal Pilot 或
M6.6 Enterprise Production Readiness Seal；用户已配置 VM 仅是 M6.5.3 基础，Pilot 不等于 Seal。

全部 fresh 本地 gates、最小 Cloud Real、中文独立提交、自身 exact-SHA Full Validation、
Remote Audit、HEAD=origin/main、clean/shutdown 成立后才 FINAL COMPLETE，随后 STOP。
