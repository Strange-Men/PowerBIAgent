# M5.10.6 — LLM 语义理解与自然事实表达重构

## Status and baseline

- Status: FIX LOCAL RELEASE CANDIDATE. The superseded published implementation is
  historical evidence only; the single-chain Understanding Layer redesign, fresh
  local gates and final-production Real acceptance are complete. Exact-SHA release
  evidence remains pending.
- Current baseline: clean `main@276d67d783f5af75dd4e55ba20e910679d623be3`;
  exact-SHA CI Run `35296985175` completed/success.
- Original implementation baseline: `main@9dfbf2f72bad299e41a138e9072a11caf8c678a7`.
- M5.10.5 exact-SHA CI: GitHub Actions Run `35088162355` success.
- Current product version: `M5.10.6`; keep it unchanged throughout this redesign.
- Semantic Layer FINAL ACCEPTANCE follows this milestone; `M5 FINAL=false`.

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
- Whitelist commit/push, exact-SHA CI and final remote audit are PENDING. M5.10.7
  and M5.10.8 remain NOT STARTED; Semantic Layer FINAL USER ACCEPTANCE remains
  pending; `M5 FINAL=false`.

---

*Updated: 2026-09-20 | M5.10.6 FIX LOCAL RELEASE CANDIDATE / exact-SHA PENDING | M5.10.7/8 NOT STARTED | Semantic Layer FINAL ACCEPTANCE PENDING | M5 FINAL=false*
