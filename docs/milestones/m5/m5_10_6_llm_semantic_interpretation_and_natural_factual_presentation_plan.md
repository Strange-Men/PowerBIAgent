# M5.10.6 — LLM 语义理解与自然事实表达重构

## Status and baseline

- Status: LOCAL RELEASE CANDIDATE. All reopened semantic residuals and the
  independent Real multi-stage request SLA mismatch are locally closed. Final
  Stress is 130/130, Critical Real is 21/21 and all local gates pass; commit/push,
  exact-SHA CI and remote audit remain.
- Current baseline: `main@6b9abd890d58bed5768687733d2c1172532850ec`;
  exact-SHA CI Run `35496889792` completed/success for the prior published FIX.
- Original implementation baseline: `main@9dfbf2f72bad299e41a138e9072a11caf8c678a7`.
- M5.10.5 exact-SHA CI: GitHub Actions Run `35088162355` success.
- Current product version: `M5.10.6`; keep it unchanged throughout this redesign.
- Semantic Layer FINAL ACCEPTANCE follows this milestone; `M5 FINAL=false`.

## Multi-turn semantic continuity closure — 2026-09-24

- Failure evidence: the complete same-topic ranking turn intermittently produced
  `fresh_question` with empty changed/context slots after one continuity review,
  dropping the committed 2025-05 scope. Focused fixtures had supplied stable Frames
  and therefore did not expose the Real structured-output variance.
- Root cause: relation fields were originally optional, the bounded committed input
  omitted the previous user request, and the one-review implementation accepted the
  second probabilistic `fresh_question` without a deterministic consistency check.
- Fix: relation/changed/context slots are schema-required. The bounded committed input
  includes the latest committed user request, and the existing Understanding boundary
  checks verbatim topic continuity plus declared slot transformation. A repeated
  inconsistent fresh Frame is normalized to `follow_up` with derived changed slots and
  only compatible omitted context slots. Explicit reset evidence and unrelated topic
  negatives remain fresh; no downstream state repair or parallel classifier was added.
- The existing bounded measure selector performs one correction review only when an
  explicit current-turn measure replacement was first classified AMBIGUOUS. Candidate
  scope is unchanged and truly generic activity wording remains ambiguous.
- Evidence: focused continuity/fresh/context/selector/presentation regression `28
  passed`; configured DeepSeek + Real Local MCP exact 5-turn chain completed `3/3`
  consecutive independent runs. Every Turn 3 retained 2025-05 and every Turn 5 bound
  `Total Quantity` while preserving Region=South and Top3 desc.

## Targeted manual-acceptance integration closure — 2026-09-23

- Pending clarification seeds committed canonical state only for slots explicitly
  named in `referenced_context_slots`; corresponding `changed_slots` values are
  cleared before current grounding wins. Unknown replacement members retain proven
  measure/field context but remain MEMBER_NO_MATCH with ZERO execution/commit.
- `ABSOLUTE_MONTH(month, year=null)` is a valid language draft. Grounding resolves it
  only from a compatible committed date-field year; otherwise it asks for the year.
  EXPLAIN_CHANGE keeps the existing non-causal factual boundary.
- Pre-fix selected-template Real diagnosis stopped before ReportPlan with
  `validation_failed / SemanticInterpretationError`, 2 LLM calls and ZERO MCP/report
  calls. The pure REPORT output frame was incorrectly required to invent a DATA query
  shape or unresolved business term. The validator now admits only an otherwise empty
  REPORT frame; DATA structure validation remains unchanged.
- Post-fix configured DeepSeek + Real Local MCP completed the selected executive
  report service path with 9 real query executions and a non-null
  `sales_executive_report` artifact.
- Frontend template selection persists through ordinary turns and failures and is
  consumed only by a completed report. Chinese presentation uses model-scoped verified
  member aliases for summary/table/chart display while canonical values remain intact.
- Focused evidence: backend `52 passed`; frontend targeted `13 passed`; frontend
  typecheck and targeted Python compilation passed. Commit/push and user manual
  acceptance remain; M5.10.7/8 are not started and `M5 FINAL=false`.

## Final acceptance reopening — 2026-09-20

The published FIX remains valid historical evidence, including its local automated
gates, configured DeepSeek + Real Local MCP 21/21 and exact-SHA CI success. It does
not close four newly observed user-acceptance residuals:

1. literal runtime member `South` may fail while localized labels “南方/华南” pass;
2. an English wrapper around the same Chinese business request may change field or
   member binding and produce a filter-field ambiguity;
3. canonical technical names such as `Total Sales` and `South` may leak into the
   normal user answer instead of verified user-facing labels;
4. the default-open General lane may present nearby businesses, current operating
   status, weather, prices or news as facts without a corresponding current-data
   authority.

The next evidence cycle is therefore failure-first again. Before any production
change, preserve these residuals in a Final Acceptance Residual Corpus. Then build a
Real Language Stress Corpus with at least 72 unique scenarios and 120 actual
configured-DeepSeek + Real-Local-MCP executions. At least 24 high-risk scenarios run
three times; any semantic contract mismatch is a stability failure, never hidden by
majority vote. Expected outcomes come from runtime schema, members and deterministic
canonical invariants, not from another LLM judge.

The stress set covers general, external-current-fact boundary, scalar,
member/filter, grouped, ranking, all eight QueryShapes, time/horizon,
ambiguous/unknown, follow-up/state, explain-change/report, cross-language,
cross-domain and cross-model isolation. It may contain domain examples only in
test/manual-smoke fixtures; none may become production phrase, PBIX or member
hardcode. Each root cause gets at most two forward-fix rounds. After the second
failed round the status is OPEN P0/P1, not prompt-tuning continuation.

## Real Language Stress historical failure result — 2026-09-20

- Corpus construction: exactly 72 unique scenarios with the required category
  split and 24 high-risk scenarios; deterministic runtime/canonical assertions,
  no LLM self-judging and no production import of stress phrases.
- First real baseline: 72 unique scenarios; 82 actual chat turns including state
  setup; 194 configured DeepSeek calls; 143 real Local MCP/tool executions. This
  was a failure-discovery run, not the required final 120+ execution pass.
- Two minimal forward-fix rounds closed focused member/object/time/state/general
  boundary/presentation residuals. Related unit regression is `212 passed`.
- Remaining P1: `为什么今年销售额下降？` fails with
  `semantic_evidence_not_verbatim` in two consecutive post-round-2 focused Real
  runs. Other explain-change paraphrases passing does not satisfy stability.
- Stop consequence: no third prompt adjustment; the final 72/120+ stress, 24×3
  stability gate, Critical Real Acceptance, full automated/drift sweep,
  whitelist commit/push, new exact-SHA CI and remote audit were not run.

## Final local closure — 2026-09-23

- END-TO-END trace classified the repeated 504 as legitimate bounded multi-stage
  cumulative latency, not a hung provider call, retry, MCP/tool bottleneck,
  duplicate or loop. A Critical Real turn completed in 130.525 seconds while its
  slowest single provider call remained 113.085 seconds.
- The overall request SLA therefore moved minimally from 120 to 180 seconds.
  Per-call LLM/provider, MCP and render timeouts remain 120 seconds; DAX remains
  30 seconds. Remaining-deadline propagation and timeout cleanup are unchanged.
  One later provider long-tail failure was classified as transient and was not
  used to justify 240 seconds.
- Final configured DeepSeek + Real Local MCP Stress passed 130/130 across 72
  unique and 24 high-risk×3 scenarios: 584 LLM calls, 395 MCP/tool executions,
  138 witnesses, request p50/p95/max 11.087/53.160/87.251 seconds, max single LLM
  83.397 seconds, and zero timeout, wrong semantic/fact, Memory, leakage,
  stability or residual counts.
- Critical Real passed 21/21 with 20 execution witnesses, zero override and zero
  business/temporary residual. General cases each used exactly one LLM call;
  ambiguous and unknown cases remained ZERO DAX/Memory.
- Fresh local gates passed: Semantic Compatibility 807/122 production files,
  backend 2804 passed/1 skipped, frontend 91 plus typecheck/lint/build, Golden 11
  plus one manual-real skip, Architecture 139, Repository Safety 412, Error
  Ledger 113, Documentation/Artifact Governance, compileall, version consistency
  and diff-check. Structural audit kept eight QueryShapes and all forbidden
  architecture boundaries unchanged.

## Manual acceptance reopening — 2026-09-18

Manual acceptance found overlapping natural-language authorities despite the
published automated and Real evidence. `LLMSemanticInterpreter` is a facade over
conversation, full QueryPlan generation and report-intent services; Router shape
regex, QueryShape reconciliation, Completeness residue NLP, TurnRelation regex,
object/member selectors and report intent still interpret language in parallel.
M5.10.6 is therefore reopened. M5.10.7 and M5.10.8 remain NOT STARTED.

The new acceptance failure corpus must first reproduce these classes on the
published baseline: general-location language misrouting; 南方/华南 runtime-bounded
member linking; unknown member ZERO DAX/ZERO factual Memory; ambiguous “销售”
clarification; clear scalar classification; ranking pending → measure change →
general turn → measure follow-up continuity; non-causal “为什么下降” analysis; and
natural presentation without canonical IDs. Production must not change until the
corpus is stably RED.

Baseline evidence: `backend/tests/unit/test_m5_10_6_understanding_failure_corpus.py`
ran twice on unchanged production and produced `12 failed` both times. The
failures independently witness A routing, B hardcoded/domain-specific member
logic, C unsafe existing-candidate selection, D/E/G missing SemanticFrame
contract, F slot-only follow-up loss and H canonical member leakage.

The corpus is now a permanent regression suite. The FIX cutover uses one
`SemanticFrame` language contract; legacy Intent/QueryPlan/conversation/
TurnRelation semantic authorities and shape reconciliation fallback are removed.

## Goal

Converge open-language understanding into one bounded semantic interpretation
contract, reduce QuestionRouter to deterministic risk/capability preflight, and
present verified business facts naturally while retaining the existing runtime,
canonical, execution and factual authority chain.

```text
User Message
→ deterministic risk/capability preflight
→ LLM Semantic Interpreter
→ general conversation OR bounded business/report semantic draft
→ runtime SemanticCatalog → Grounding → Completeness → CanonicalQueryPlan
→ deterministic DAX → QueryResult → Result Inspection → VerifiedFactSet
→ Natural Answer Composer → FactOutputValidator → User
```

## Authority contract

- LLM owns language interpretation and wording only. `SemanticInterpretationDraft`
  may propose mode, one of the eight existing QueryShapes, runtime-owned object
  candidates, raw member/filter phrases, time/ranking/comparison intention,
  evidence spans and ambiguities.
- Runtime SemanticCatalog/Grounding owns canonical object/member binding;
  StateTransition/Completeness owns executable canonical state; deterministic DAX
  and Layer 3 own execution; QueryResult inspection/VerifiedFactSet owns external
  business facts.
- General conversation is default-open, current-message-only and no-tool. A
  structured `requires_business_grounding` result escalates possible organization
  facts into the strict business path.
- Mixed social/business turns take the higher-risk business path.
- QueryShape remains the existing eight-value enum. No ninth shape or second planner.

## Natural factual presentation

- Separate `canonical_scope` from verified `user_facing_scope`; never expose opaque
  model keys, canonical field identity, fact/result IDs or mechanical scope prefix
  as the normal UI answer.
- Natural Answer Composer consumes only VerifiedFactSet, verified user-facing scope
  and Data Availability Context. LLM wording is validated after composition;
  invalid output is repaired within a bounded attempt or replaced by a deterministic
  safe fallback.
- Table/chart continue to use the existing verified presentation contract.

## Available data horizon

- Keep requested scope, observed coverage and available data horizon independent.
- Horizon is measure/fact-family + temporal-dimension aware and may only come from
  existing verified rows or a deterministic auxiliary query derived from the current
  CanonicalQueryPlan, using the verified measure and runtime-proven temporal field.
- The probe remains read-only, deterministic DAX, existing safety/inspection/fact
  validation, with LLM authority zero. Cache key, if needed, includes semantic model,
  measure, temporal dimension and schema fingerprint.
- Never infer horizon from application date, requested end, Date-table max, LLM,
  generated/query/snapshot time or refresh metadata. Without authoritative refresh
  metadata say “当前模型中可观测到的数据截至…”, never “数据更新到…”.

## Failure-first acceptance

RED reproducers must cover natural scalar/ranking answers, technical-scope leakage,
unseen general and business paraphrases, natural capability response, mixed-request
escalation, ambiguous/unknown semantics with ZERO DAX, nonexistent candidate/member
mutations, numeric/comparison/cause/availability hallucination, partial 2026 horizon,
no-row versus zero, general/business/pending/model state isolation, cross-domain
Retail/Education/Inventory/Logistics/unknown holdout, and report reuse of shared
availability context.

## Frozen scope

No new QueryShape, Planner, Grounding, Memory, Agent, LangGraph, RAG/vector DB,
ontology server, persistence DB/migration, MCP runtime/refactor, retry/timeout change,
Provider rewrite, LLM-generated DAX, arbitrary DAX, write/delete/update, Forecast,
Target, Budget, new YoY/MoM/business calculation, report visual redesign, template
compatibility, M5.10.7 or M5.10.8 work.

## Evidence order

G0 governance → G1 read-only authority audit → RED production-path reproducers →
minimal implementation → focused/cross-domain/full gates → configured DeepSeek +
Real Local MCP → whitelist staging → commit/push main → exact-SHA CI → remote audit.
Local automated, Local Real and Remote CI are reported separately.

## Historical evidence from the superseded implementation

- Focused: M5.10.6 15; Router/API 246; cross-language 168; numeric mutation
  39; pending/state/grounding 193; M5.10.4 43; M5.10.5 supplemental 276.
- M5.9.4 formal entry: 17 passed; fixed-seed generated cases 51,200/51,200.
- Semantic Compatibility: 878 passed; 128 production backend files scanned.
- Full backend: 2,928 passed, 1 manual-real skipped. Golden: 11 passed,
  1 manual-real skipped.
- Frontend: 91 passed; typecheck, lint and production build passed.
- Governance/static: Architecture 145, Repository Safety 414, Error Ledger 105,
  Documentation/Artifact Governance, compileall, version consistency 49 and
  diff-check passed.
- Configured DeepSeek + Real Local MCP on the superseded production code: 24/24 passed;
  automation residual=0.
- Drift audit: eight QueryShapes unchanged; no second Planner/Grounding/Memory/
  Intent authority, Agent, migration, MCP runtime/Provider/persistence rewrite or
  M5.10.7/8 work. Report consumes the shared availability context.
- The implementation was committed and pushed at `276d67d`; exact-SHA CI Run
  `35296985175` succeeded. The new manual acceptance failure means this evidence
  cannot close M5.10.6 and must be rerun after the single-chain redesign.

## FIX implementation and local evidence — 2026-09-20

- `SemanticFrame` is the sole open-language authority. Router is deterministic
  capability/safety preflight; SemanticCatalog/Grounding bind runtime object and
  member candidates; deterministic temporal resolution binds canonical time;
  StateTransition/Completeness merge and validate canonical executable state.
- Runtime-bounded member selection supports conventional localized category labels
  such as 华南/南方→South only after independent veto and exact member verification.
  Specific-instance inference such as 深圳→South and unknown 火星区 remain
  unresolved with ZERO DAX/factual Memory mutation.
- Complete runtime month-start member evidence can provide a request-scoped
  temporal grouping proof when imported PBIX metadata lacks a static month
  expression. No Catalog mutation or LLM canonical date authority is introduced.
- Production uses deterministic DAX only. QueryResult, Inspection,
  VerifiedFactSet, Natural Answer/FactOutputValidator and shared Report factual
  authority remain unchanged; EXPLAIN_CHANGE cannot invent causal evidence.
- Fresh local automated: backend `2764 passed, 1 skipped`; Semantic Compatibility
  `801 passed / 122 production files`; M5.9.4 formal `51,200/51,200`; Golden
  `11 passed, 1 manual-real skipped`; frontend `91 passed` plus typecheck, lint and
  production build; Architecture 139, Repository Safety 416, AI Error Ledger 109,
  Documentation/Artifact Governance, compileall, version consistency 49 and
  diff-check passed.
- Local Real, recorded separately: configured DeepSeek + Real Local MCP `21/21
  PASS`, 20 execution witnesses, zero override, wrong DAX=0, business residual=0
  and temporary residual=0.
- This FIX was whitelist committed/pushed as
  `6b9abd890d58bed5768687733d2c1172532850ec`; exact-SHA CI Run `35496889792`
  completed/success. That is historical evidence only; the current reopened
  closure still needs its own commit/push, exact-SHA CI and final remote audit.
  M5.10.7 and M5.10.8 remain NOT STARTED; `M5 FINAL=false`.

---

*Updated: 2026-09-23 | M5.10.6 LOCAL RELEASE CANDIDATE | Real Stress 130/130 and Critical Real 21/21 | all local gates PASS | new commit/CI pending | M5.10.7/8 NOT STARTED | M5 FINAL=false*
