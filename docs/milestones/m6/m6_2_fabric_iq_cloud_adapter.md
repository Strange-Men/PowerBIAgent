# M6.2 — Fabric IQ Cloud Data Plane Adapter

2026-10-10；用户明确批准M6.2 implementation、targeted Real、Phase A与Final seal。
开发阶段Settings.version保持M6.1，Real与Phase A CI通过后最终seal更新为M6.2。
M6.2 COMPLETE / M6.3 READY仅以最终自身exact-SHA CI和remote audit生效；M6.3未实施、须独立批准。

## Current Reality Audit / Cold Start

main、clean；fetch前后HEAD==origin/main==`1c71dee714b20bdb8ea4db11d7cf984ed42ac125`。
M6.1 AuthService/PrincipalContext/opaque session/MSAL broker已实现；Cloud data plane未实现。
已读AGENTS、Charter、CLAUDE、07/08/09、ADR-020、M6.0/M6.1 evidence、README/CHANGELOG、
Error Ledger有效规则与涉及Auth/PowerBI/ToolGateway/DTO/failure/settings/main及邻近tests。

## Official Contract（fresh 2026-10-10）

| Source | Updated | Verified contract |
|---|---|---|
| [Microsoft Fabric IQ MCP](https://learn.microsoft.com/en-us/fabric/iq/connectors/fabric-iq-mcp) | 2026-09-15 | GA；Streamable HTTP；delegated-only；现有RLS/OLS继续生效；三Power BI scopes；runtime tools/list authority；selector；CSV可能截断 |
| [Official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) / [Streamable HTTP API](https://py.sdk.modelcontextprotocol.io/api/mcp/client/streamable_http/) | 页面未提供 | 自定义http_client、headers/auth、ClientSession initialize/list_tools/call_tool与context lifecycle；实际已锁定/安装mcp==2.0.0，审计installed source |
| [Power BI Execute Queries](https://learn.microsoft.com/en-us/rest/api/power-bi/datasets/execute-queries) | 页面未提供 | REST上限100000 rows/1000000 values/15MB/120请求每分钟；200也可能含错误。仅作为保守风险参考，不假定IQ拥有完全相同REST合同 |

公共endpoint：`https://fabriciq.svc.cloud.microsoft/v1/mcp/fabriciq`。
官方private-link显式endpoint：`https://api.fabric.microsoft.com/v1/mcp/fabriciq`；无自动fallback。
每个HTTP请求固定`X-Variants: Fabric.Routing.FabricIQ.V1`，AuthService broker注入delegated Bearer。
Power BI `Item.Read.All`、`Item.Execute.All`、`Dataset.Read.All`；无Workspace.Read.All。
不支持service principal/application-only。tenant home region须支持全部Fabric workloads；
Power BI-only regions/sovereign clouds不支持；无需Fabric/Premium capacity，不要求workspace role/Build。
IQ maxRows默认250；可显式请求更大，但官方未提供IQ绝对row/byte上限或完整性保证。
大结果embedded CSV不保证complete；不把REST限制、maxRows或成功HTTP当作完整性证明。
错误有MCP isError、结构化Error与text三类，runtime逐项验证，不输出raw error。

## Accepted P0 implementation design（编码前）

| Risk | Control / failure-first verification |
|---|---|
| delegated token exfiltration | endpoint精确两项allowlist；无port/query/fragment/credentials/path变化；HTTP client禁redirect/trust_env；每请求校验目标并从broker取token；拒绝未知host |
| confused deputy / A-B reuse | factory仅绑定AuthService.require_session确认的immutable PrincipalContext和opaque session；每次HTTP调用前、结果消费前复验；binding带tenant/principal/session/authorization epoch；他人key在MCP前拒绝 |
| OAuth duplication / browser token | 只复用AuthService.get_delegated_token；无client bearer、tenant、X-User-ID输入；token仅Auth/Transport内存 |
| resolver parse mistaken for authorization | server-owned bootstrap → Resolve candidate → schema identity/access检查 → 才创建随机opaque key；失败ZERO binding |
| stale capability / contract drift | 每个SDK connection initialize→完整tools/list分页→验证required args/types；允许额外tools/optional字段；关键删除/改型/新required参数fail closed；safe canonical fingerprint |
| false metadata authority | cloud DTO显式None表示未知hidden/expression/system/key/direction/cardinality；PK/FK原始证据在provider字段保留，未有方向证据不投影成from/to关系；不解冻Core |
| incomplete results | 校验模型identity/单table/columns/rows/count/null/errors/CSV；当前无已验证complete-response semantic，全部Cloud结果以truncated=true保守表达；additive truncated:false不能自行授予complete authority |
| cache / revocation / lifecycle | 只request级绑定/schema，绝无跨principal cache；每operation拥有短SDK context并finally关闭；request teardown清binding；logout/expired晚到结果拒绝 |
| retry multiplication | Adapter/HTTP不重试query；SDK SSE resume仅恢复同request，不重发query；transient query retry仅既有ToolGateway有界policy；Real targeted harness设0 query retries |
| raw SDK/HTTP logs | SDK与HTTP emitter filter保留severity、安全category，清payload/exception；safe typed PowerBIAdapterError→既有唯一FailureInfo mapper |
| product ownership bypass | ENTRA_BFF只增加app-scoped无principal factory；不初始化business persistence/Memory/LLM/report；全部旧/api仍关闭；无永久debug API |

M6.3 RLS/OLS User A/B与persistence ownership、M6.4 Catalog/Product E2E均不在本轮。
单账号真实smoke不证明RLS/OLS验收。没有安全他人资源fixture时明确UNAVAILABLE。
ADR-020决策不变，无需新ADR；Legacy RemoteMCP保持不改。

## Implementation / Validation evidence

### Implementation

独立FabricIQPowerBIAdapter实现既有PowerBIAdapter接口，Legacy RemoteMCP未修改。
ENTRA_BFF生命周期仅新增无身份factory；dependency创建request/session-bound adapter并finally aclose。
CloudSemanticModelRef携带随机opaque key、tenant/principal/session/authorization epoch和schema-before-bind证据。
每次operation重新initialize/tools/list并验证required fingerprint；无跨principal cache、无Local/Mock fallback。
SDK mcp==2.0.0使用httpx2==2.9.1；每HTTP frame重新验证session/endpoint并由Auth broker注入token/selector。
Transport/Adapter没有query retry；现有ToolGateway是唯一bounded transient retry owner。
primary operation失败不会被teardown认证失败覆盖，logout后晚到结果仍拒绝消费。

Schema DTO只作向后兼容None扩展；cloud未提供的hidden/expression/system/key保持unknown。
ActiveRelationships的qualified PK/FK保留在excluded provider_metadata，不能进入Trace model_dump；
from/to、cardinality、filter direction映射NOT_VERIFIED，不伪造canonical关系。
QueryResult严格检查identity、单表、列名/重复、row width/count、标量/null、errors与CSV一致性；
无官方/运行时complete semantic时统一truncated=true，不静默clamp或宣称Verified-complete。
bounded member lookup仅对已验证table/column构造deterministic TOPN(limit+1) DAX。
具体为SELECTCOLUMNS(DISTINCT(grounded_column), fixed_alias, grounded_column)，
随后TOPN/order by fixed_alias；不反向解析Fabric友好列标签来创建canonical identity。
兼容性probe与members只接受自身显式alias的bare/bracketed形式。
Runtime structuredContent.artifact_citation是补充引用，text JSON拥有schema/result；
引用ArtifactId与正文必须一致，Name同时存在时也必须一致；引用单独存在不能授权，
IconUrl/Description/Url不参与identity或执行authority，绝不跟随这些URL获取token/data。
重复的完整payload mirrors仍须完全一致，额外不明text/error不被成功rows掩盖。

### Local automated（2026-10-10）

| Gate | Evidence |
|---|---|
| Failure-first | Adapter import缺失RED后实现；operation QUERY_REJECTED被teardown AUTH_REQUIRED覆盖的negative RED后minimal forward-fix |
| M6.2 focused | Adapter、真实SDK+fake HTTP peer、Auth→Token→Adapter与API boundary：81 passed（Real合同对照后补充轮） |
| Backend normal full suite | 2964 passed / 1 skipped / 2 deselected，780.85s；收集在补充cloud tests之前；后续cloud变更由上述81 tests验证 |
| Semantic Compatibility | PASS；819 passed；扫描139 production files |
| Golden | 11 passed / 1 manual Real baseline skipped |
| Existing Auth/Settings/Failure regression | 88 passed |
| Frontend | 11 files / 112 passed；初轮74通过后3个worker启动超时，无assert失败；重任务结束后原命令重跑全部通过 |
| Typecheck / lint / build | PASS / PASS / PASS（1817 modules） |
| Governance / architecture / safety / ledger / artifacts / strict diff | PASS；最终文档同步后再验 |

Final seal本地复验：Settings、documentation governance与全部M6.2 focused合计159 passed；
documentation/security/architecture/ledger/artifact gates与git diff --check再次PASS。
repo外临时smoke server已停止，恢复正式backend.app.main；health=200、临时route=404、
anonymous旧product API=401。临时harness与脱敏证据仅保留repo外，不作为产品入口。

全量后端有8条既有MSAL warning，未隐藏/降低校验。
Repository Safety首次发现synthetic credential命名后按既有测试安全标记修改；扫描规则未改。
未运行本轮豁免的51200 stress、130-turn、DeepSeek/Kimi Real或report browser matrix。

### Local Real — authenticated two-model acceptance（2026-10-10）

两个指定测试模型已从Fabric工作区UI恢复URL；只保存repo外server bootstrap，未写入仓库。
临时smoke harness只存repo外，Depends(require_principal)，拒绝client参数，复用真实M6.1 Auth broker。
本地gates完成后按用户第31节停点，由用户真实组织账号Microsoft登录；无fake Principal/token。
复用既有M6.1 AuthService/validated Principal/MSAL delegated broker；未改Entra配置或增加scope。
最终串行完整验收started_at_utc=2026-10-09T18:17:16.414594+00:00，耗时分类60_to_180s，status=PASS。

| Probe | M3 Rich Test | Logistics Test |
|---|---|---|
| Resolve / schema-before-bind | PASS | PASS |
| Schema tables / measures / active relationship evidence | 5 / 4 / 4 | 4 / 7 / 3 |
| Scalar deterministic DAX | PASS；1 row / 1 column | PASS；1 / 1 |
| Grouped deterministic DAX | PASS；4 rows / 2 columns | PASS；5 / 2 |
| Bounded members（limit=5） | PASS；4 members | PASS；5 members |
| Invalid DAX | QUERY_REJECTED | QUERY_REJECTED |
| Principal binding | PASS | PASS |

模型identity与随机server_model_key相互分离PASS；每项complete_claimed=false，未伪造complete authority。
虚构all-zero模型URL：schema失败SCHEMA_UNAVAILABLE，ZERO binding PASS；不将Resolve parse当授权。
main adapter wire证据：initialize=13、tools/list=13、tools/call=14；所有HTTP frame都经同一
endpoint/session校验与Auth/selector hook；negative adapter亦复用该transport，不计入上述计数。
Capability fingerprint：`3db4195269815aa856b0cfa934c288cc7af6064a706f8110da98e446ed217d18`；
client mcp=2.0.0，selector=Fabric.Routing.FabricIQ.V1，endpoint category=public。
只保存counts/shape/boolean/safe error/hash；无真实业务值、GUID/URL、token或完整schema/query dump入库。
CSV/大结果只有synthetic fixtures验证，未做真实大结果验收；private-link只有allowlist验证，未实连。
真实Entra登录与broker已验证；最初citation误判、IconUrl差异、friendly column label误判均
先由synthetic failure-first复现，再做provider-boundary minimal fix；没有忽略错误text或降低校验。
早期临时harness阶段标记与重复刷新问题已修正，最终验收采用app级稳定串行锁和fresh完成时间。
临时shape诊断曾遮蔽invalid-DAX错误，修复诊断后真实两模型均QUERY_REJECTED；生产mapper未为此放宽。
81 focused tests还覆盖actual SDK isError→QUERY_REJECTED、ZERO query retry与raw detail不外泄。

### Remote exact-SHA CI status

Phase A：`daeb5b63e81364da97eabdd0d20b835c868388df`，commit `M6.2_FabricIQ云端数据适配器候选`。
[exact-SHA CI37972741912](https://github.com/Strange-Men/PowerBIAgent/actions/runs/37972741912)
push事件、completed/success；Full Validation (Windows)与全部23 steps实际success，无skipped step。
fetch后origin/main仍为该Phase A SHA，才更新Settings.version=M6.2与本轮final seal文档。
最终commit `M6.2_FabricIQ云端数据链路封板`；自身SHA不写入自身提交。须查询当前checkout
exact SHA的独立Final CI completed/success，全部required steps成功，fresh fetch后
HEAD==origin/main且worktree clean，才判定M6.2 COMPLETE / M6.3 READY。
不得继承Phase A或历史CI；Final SHA/CI/remote audit结果在最终交付报告给出。
没有安全他人资源fixture：UNAVAILABLE IN CURRENT TEST ENVIRONMENT；不宣称RLS/OLS A/B验收。

### M6.3 / M6.4 handoff

M6.3须独立批准，承担persistence ownership与正式跨用户RLS/OLS验收。
M6.4才引入Fabric REST scoped Catalog与完整Product UX；本轮不增加Workspace.Read.All或catalog API。
ENTRA_BFF旧chat/history/report/model APIs继续fail closed，Cloud Product E2E仍NOT YET。
