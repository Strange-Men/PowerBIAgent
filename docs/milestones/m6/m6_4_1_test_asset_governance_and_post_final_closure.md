# M6.4.1 — 测试资产治理与封板遗留收口

## 正式基线与 scope

M6.4 FINAL COMPLETE；main `bdbe7189be21ff043340c2025625a9e3398310b0`，中文提交
`M6.4_云端产品最终验收与正式封板`，Full Validation 38693083553 SUCCESS，Remote Audit PASS。
本轮起始 fresh fetch/main/HEAD=origin/main/clean 已验证；本轮 Final CI 独立于该基线 CI。

最新 Scope Recovery 取代此前 cache/connection/Favorites 实施方向。10 个 tracked 实验文件按
逐文件 reverse diff 恢复，其 Git blob 与稳定基线一致；6 个专属新文件移出仓库。
实验源码、日志与 synthetic DB 只在仓库外 M6.4.1/Research，NOT ADOPTED / OUT OF CURRENT SCOPE /
NO PRODUCTION CODE RETAINED，不是本轮 acceptance requirement。Frozen Core authority 与事实链无修改。

## Folder Governance

唯一仓库外根为 `PBIAGENT_TEST_ROOT`，本机配置为 `D:/AAA_Workfile/PBIAgentTest`。
正式仓库保留原位。Fixture、LateResponse、Acceptance、RealEvidence、Performance、Cache 按 milestone
存放；既有 M6.4_FIX 和 M6.4.1_PREP 历史结构保留，不混合版本证据。

旧五目录 fresh inventory 为 448 文件 / 44,252,661 bytes；已 Copy → Verify，逐文件 SHA zero diff。
10 个旧 DB 由 acceptance runner 新建 synthetic 路径证明，只允许 byte copy/hash，未打开、SELECT、
读行或迁移 schema。无法分类 DB 必须 UNCLASSIFIED_DB 并留原处。
活跃工具路径切换，历史 snapshot/PREP/失败记录只作历史引用；原件和新内容 hashes 分别保留。

治理回执位于仓库外 M6.4.1/Governance：inventory-before、copy-manifest、sha256-verification、
reference-migration、pre-delete-manifest、inventory-after、governance-final-receipt。
清理按 verified copy、引用迁移、无持锁和回归证据进行。此前两组删除被工具 policy 拒绝，
用户完成旧五目录及仓库五个误生成目录的人工删除；fresh 回执为 **MANUAL_DELETE_COMPLETE**。
旧目录=0、仓库临时目录=0、active old-path reference=0、SHA mismatch=0、UNCLASSIFIED_DB=0。

本地 runner 首次将反斜杠路径写入 PYTEST_ADDOPTS，参数解析去掉反斜杠，造成临时文件误入
仓库及报表假失败。原始失败、2,928个synthetic文件和SHA在Research/RunnerPathFailure保留。
修复使用正确引用的 Path.as_posix()、预建父目录与owned TemporaryDirectory；repo-owned
scripts/run_local_validation.py 要求显式外部 PBIAGENT_TEST_ROOT，结束/异常清理temp，保留
output/receipt。CI方式不变。三个canonical pyc已被测试重建，其原始字节在VerifiedSourceArchive
独立SHA验证，原件保全不等同于将修改后的runner/缓存冒充原hash。

## P2-A current-state

修复 Charter/AGENTS/README/CLAUDE/07/08/09 的封板前 current-state 文字。
历史开发/失败/PASS 记录保留在显式历史区域；不重新打开 M6.4 已关闭合同。

## P2-B conservative result envelope

状态：**CLOSED_AS_EXPLICIT_LIMIT**。

Fabric IQ Cloud business N=min(request.max_rows,12)，wire maxRows=N+1，columns ≤8。
最多104 wire cells、每 cell/name ASCII JSON ≤66 bytes、execution JSON ≤8192 bytes 的原合同保留。
sentinel、CSV、unknown、超界或不完整结果在正式 Facts 前 fail closed。
Local max_rows=1000、八 QueryShape、Int64、lineage、completeness、VerifiedFactSet 和 Report authority 不变。
复验既有 inline envelope/product completeness/shape tests；不增加容量、Provider 或新性能功能。

## P2-C OLS Real deny

状态：**DEFERRED_BY_TEST_PRINCIPAL**。

M6.4 Final 已记录 Test B 不可用的用户批准例外，Test A 的现有角色允许 RestrictedTable；
因此不能声称 Test A 提供 OLS deny。本轮未获得新可用 Test B，不创建账号、扩大权限或调用未知身份。
后续生产安全封板须用独立批准的受限 principal 取得 fresh Real OLS deny evidence；当前 synthetic
deny、RLS 和 owner isolation 不替代该责任。该状态不重新打开 M6.4 Final。

## 发布合同

Settings.version 在治理与 fresh gates 全部 PASS 前保持 M6.4。完成后升 M6.4.1，中文提交
`M6.4.1_测试资产治理与封板遗留收口` → 普通 push main → 自身 exact-SHA Full Validation SUCCESS →
Remote Audit → HEAD=origin/main 与 worktree/staging clean，才可 FINAL COMPLETE。
用户人工删除已fresh验证。结束后 STOP，不进入 M6.5。

## Fresh 验证与发布判定

本轮治理、README及fresh gates通过后Settings.version已升M6.4.1。全后端3521PASS/1SKIP、
15既有warnings；Semantic819PASS；Golden11PASS/1manualSKIP；前端160PASS；Typecheck/Lint/Build、
Security/Ledger/Architecture/Documentation/Git diff strict均PASS；runner/IQ补充负例16PASS。
README Markdown已解析、21相对链接存在，Mermaid官方parser识别flowchart-v2，无本机路径/Secret/历史Seal流水账。
长run目录触发Windows报表路径限制的focused失败保留，缩短run后53PASS；前端worker启动超时原记录保留，
fresh运行160PASS/无unhandled error，不修改测试expected或timeout。
本次Local/Cloud Real为NOT_RERUN_NO_PRODUCTION_CHANGE；M6.4既有Real分别保留，不能冒充本轮fresh Real。
仅Settings版本标记属于runtime diff；frontend配置仅允许本地验证输出重定向，CI默认布局不变。
本提交发布判定须核对main最终提交自身Full Validation SUCCESS、Remote Audit及clean；
提交无法嵌入自身SHA，exact-SHA与CI/Audit回执保存在外部Governance，不引用旧M6.4 CI完成本轮。

## README Information Architecture Governance

fresh参考 microsoft/semantic-kernel、microsoft/autogen、google-gemini/gemini-cli 和
 google/googletest 当前官方README：先定位与能力，再运行方式/启动，最后文档与贡献入口。
只学习信息架构，不复制文案；原README约29.8KB，本轮约11.8KB。移除exact-SHA/Run ID、
历史施工流水账、完整API/内部authority及大段配置排障。原稿在外部Governance保存。

信息落点：milestone历史→CHANGELOG/原专项；Final证据→07/09/专项；authority→Charter/ADR/AGENTS；
Auth/operator→09及M6.1/Cloud专项；API→OpenAPI/04；Persistence→ADR-012/02；测试治理→AGENTS。
原README独有的Conda路径排障、dotenv检查、namespace/cursor及Kimi配置提示移至09的简短运维入口，
不写本机绝对路径，不新增生产能力。
