# M5.10.5 — 时间语义与事实呈现一致性收口

## Status and baseline

- Status: COMPLETE — FIX commit
  `9dfbf2f72bad299e41a138e9072a11caf8c678a7`; exact-SHA GitHub Actions Run
  `35088162355` completed/success.
- Original baseline: clean `main@3cca00b8cc37007411ef60015c419ff6e34530f1`.
- FIX baseline: `main@3d6a00693c0371603f6c3087acea73d09b8e6acd`.
- Product version at start: `M5.10.4`.
- M5.10.3 and M5.10.4: COMPLETE; Semantic Layer FINAL ACCEPTANCE remains pending.
- `M5.10.6 ACTIVE`; `M5 FINAL=false`.

## Single goal

Close deterministic time interpretation and factual presentation truth without
changing the existing semantic, execution, runtime, provider, persistence, or
report-rendering authorities.

## Capability restriction matrix

| Level | Request class | Allowed path |
|---|---|---|
| 0 | Greeting / social conversation | Existing selected LLM in an isolated no-tool lane; ZERO schema/member/DAX/report/business Memory |
| 1 | Current date/time | Application clock in the configured timezone; ZERO DAX |
| 2 | Product-adjacent concepts/help | Bounded explanatory response; never claims current model facts |
| 3 | Power BI business facts | Existing Router → bounded draft → runtime Grounding → CanonicalPlan → deterministic DAX → VerifiedFactSet |
| 4 | Report generation | Existing VerifiedFactSet → ReportData/ReportSpec → registered fixed renderer |
| 5 | Write/destructive/unsupported | Existing bounded refusal before business execution |

Low factual risk permits a natural LLM answer using only the current user
message. Business and report facts remain progressively stricter and may never
inherit authority from a conversational response.

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

## Post-release FIX audit

- P1-A confirmed RED: creative/social requests were either canned or routed as
  unsupported. The existing Router now sends only bounded low-risk
  conversational classes to one new `LLMTask.CONVERSATION` on the selected
  existing provider. The request contains only the system boundary and current
  user message; provider/profile/retry/usage/trace contracts are reused and no
  business context or tool is available.
- P1-B confirmed RED: model/source-field digits and coverage row indexes could
  enter one global numeric allowlist. Numeric validation now admits business
  values only from user-visible verified fact types. Exact deterministic
  scope/coverage fragments are validated separately; model identity,
  source-field identity, source rows, fact/result IDs, hashes and other
  provenance never authorize a business numeric claim.
- Additional P1 sweep findings were closed failure-first: system/help/weather
  prefixes can no longer swallow a later business request; greeting/courtesy
  discourse is ignored only by the residue detector while unknown business
  nouns still block; a slot-only pending completion cannot let a weak LLM
  draft rewrite the runtime-validated pending QueryShape.
- Original 19 production files: `FIX` = `application/deepseek_turn_service.py`,
  `application/turn_pipeline.py`, `facts/verified.py`,
  `intent/question_router.py`, `query_plan/completeness.py`; `KEEP` = the other
  14; `ROLLBACK` = none; `DEFER` = none. The isolated answer service, task enum
  and Mock parity wiring are supporting changes outside that original 19-file
  set.
- Fresh local automated evidence after the FIX: focused `770 passed`;
  M5.9.4 formal entry `29 passed` and fixed-seed 51,200/51,200;
  Semantic Compatibility `870 passed / 125 production files`; full backend
  `2903 passed, 1 skipped`; Golden `11 passed, 1 manual-real skipped`;
  frontend `91 passed` plus typecheck/lint/build; Architecture 142, Repository
  Safety 409, AI Error Ledger 104, Documentation/Artifact Governance,
  compileall, version consistency 49 and diff-check PASS.
- Local Real is separate evidence: configured DeepSeek + Real Local MCP on
  `PowerBIAgent_M3_Rich_Test` completed 19/19 with 19 execution witnesses,
  business residual=0 and temporary residual=0. It covered actual
  conversational calls, deterministic date/time, business escalation,
  business↔social isolation, vague-time pending completion, coverage and the
  2025 fixed report scope.
- Remote exact-SHA CI evidence: FIX SHA
  `9dfbf2f72bad299e41a138e9072a11caf8c678a7`; GitHub Actions Run
  `35088162355` completed/success. Local automated and Local Real counts above
  remain separate evidence and are not relabeled as remote results.

## Manual test conclusion and handoff

The user confirmed the factual-safety core is effective. Manual testing also
proved that the normal answer still exposes technical scope, general/capability
responses are not sufficiently natural, requested range is not clearly
distinguished from the observable business-data horizon, and a model whose 2026
sales facts end in March can be misread as a full-year statement. These are not
retroactive M5.10.5 failures; they are the failure-first baseline for M5.10.6.

---

*Created: 2026-09-16 | Updated: 2026-09-17 | M5.10.5 COMPLETE | 9dfbf2f / CI 35088162355 success | M5.10.6 ACTIVE | Semantic Layer FINAL ACCEPTANCE PENDING | M5 FINAL=false*
