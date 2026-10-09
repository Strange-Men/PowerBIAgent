# M5.10.9 FIX — Document Semantic Consistency & M6 Handoff Closure

> 2026-09-30 documentation forward-fix；2026-10-09 CI stability continuation；M5.10.9 FIX FINAL REVALIDATION PENDING。
> M5 FINAL=true；M5 CORE ANALYSIS KERNEL FROZEN；LOCAL MVP BASELINE FROZEN。
> 本文件只记录本次 audit / 分层 evidence / closure；current state、路线、handoff 分别见 07/08/09。

## Cold Start / current reality

initial main、HEAD 与 fetch 后 origin/main 均为
`86aaaec7d2172c041e97392c3de03adcca77ca1b`；worktree clean，无 merge/rebase/cherry-pick。
Settings.version=M5.10.9；M5 FINAL=true。fresh GitHub REST 核验
[Run 36678384015](https://github.com/Strange-Men/PowerBIAgent/actions/runs/36678384015)
head_sha 匹配、completed/success；进入本次文档修复的基线成立。
按 AGENTS 与用户指定清单读取入口、PRD/01/06/07/08/09、index、frontend spec、Ledger、
ADR-006/014/019、M5.10.8 FIX / M5.10.9 evidence、Settings、RemoteMCP、治理脚本/邻近 tests、CI。
进一步核对 registry / compatibility service / DAX builder / QueryShape / frontend 实现与 tests。

## Semantic drift / correction

| 文件 | 原漂移 | 校正 |
|---|---|---|
| AGENTS | 状态指向 09，施工期 scope/两阶段命令仍为当前规则 | 07 状态/08 路线/09 handoff；获批 M6 patch prerequisite |
| CLAUDE | 上轮禁止 M6 与 candidate/seal 步骤 | 通用开发协议；具体 scope 授权与 fresh contract |
| Charter | 末尾上轮本轮不实现措辞 | 仅改阶段适用性：尚未实现、获批 scope 与 09 prerequisite；北极星不变 |
| PRD / 01 | EQ-only grammar、单模板与双模板混存，旧名称 | 八种 QueryShape；双 Sales registry；model-aware eligible catalog |
| 06 | 旧日期/版本/current FINAL=false 页脚 | 长期安全/Git规范，状态委托 07/08/09 |
| 07 / 08 / 09 | 已封板仍描述施工；09 裸 FINAL=false 指令 | 保持既有 Final；FIX 独立收口；NEXT=M6、NOT IMPLEMENTED 与前置顺序 |
| frontend spec | 重复 header、泛化灰项规则、旧模型/选择生命周期事实 | 两层 eligibility；域不匹配 not_returned；域匹配 capability_validation；现有 disabled UX |
| ADR index | 专业模板保持 unavailable | ReadingContext / immutable snapshot / shared SALES_QUERY_REQUIREMENTS；正文不改 |
| RemoteMCP | ADR-006 accepted docstring | legacy deferred / SUPERSEDED 适用性说明；行为保留 |

八种 shape 为 SCALAR、ENTITY_LIST、GROUPED、RANKING、MEMBER_SET、FILTERED_AGGREGATION、
TREND、BOUNDED_TREND。实际筛选为 EQ 与 runtime-validated IN_SET；趋势须证明时间维度/范围。
没有新增 YoY/MoM/Forecast/arbitrary comparison/causal/unrestricted DAX/filter operators。
Sales 域匹配模板保留 compatible/partial/incompatible/unavailable；后两者可见但禁用。
Logistics / Unknown 无适配域时返回 empty catalog，数据问答不受影响；schema failure 单独反馈。

## Governance / failure-first

新增测试先 RED：新 semantic helper 尚未实现时 21 failed / 8 passed。
helper 实现与 mutation 校准后，文档尚未修正的稳定 RED 为 1 failed / 28 passed；
gate 精确列出 8 项真实 current semantic drift。初版正则漏掉“唯一公开模板为”与“最终条件成立”，
由新增 negative tests 发现并补齐；未修改 expected 或降低 validator。
focused allowlist 覆盖 AGENTS/CLAUDE/09 施工指令、00/01 单模板、PRD 八 shape、ADR-019 摘要、
frontend 两个短 policy anchors；不要求全文一字不差，也不证明每句文档语义。
明确 Historical heading 的 section/child headings 排除；同级恢复 current 检查。
archive/milestone 不进入 semantic allowlist；旧 CHANGELOG 与 ADR-006 历史正文保留。
Error Ledger：ERR-5109-002（marker consistency ≠ semantic truth）；候选 exact-SHA CI success 后
以实际候选 commit 记录 resolved，M6 legacy prerequisite 仍保留。

## RemoteMCP legacy / M6 handoff

remote_mcp.py 仅校正模块 docstring；server_url default、constructor、methods、NotImplemented
消息（包括旧 ADR-006 wording）、provider selection、Settings、transport/auth 与 runtime contract 不改。
这些旧值不是 production contract；已在 09 + ERR-5109-002 正式列为 M6 first-step P0 prerequisite。
本次不验证 endpoint、不换地址、不实现 Cloud/Fabric IQ/Entra/存储或 M6 identity。

NEXT=M6：Cold Start → external Microsoft capability verification → auth/identity/RLS-OLS evidence
→ threat model → tenant/principal/resource identity → ownership/IDOR → token lifecycle → cache isolation
→ accepted implementation contract → 用户具体 patch scope 授权 → production implementation。
Token 只在 Auth/Transport；Frozen Core authority 保持，M6 优先通过 Adapter/Repository/Service 扩展。

## 2026-09-30 Local automated — historical PASS

- Documentation Governance：PASS；focused governance 29 passed。
- Governance + Settings/version + Error Ledger regressions：131 passed（29 + 49 + 53）；exit 0。
  首次 09 改英文标题触发旧 Settings test 的当前阶段 anchor 要求；保留该 anchor 后版本测试通过，未改旧测试。
- Normal backend required suite：2874 passed / 1 manual-real skipped / 2 authorized deselected；exit 0。
- Semantic Compatibility：819 passed / 126 production files；exit 0。
- Golden：11 passed / 1 manual-real skipped，0 errors。
- Repository Safety：427 files；Architecture：143 production Python files；Error Ledger：119 entries / 0 errors；Artifact Governance：PASS。
- RemoteMCP AST 除模块 docstring 外完全一致；Frozen Core/frontend/CI/history unchanged 静态验证 PASS。
- Frontend：10 test files / 105 tests passed；lint（0 errors / 0 warnings）、typecheck、production build PASS；exit 0。
- git diff --check PASS；staging 前重新执行 Repository Safety / Documentation Governance / cached diff 检查。

normal backend suite 仅按本次明确限制 deselect test_business_language_stress.py 中
test_generator_covers_51200_safe_reproducible_cases 与 test_stress_report_has_zero_generated_failures；
测试节点、CI full matrix 均不修改。

## Local Real / Browser — NOT RUN（用户 scope）

本次不修改业务 runtime。按用户明确指令，不执行 Real Data/Report E2E、DeepSeek/Kimi smoke、
大型 stress、51,200-case、130-turn、provider matrix、browser full acceptance 或 Desktop Real query。
远程 CI 仍执行仓库原有 required suite，不能把 Remote CI 视为 Local Real evidence。

## Historical Phase A / B closure evidence

M5 FINAL=true 从开始到结束保持。Phase A commit：
`M5.10.9_FIX_文档语义一致性与M6交接候选`；SHA
`9196bb7e52fbc8869daff7233518ac896bc813ca` /
[Run 36686978579](https://github.com/Strange-Men/PowerBIAgent/actions/runs/36686978579)
completed/success；required Full Validation (Windows)、commit check-run 与全部 steps success。
fetch 后 HEAD==origin/main、worktree clean。两次普通 fetch 曾遇到 GitHub 443 连接超时；
ls-remote 证实 remote 未前进，单次命令 HTTP/1.1 fetch origin main 恢复，未修改 Git 全局配置或代码。
Phase B 仅作小型 status/evidence marker patch：
`M5.10.9_FIX_文档语义一致性与M6交接收口`；再等待最终 exact-SHA CI / required check success。
最终 FIX COMPLETE marker 仅在最终 exact-SHA CI completed/success、required checks 全绿、
fetch 后 HEAD==origin/main 与 worktree clean、人工关键文档审计成立后有效。
自身 SHA 不写入自身提交；最终精确 SHA/Run 在交付中记录，09 提供可重现解析步骤。
完成本次 FIX 后停止；可进入下一轮独立 M6 Cold Start / Research / Planning，M6 implementation 尚未开始。

## 2026-10-09 — CI lifecycle test stability forward-fix

用户明确授权：“允许修改 backend/tests/api/test_health.py”，且仅限
`TestLifespanIntegration.test_no_global_state_cross_apps`；允许必要的 07/09、Ledger、
本 evidence 与 CHANGELOG closure evidence 修正。不再请求相同 scope；不修改 production code、
Settings.version、Frontend 或 M6。根因记录 ERR-5109-003，首次 minimal repair。

### Fresh baseline / failure-first

fresh main、HEAD 与 fetch 后 origin/main 均为 `953be2683d539fbf4b43d59cca086a3fd598928c`，
worktree clean。重新读取真实 [Run 36688714620](https://github.com/Strange-Men/PowerBIAgent/actions/runs/36688714620)
Job `109800545295` 日志：`test_no_global_state_cross_apps` 在 line 378 比较 id，
出现 `1248422350736 != 1248422350736`；full pytest 为 1 failed / 2876 passed。
Golden、Frontend、Typecheck、Lint、Build、strict diff 后续步骤未执行，不能算 PASS。
旧失败 run 永久保留，不 rerun 规避 nondeterministic oracle；953be268 的 FIX COMPLETE 未生效。
M5 FINAL=true 与原 Final baseline 持续有效。

`git show` / blob audit：原 Final `86aaaec7d2172c041e97392c3de03adcca77ca1b` 与
953be268 的 `backend/tests/api/test_health.py` 完全相同，blob 均为
`76fefe064e0002fd868a9a4b8cc5e07ca0a11fc0`。文档 FIX 没有引入该测试逻辑。
`main.py` 在 startup 创建 app-scoped MockTurnService，在 shutdown 清理 app.state 引用；
测试没有保存对象强引用，只保存整数 id，因此第一个对象释放后 CPython 可以复用地址。
相同 id 不能证明两个 app 共享 Service；当前证据为既有测试 oracle 错误，不是 production regression。

### Minimal implementation / local verification

仅获批单测改为保留 svc_a / svc_b 强引用，各自在 lifespan 内 assert 非 None，
用 `svc_a is not svc_b` 验证同时存活对象的隔离；分别验证 app_a / app_b lifespan 退出后
`mock_turn_service is None`。不比较整数 id，不加 GC/sleep/retry/timeout/随机化或 allocator 变更。
邻近既有 `test_two_apps_different_services` 采用同一对象 identity 原则。
2026-10-09 fresh Local automated：

- 单测 `test_no_global_state_cross_apps`：1 passed；test_health.py 整文件：23 passed。
- 单测有界重复：20 次独立 Python/pytest 进程，20/20 PASS；首个失败立即停止，无 retry-until-green。
- AST scope audit：仅该单测方法体改变，其他 tests/imports 完全一致；production / frontend / CI diff 为零。
- Documentation Governance / Version / Error Ledger regressions：131 passed（29 / 49 / 53）。
- Repository Safety：427 files PASS；Architecture：143 production files PASS；Error Ledger：120 entries / 0 errors；Artifact Governance PASS。
- Semantic Compatibility：819 passed / 126 production files；Golden：11 passed / 1 manual-real skipped / 0 errors。
- Normal backend required suite：2874 passed / 1 skipped / 2 authorized deselected，exit 0。
  仅 deselect 原有两个 51,200 节点，CI matrix 与测试定义不改。
- Frontend 首轮与 Python checks 并行，67 passed，但 3 个文件因 forks worker 启动 timeout 未运行；exit 1，保留为失败证据。
  Python checks 完成后独占资源重跑同一 `npm test`，10 files / 105 tests PASS，所有文件实际执行；不改配置、timeout 或 ignore。
  Lint / Typecheck / Build 全部 PASS，exit 0；Vite 的 PLUGIN_TIMINGS 提示保留，未降低任何 gate。

Local Real / smoke / 51,200 / 130-turn / large stress / browser full acceptance 不运行；Remote CI matrix 不改。

### Phase C / D closure contract

Phase C：`M5.10.9_FIX_CI生命周期测试稳定性修复`，current marker 为 FINAL REVALIDATION PENDING；
白名单 staging / push main，等待新 exact-SHA CI 及全部 required steps success。
Phase D 仅在 Phase C success 后做 tiny marker patch，记录 C SHA / Run / success，提交
`M5.10.9_FIX_CI稳定性修复与最终封板`；再次等待最终 marker SHA 自身的完整 CI success。
最终 fetch 后 HEAD==origin/main、worktree clean，required check / Golden / Frontend / Typecheck /
Lint / Build / strict diff 均实际 success 后，FIX COMPLETE 才生效并停止。M6 implementation 未开始。
