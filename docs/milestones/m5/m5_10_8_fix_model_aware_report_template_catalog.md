# M5.10.8 FIX — 模型感知报表模板目录收口

## 范围与基线

2026-09-30；LOCAL AUTOMATED / REAL / BROWSER PASS，REMOTE exact-SHA CI 待提交推送后审计。
起始 clean main 与 origin/main 均为 `ef5a4c8ead7c05576360d3070ecf0e286e841dc5`；该基线
Run `36661689674` completed/success。本记录是本轮唯一文档变更。Settings.version 保持
M5.10.8，M5 FINAL=false；不实施 M5.10.9 / M6，不新增物流报表模板。

## Problem / Root cause

人工 UI smoke 发现物流模型仍展示两个不可用销售模板。HEAD 审计确认 `sales_report`
显示为“简易模板”，却绑定 SALES_REPORT_CONTRACT；专业模板绑定
SALES_EXECUTIVE_REPORT_CONTRACT，二者共用 SALES_QUERY_REQUIREMENTS。
原 CompatibilityService 对所有 registry descriptors 直接执行 schema capability validation，
缺少独立业务域筛选；前端因此展示大量灰项，通用名称进一步误导。

## Design / Implementation

- 新增 application-owned immutable SemanticModelProfile，保存 semantic_model_key 与
  frozenset domains，支持多域；复用 ModelSemanticContextBuilder 的身份、重复对象与
  hidden/system visibility 验证，不建立新的 Catalog/Grounding 或 capability engine。
- 当前最小 Sales 规则复用 SALES_QUERY_REQUIREMENTS 中 total_sales、total_orders、
  average_order_value 的 canonical measure identities（包括表归属）；任一可见 identity
  可证明 Sales scope，Total Quantity 单独不能证明 Sales。类型是否满足合同仍交给原 validator。
- Logistics 的最小确定性组合为可见 canonical Total Shipments measure + Carrier/Route
  fields。其他未被这些精确规则证明的 schema domains 为空，fail closed。模型 key/name、
  display name、description、conversation、用户问题与 LLM 均不参与分类。
- 两个现有 descriptor 明确 domains={sales}。simple 改名“简易销售分析模板”，description
  为“基于销售指标快速生成 KPI、趋势与分类分析”；template/renderer/contract key 不变。
  未声明 domains 的 descriptor 默认空集合，不能无意成为通用模板。
- CompatibilityService：schema → profile → domain intersection → 原
  ReportContractValidator / compute_section_capabilities。域不匹配不进入 response；域匹配后
  compatible/partial/incompatible/unavailable、section count 与 selectable 原样保留。
- Response 顶层 reason_code：合法空目录为 no_eligible_report_template；schema 读取、
  metadata 验证或 identity 失败为 semantic_model_schema_unavailable，均 items=[]。
  schema 失败时不能证明 eligibility，所以不展示未经证明的模板。
- Frontend 只投影 backend items。正常空目录文案为“当前数据模型暂无适配的报表模板，但仍可
  正常进行数据问答。”；schema failure 为独立重试提示；无有效模板则 selection=null。
  generation、model-key、effect cancel 与发送 guard 不变。
- 未来声明 logistics 域的 descriptor 自然进入同一候选集，但仍须注册正式 contract 才能可选，
  无需 frontend model-name 分支。本轮未实现 enterprise metadata / Entra / Cloud registry。

## Local automated — fresh

- Failure first：backend 4 failed / 4 passed，frontend 2 failed / 33 passed，生产修复前已证明
  非 Sales 仍返回灰项、缺 profile/response state、空文案错误。
- Final focused：147 passed，覆盖 Sales full/partial/domain-matched incapable、Logistics、
  unknown、hidden/system/quantity-only/wrong-owner negative、schema failure、未来 descriptor
  进入现有 contract validation，以及邻近 report contract/adaptive/generation/registry。
- API legacy mock fixture 的 TotalSales 不是当前注册 Total Sales canonical identity；其显示名
  不证明域，expected 明确更新为 fail-closed empty catalog。未引入模糊匹配或放宽合同。
- Frontend：105 passed；新增 normal empty state + Q&A enabled、schema failure 区分、Sales
  请求晚到 Logistics 后不能恢复销售模板/selection，并验证发送 Logistics 不携带 template key。
- Backend 正常 suite：2849 passed / 1 manual-real skipped / 2 deselected，exit 0。
  按用户要求仅排除 test_business_language_stress.py 的两个 51,200-case 节点；测试与 CI 配置
  均未修改。首次启动排除路径写错，进程已停止；最终 fresh run 确认两个节点实际 deselected。
- Semantic Compatibility：819 passed / 126 production files；frontend typecheck/lint/build PASS，
  lint 0 errors / 0 warnings；Golden 11 passed / 1 manual-real skipped。
- Repository Safety 422 files、Architecture 143 production files、AI Error Ledger 117 entries、
  Documentation Governance、Artifact Governance、compileall、diff-check PASS。
  最终 staging 后再执行 safety/governance/diff-check。
- 扩展性新测试曾误用 status 名称作为 reason code；按现有 validator 的 report_template_unknown
  修正该新测试 oracle，未修改 validator。一次 focused 命令引用不存在的复数文件名，没有执行
  tests；最终使用实际 report_contract.py 的 147 项 focused run 已全部通过。

## Local Real — DeepSeek + Local MCP

复用 cross_language_real_acceptance.py 的既有 ownership、witness 与 teardown；仅扩展 m5108
的 catalog case，独立端口运行，zero semantic override。仅两个 chat requests：

- Sales：真实 catalog 只返回 sales_report / sales_executive_report，两者 selectable；新 simple
  名称正确。选择 sales_executive_report 生成报表 completed，Layer 3 / factual validation PASS，
  9 组 actual DAX fingerprint → unique canonical plan → rebuilt VerifiedFactSet 配对通过。
  ReadingContext/DataSnapshot、非空 KPI/chart/table、无 script、HTTP view/download 字节与 hash
  全部核验通过，ZERO LLM DAX。
- Logistics：真实 catalog items=[] / no_eligible_report_template，无 Sales templates。
  随后 Total Shipments 数据问答 completed；真实结果、canonical identity、VerifiedFactSet、
  committed Memory 与 factual validation PASS。没有模板不影响数据问答。
- 两项 catalog + 两个 chat 的 4/4 assertions PASS，10 个 execution witnesses，business
  residual=0，temporary teardown residual=0。未运行大型 Real/stress/provider matrix。
- 实际业务数值、rows、DAX、完整回答或 provider prompt/response 仅在进程内核验，没有写入 Git。

## Browser UI — real catalog, no additional chat

使用 freshly built frontend 与独立临时 Real backend，通过 Codex 浏览器工具完成：
Sales 只显示两个销售模板 → 选择 simple → 切换 Logistics → 最终 selection 清空、无 Sales
灰项、指定空状态文案正确 → 输入物流问题后发送按钮可用（未发送额外请求）。console
warning/error=0。临时浏览器关闭、owned backend 停止，temporary residual=0。
截图保留在工作区外的可视化目录，不提交真实业务或页面输出。

## Architecture / Remote acceptance

Frontend 不拥有 eligibility；LLM 不拥有 domain authority；模型名字不拥有 domain authority。
未改 Understanding、Grounding、CanonicalQueryPlan、DAX/Safety、QueryResult、VerifiedFactSet、
ReportPlanner/Spec/Renderer、事实表达、Memory 或 ToolGateway；Sales Contract 未放宽；partial
与 stale-response 防护保留。仅目录服务、metadata、frontend、focused tests 与既有验收观察脚本变化。

提交名：`M5.10.8_FIX_模型感知报表模板目录收口`；不打 Tag。推送前再次 fetch，remote main 已
前进则停止。推送后依赖自动 exact-SHA CI，不预填 final SHA/Run、不追加文档回填 commit。
最终消息记录新 SHA、CI Run、各 steps 与 remote-main/worktree audit。只有所有本轮条件及 CI
均绿色才宣告 M5.10.8 FIX COMPLETE / READY FOR M5.10.9，然后停止；M5 FINAL=false。
