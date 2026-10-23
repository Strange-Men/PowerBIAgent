# M6.5.2 FIX3 Round 1 — Semantic evidence / conversation audit

状态：本地核心问数验证完成；发布按本提交自身 CI/Remote Audit 生效。基线 d7f2e4d；不继承历史 PASS。用户已另行授权将人工确认的 `.env.example` 一起提交，内容不改。

## Root cause 与 authority

Fabric IQ → normalize_schema 已保留 ActiveRelationships PK/FK 原始声明于
provider_metadata，relationships=[] 是刻意拒绝未经证明的 Core edge，并非原始数据丢失。
真实缺口是 Context/Catalog 没有正式消费这些声明；DisplayName/Expression 即使提供也被丢弃。
本轮保留这些字段，表达为分级证据；不将 PK/FK 或方向文字推断成 cardinality、filter direction、
hierarchy、default date。未提供、提供空集、尚未观察三种状态独立保留。

ModelSemanticContext 统一承载已规范化 tables/objects/relationships/hierarchies/temporal evidence
及 provider declarations/provenance。Catalog 为正式消费层，仍使用原有 bounded selector。
只读 Capability Profile 绑定同一 schema fingerprint；列出 scalar/grouping/temporal/search 能力。
它没有 selection、plan、DAX 或执行方法。Template compatibility 未取得正式证据即 UNKNOWN。
未映射 hierarchy 原文只作 LINGUISTIC_HINT；不会变成 CanonicalQueryPlan 中的层级。

Microsoft 官方合同（2026-10-23 重查）：
https://learn.microsoft.com/fabric/iq/connectors/fabric-iq-mcp
提供 schema、metadata、ValueSearch 与 current-principal 授权；没有承诺 ValueSearch
complete 证明全模型字段穷尽。exact existence 与 field uniqueness 分开；未能排除竞争字段时澄清。
字段已有正式 proof 时，多 measures 进入原有同一个 plan；不增加 QueryShape。

## Conversation / Pending 生命周期

顺序：current explicit grounded > scoped pending > last successful committed。
DATA/REPORT 在 forced-mode 重构之前验证 relation/changed_slots/referenced_context_slots 显式存在；
缺失进入既有一次 repair，仍缺失则拒绝。GENERAL 保持 reset、no-tool、no mutation。

Grounding 后统一保存本轮条件，再进入 shape/plan/downstream validation 和事实执行；
member evidence 异常保存 partial outcome，异常仍沿原 typed failure 通道传播。
unresolved time/member 保存 language-only obligation，不是 canonical identity 或执行权限。
不支持的请求不创建新的可执行 pending；已有 unresolved chain 不因该失败而清除。
仅成功 commit、明确 fresh/abandon、模型/指纹或会话隔离边界清除或拒绝旧 pending。
Repository 按 conversation/runtime 隔离，merge 再复验 conversation/model/fingerprint/mode。

永久回归映射：

| 不变量 | 证据入口 |
|---|---|
| unresolved → measure/member replacement；lookup/shape failure | test_fix3_semantic_core.py |
| explicit > pending；失败不得 commit | test_chat.py::TestPendingClarificationProductionPath |
| fresh 不继承旧条件；follow-up compatible inheritance | test_chat.py::test_time_replace_fresh_follow_up_and_failed_turn_boundaries |
| model/conversation boundary | test_fix3_semantic_core.py 的 scoped pending 负例及 Cloud boundary tests |
| GENERAL 不消费 pending / business state | test_chat.py::test_conversational_turn_does_not_consume_pending_business_state |
| 缺失对话合同拒绝/repair | test_fix3_semantic_core.py 的 omitted conversation contract 三负例 |
| 未知模型无 override 的能力与证据分类 | test_fix3_semantic_core.py 的 provider declaration/catalog 回归 |

## 验证与停止边界

本轮 Full Backend 已完成（bcf6e352），后续按用户最新要求仅运行必要 affected regression，不重复全套。
Architecture、Semantic、Golden 与专项/受影响回归分层留于仓库外；最终提交自身 CI 独立验证。
证据在仓库外 PBIAgentTest/M652F3R1；早期短路径副本使用 Git 基线样例；用户确认后最终副本同步实际 `.env.example` 并重新扫描。
单独授权的安全修复仅识别明确的人类占位说明，保留真实/疑似凭据、嵌入凭据及 `.env` 拒绝负例。不得读取用户 DB/Secret 或转储真实响应。
Real 按用户最新固定范围：Online Retail 四条（总销售额、France H1、换 Quantity、
15056BL 双指标）和「PBI_实战1_快速穿越」四条（scalar、Top5、真实成员筛选、
显式日期），八条 Understanding / canonical objects / Plan / DAX / Answer 均正确。
陌生模型没有 production identity literal 或专用 override；全部通过真实 Entra、DeepSeek、
Fabric IQ 和 SQLite，FABRIC_TEST_MODE=false。回执只保留逐层判定，不转储真实回答/数值。
Real 发现并修正两个根因：fieldless ValueSearch hit 原先一律澄清，现由原有完整 Catalog
语义选择与独立 exact existence 共同证明；用户显式日期字段原文不再被丢弃或强制视为分组。
仅时间约束的无分组聚合若被草稿错误标为成员筛选形状，进入既有 repair，不静默改 Plan。
Getting Started 模型返回带货币符号/千分位的 Decimal wire string，严格数值合同正确拒绝，
ZERO Facts/commit；该格式处理按用户排除范围留 backlog，不计为 Real PASS。
用户 `.env.example` 注释行的既有空格按不修改配置的明确约束保留；代码 diff check 通过。
产品服务按用户要求保持运行，便于人工演示；不执行 shutdown。

Backlog：locale、template alias、>12 分类、连接复用、性能、资源 UX、部署、Round 2/FIX4。
不为未知模型新增 override，不修改 Frozen authority，不进行 relationship inference。
