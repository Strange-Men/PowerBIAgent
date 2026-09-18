# M5.10.6 — LLM 语义理解与自然事实表达重构

## Status and baseline

- Status: LOCAL RELEASE CANDIDATE; fresh local automated and Local Real passed; Remote exact-SHA CI/final audit pending.
- Baseline: clean `main@9dfbf2f72bad299e41a138e9072a11caf8c678a7`.
- M5.10.5 exact-SHA CI: GitHub Actions Run `35088162355` success.
- Product version at start: `M5.10.5`; update to `M5.10.6` only after production changes.
- Semantic Layer FINAL ACCEPTANCE follows this milestone; `M5 FINAL=false`.

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

## Final local evidence

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
- Configured DeepSeek + Real Local MCP on final production code: 24/24 passed;
  automation residual=0.
- Drift audit: eight QueryShapes unchanged; no second Planner/Grounding/Memory/
  Intent authority, Agent, migration, MCP runtime/Provider/persistence rewrite or
  M5.10.7/8 work. Report consumes the shared availability context.
- Remote exact-SHA CI and final remote audit remain pending until commit/push.

---

*Updated: 2026-09-18 | M5.10.6 LOCAL RELEASE CANDIDATE | Remote exact-SHA CI PENDING | M5.10.7/8 NOT STARTED | Semantic Layer FINAL ACCEPTANCE PENDING | M5 FINAL=false*
