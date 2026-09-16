# M5.10.5 — 时间语义与事实呈现一致性收口

## Status and baseline

- Status: IMPLEMENTATION COMPLETE — READY FOR SEMANTIC LAYER FINAL USER ACCEPTANCE.
- Baseline: clean `main@3cca00b8cc37007411ef60015c419ff6e34530f1`.
- Product version at start: `M5.10.4`.
- M5.10.3 and M5.10.4: COMPLETE; Semantic Layer FINAL ACCEPTANCE remains pending.
- `M5.10.6 NOT STARTED`; `M5 FINAL=false`.

## Single goal

Close deterministic time interpretation and factual presentation truth without
changing the existing semantic, execution, runtime, provider, persistence, or
report-rendering authorities.

## Capability restriction matrix

| Level | Request class | Allowed path |
|---|---|---|
| 0 | Greeting / social conversation | Direct natural response; ZERO schema/member/DAX/business Memory |
| 1 | Current date/time | Application clock in the configured timezone; ZERO DAX |
| 2 | Product-adjacent concepts/help | Bounded explanatory response; never claims current model facts |
| 3 | Power BI business facts | Existing Router → bounded draft → runtime Grounding → CanonicalPlan → deterministic DAX → VerifiedFactSet |
| 4 | Report generation | Existing VerifiedFactSet → ReportData/ReportSpec → registered fixed renderer |
| 5 | Write/destructive/unsupported | Existing bounded refusal before business execution |

Low factual risk permits a natural direct answer. Business and report facts
remain progressively stricter and may never inherit authority from a direct
conversation response.

## Failure-first scope

1. Prove greeting, thanks, current date/time and bounded concept explanations
   currently take the wrong route or lack a deterministic clock contract.
2. Prove exact/relative/recent/vague time behavior, including
   `最近几个月 → 最近6个月`, correction, and English equivalents.
3. Prove requested canonical scope is distinct from observed result coverage;
   cover full, partial, empty, unknown and unknown refresh time.
4. Prove query scope contains selected model, measure, grouping, filters, time
   and ranking only from the executed CanonicalQueryPlan.
5. Reuse the existing report reading-context path and prove requested scope,
   VerifiedFactSet evidence and observed coverage remain coherent.

## Frozen boundaries

- No new QueryShape, Planner, Grounding, Memory, Agent, migration, MCP worker,
  retry/timeout policy, Provider architecture, renderer, or visual redesign.
- LLM may interpret language, but cannot create dates, runtime identities,
  members, canonical values, DAX, QueryResult, coverage, refresh time or facts.
- Existing M5.10.3/4 zero-wrong-question and pending/committed precedence remain.
- M5.10.6 compatibility/error UX and M5.10.7 final closure are excluded.

## Evidence order

Spec → failing production-path regressions → minimal implementation → focused
time/capability/scope/report gates → cross-domain and semantic sweep → full
backend/frontend/governance gates → configured DeepSeek + Real Local MCP →
whitelist commit/push → exact-SHA CI and remote audit.

## Implementation and evidence

- Existing `QuestionRouter` now applies the capability restriction matrix before
  schema/member/DAX/business Memory. Current date/time uses the configured IANA
  application timezone (`Asia/Shanghai` by default). The bounded concept route
  accepts only complete concept phrases and cannot swallow business-fact wording.
- Existing temporal grounding now closes exact/relative/quarter/recent-N-month
  expressions and compatible time-only follow-ups. Vague ranges remain a
  structured pending clarification, and an LLM-supplied count cannot make them
  executable.
- Requested scope is projected only from the executed CanonicalQueryPlan.
  Observed coverage is an immutable QueryResult/VerifiedFactSet-derived fact
  with FULL/PARTIAL/EMPTY/UNKNOWN/NOT_APPLICABLE states. Empty rows are never
  presented as numeric zero.
- Explicit current report time is applied to every fixed subquery and Reading
  Context. Report-wide coverage is conservative across all fact sets; a single
  trend query cannot promote unknown siblings to FULL.
- Failure-first regressions cover capability short-circuiting, configured
  clocks, absolute/relative/quarter/recent/vague time, pending completion,
  current report scope, full/partial/empty/unknown coverage and LLM-invented
  vague-month counts.
- Fresh local automated evidence: focused `594 passed`; M5.9.4 formal entry
  `29 passed` and 51,200/51,200 generated cases; Semantic Compatibility
  `833 passed / 124 production files`; backend `2864 passed, 1 skipped`;
  Golden `11 passed, 1 manual-real skipped`; frontend `91 passed` plus
  typecheck/lint/build; Architecture 141, Repository Safety 408, AI Error
  Ledger 99, Documentation/Artifact Governance, compileall, version and diff
  gates PASS.
- Configured DeepSeek + Real Local MCP: 12/12, 16 real execution witnesses,
  provider failures=0, business residual=0 and temporary residual=0. Report
  coverage remained conservative UNKNOWN where sibling query coverage could
  not be proved.
- QueryShape remains eight values. No second Planner/Grounding/Memory/Agent,
  migration, MCP runtime, Provider architecture, renderer visual redesign or
  M5.10.6 implementation was added.

---

*Created: 2026-09-16 | Updated: 2026-09-16 | M5.10.5 IMPLEMENTATION COMPLETE | READY FOR SEMANTIC LAYER FINAL USER ACCEPTANCE | M5.10.6 NOT STARTED | M5 FINAL=false*
