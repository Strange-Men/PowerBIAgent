# M6.5.2_FIX4 — Semantic Model Understanding / Grounding Core Refactor

状态：本地实现与专项验证进行中；Settings.version 保持 M6.5.2。发布仍只按本轮自身
exact-SHA Full Validation、Remote Audit、HEAD=origin/main、clean 成立。

## 1. Phase A — 代码审计根因

### RC-1 Understanding 过度约束且存在第二概率 veto

- `backend/app/intent/semantic_interpreter.py` 每次 DATA/REPORT 解释追加一次
  `UNDERSTANDING_COVERAGE` LLM 调用；任意 `MISSING_SEMANTIC_SPAN` 使整轮失败。
- `evidence_spans` 要求每个 mention 有同 slot 逐字副本；relation continuity 还能再触发
  一次 review。
- FIX3 Real 已出现 `semantic_coverage_incomplete`；真实失败不是语义错误，而是
  frame 漏标/措辞不一致。

### RC-2 无 Candidate Retrieval，全 Catalog 直接进 selector

- `ObjectGrounder.select_bounded` 将该 role 的全部候选发给 LLM；
  `len(candidates) > 128` 或 evidence > 64KB 直接 `bounded_llm_candidate_budget_exceeded`。
- `SemanticCatalog.selection_candidates` 对 dimension/filter 返回全部可见字段。
  200+ 字段模型在 DAX 前必然失败，且没有 lexical/语义缩小层。

### RC-3 Grounding 逐 slot 概率判定 + temporal authority 未消费 provider 声明

- `ground_frame` 对每个 measure/dimension 分别 `select_bounded`；member 可再触发
  `select_member` + category repair + equivalence veto；trend 还有 `_runtime_month_grouping`
  selector。
- 一条 ranking + member + time + follow-up 最坏 9–12 次 LLM 语义判定。
- Fabric IQ `ActiveRelationships` PK/FK 已保存在 `provider_evidence`，但
  `_resolve_date_field` 只消费 `context.relationships`（Fabric IQ 为 `[]`）。并且
  `catalog.context is not None` 的早退使唯一 runtime date field 永远不可达。

### RC-4 Fabric IQ formatted numeric

- `_typed_cell` 对 numeric schema string 只接受纯 ASCII 小数；`$12,345.67` 触发
  `CONTRACT_DRIFT`。这是真实陌生模型 blocker，不是宽容度问题。

### 不动的部分

DAX Builder、DAXSafety、ResultInspection、VerifiedFactSet、Answer/Report authority、
八 QueryShape、12-row/N+1/8-column、ValueSearch exact-existence 合同。没有证据表明
这些层需要重构。

## 2. 目标架构（已实施）

```
Natural Language
  → Lean SemanticFrame (language only)
  → deterministic structural/evidence/time/ranking checks
  → SemanticCandidateRetriever (existing Catalog objects only)
  → ONE BoundedSemanticResolver call for all unresolved object slots
  → deterministic binding / member ValueSearch / temporal proof
  → StateTransition → CanonicalQueryPlan → Deterministic DAX → Facts
```

### 2.1 Lean SemanticFrame

- 新 prompt 约 6.2KB（原约 12KB+），删除 coverage veto prompt、relation review 和
  大量 case exception。
- `measure_search_terms` / `dimension_search_terms`：最多 3/mention、12 total 的
  普通语言翻译/同义词，仅用于 retrieval，不是 ID/绑定。
- `evidence_spans` 保留为可选兼容字段；生产不再要求、不再据此 veto。
- 新增确定性校验：
  - 每个 mention/time expression/filter member 必须是 current message 的 verbatim substring；
  - 具体时间语言必须进入 time_mentions/time_intent；
  - ranking operator 必须来自 current message；top_n/direction 由 deterministic cue 校正；
  - 词法 coverage：去除 slot literals、framing 词后，残留业务 literal 触发一次 bounded repair；
  - relation continuity 由 deterministic invariant 归一化；显式 reset cue 永远保持 fresh。

### 2.2 SemanticCandidateRetriever

`backend/app/query_plan/candidate_retrieval.py`，provider-neutral、只读：

- measure ≤12、dimension/filter ≤12、date ≤8、temporal grouping ≤8；
- 使用 canonical/display/description/aliases/table/format/expression 的 lexical、
  token、bigram 评分；
- 永远只返回当前 Catalog 的 existing objects；没有 candidate 时返回 deterministic
  bounded slice，绝不因 catalog 大小直接失败；
- 无 embedding、无第二 semantic authority。

### 2.3 ONE BoundedSemanticResolution

`backend/app/query_plan/semantic_resolution.py`：

- 一次 LLM 调用处理所有仍未确定的 measure/dimension/filter-field slots；
- 只允许返回 slot 候选集合内的 exact candidate_id；
- DeepSeek prompt 短、角色单一、严格 JSON、允许 abstain、禁止 DAX/facts/plan/ID 创建；
- Runtime 独立复核 candidate 在 catalog、在 slot 候选集、类型/role 正确；
- AMBIGUOUS/UNRESOLVED → clarification，不再用第二次 LLM 投票。

### 2.4 Grounding 绑定

- exact canonical/alias/mention/relationship evidence 优先，不调用 LLM；
- 同 name dimension owner 先经 active many-to-one relationship / measure-table path
  确定性证明；
- description/display conflict 直接 AMBIGUOUS，不允许 selector 覆盖；
- fieldless member 的 exact/normalized runtime proof 先于 LLM，且 proof 结果复用，
  不重复 member lookup；
- member value 继续走 ValueSearch/exact proof + bounded label selection + reject-only veto；
- trend month axis 改为 deterministic `_prove_month_axis`: 对 bounded date fields 的
  complete member values 证明唯一 month-start axis；无 LLM grain authority。

### 2.4.1 Deterministic shape / coverage safety

- Shape invariants are code-owned and applied after relation continuity:
  - one ungrouped aggregate → `SCALAR`;
  - an aggregate restricted to named members → `FILTERED_AGGREGATION`;
  - one named member is not `MEMBER_SET`;
  - a fresh period total with no trend wording is not `BOUNDED_TREND`;
  - a follow-up/time correction with referenced dimension/shape keeps the
    inherited trend shape.
- Lexical coverage removes framing, reset and negated correction phrases
  (`不是X`, `not X`, `instead of X`) before flagging an omitted business term.
- Optional `evidence_spans` are not a second veto; every authoritative mention is
  still checked as a verbatim current-message substring.
- A bare generic ASCII measure noun (single token, no spaces) that no candidate
  metadata supports cannot be bound merely because the resolver preferred one
  of several candidates; it becomes `AMBIGUOUS` and clarifies.
- Multi-measure candidate preservation: ordinary ASCII metric wording is matched
  by whole-token subset against canonical/display/alias names (`quantity` →
  `Total Quantity`, `on-hand units` → `On Hand Units`); multiple containing
  measures remain ambiguous.
- Fieldless member proof now searches all categorical string fields in
  dimension tables reachable from the grounded measure table (not only the
  relationship key endpoint), bounded to 12 fields, with complete exact
  membership verification.
- A grouped frame whose only "dimension" is a proper-named value introduced by
  a filter preposition (`for Data Science`) is normalized to member/filter
  evidence and `FILTERED_AGGREGATION`; a real `by <Category>` dimension is not.

### 2.5 Temporal authority

`_resolve_date_field` 顺序：

1. explicit current date field mention;
2. active relationship temporal candidate;
3. model-scoped default temporal role;
4. unique temporal-grouping date binding;
5. provider-declared PK/relationship date endpoint（新）；
6. unique runtime date field（新可达）；
7. multiple → AMBIGUOUS/clarification。

Provider PK/FK 只证明 endpoint，不推断 cardinality/filter direction；多个 date
endpoint 仍 ambiguous。

### 2.6 Fabric IQ numeric normalization

- 仅在 runtime schema 已证明 output column 为 numeric（Decimal/Double/Float/Currency，
  fresh schema）时进入；
- 支持明确 currency symbols（$ € £ ¥ ￥ ₩ ₹ ₽）与严格 US/EU grouping/decimal 形式；
- format string 明确时按其 separator 解析；无 format 时仅在 US/EU 解析一致时接受；
- 直接 Decimal，无 float；拒绝 exponent、percent、括号负数、malformed grouping、
  歧义 locale、任意文本；fail closed 保持。

## 3. 复杂度结果

- Understanding prompt：13,738 chars → 6,727 chars（约 −51%）；另删除 1,356 chars
  的 coverage prompt。
- Understanding：per DATA/REPORT turn 1 次 LLM（原 2 次 + repair/review）。
- Grounding：通常 0 次（确定性 exact/mention/relationship）或 1 次 batch resolution；
  不再按 slot 逐个 LLM。
- Member value：仅 exact/normalized miss 时走 bounded label selection + veto。
- 典型 ranking/member/time：2–4 次 semantic LLM（原 6–12）。
- Production net diff：7 files、约 +1.7k LOC（含 deterministic retrieval/resolution、
  temporal proof、numeric parser）；Grounding 文件本身变长，但新增职责是显式的
  确定性证明与单一 batch resolution，不新增第二 Grounding/Planner/Memory，也不保留
  新旧 production 双路径。Legacy `SemanticGroundingService.ground` 仍为
  historical/test-only，不在 production call graph；`ground_frame` 已不调用任何
  per-slot selector。

## 4. Diff / scope

Production：`semantic_interpreter.py`、`grounding.py`、`fabric_iq_normalization.py`、
`deepseek_turn_service.py`（audit 一行）、新增 `language_cues.py`、
`candidate_retrieval.py`、`semantic_resolution.py`。未改 Settings.version、前端版本、
QueryShape、DAX/Facts authority。

Tests：interpreter/grounding/chat/model context/numeric boundary 更新；新增
`test_candidate_retrieval.py`、`test_natural_language_semantic_stress.py`、
`backend/tests/stress/natural_language_semantic_stress.py` 与 operator-run
`backend/tests/stress/real_llm_semantic_stress.py`。

## 5. 验证

- Focused：interpreter / grounding / chat / model context / numeric / stress harness。
- Semantic Compatibility Gate：822 PASS。
- Architecture / Repository Safety / Error Ledger / Documentation / Artifact / Golden：
  PASS。
- Affected regression（interpreter/grounding/chat/model context/numeric/report/
  stress harness/API shape）：838 PASS（short-basetemp Windows run）。
- Full Backend final candidate：4054 PASS / 1 SKIP / 22 existing warnings
  （short-basetemp owned run，8m24s）。
- Stress Harness：3 profiles × 16–18 natural cases，48–54 case；oracle 仅测试侧；
  生产不 import。
- Real LLM semantic stress：operator-run 脚本使用真实 DeepSeek + synthetic semantic
  metadata，不读取业务数据；首轮 48 case 为 29 PASS/1 CLARIFICATION/18 FAIL，修正
  filtered shape、optional evidence span、clarification evaluation、follow-up 与
  deterministic shape invariants 后，v4 为 37 PASS/9 CLARIFICATION/2 FAIL；剩余
  token-set multi-measure 与 proper-named filter normalization 通用修复后，最终
  v5 为 39 PASS/9 CLARIFICATION/0 unexpected FAIL，failure clusters 为空。9 个
  clarification 分别是每个 model 的 ambiguity、member no-match、unknown term。
  receipt 在仓库外 `PBIAgentTest/M6.5.2FIX4/Real/llm-stress-48-v5-final.json`。
- Real Cloud stress：需要交互式 Microsoft 登录；本轮不伪造。若未完成，明确记录为
  deployment/validation blocker，而不是 PASS。

## 6. 已知限制

- relationship cardinality 仍为 CONTRACT_GAP；provider endpoint 只用于唯一 date role。
- Candidate cap 12：极不透明的跨语言短语可能 clarification；这是 fail-closed，不是
  wrong binding。
- 无 embedding/vector DB；retrieval 是 lexical + optional LLM search terms。
- Legacy `ground` 仍为测试兼容路径；未来独立清理，不在本轮生产链。
- 12-row/N+1/8-column、Fabric IQ completeness、RLS/OLS 合同未改变。
