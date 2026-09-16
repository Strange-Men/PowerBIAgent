# M5.10.3 — 人工验收后语义安全收口

## Status and baseline

- Status: IMPLEMENTATION READY; DeepSeek Real E2E BLOCKED and user manual acceptance PENDING.
- Product version at G0 start: `M5.10.2`; release-candidate version: `M5.10.3`.
- Repository baseline: `main@82ba346fde7cf71ba1d3bfeb4038f660500ff8be` and `origin/main` at the same SHA.
- Start condition: clean worktree; no merge/rebase/cherry-pick/revert state.
- Completion ceiling: `M5.10.3 IMPLEMENTATION READY FOR USER MANUAL ACCEPTANCE`.
- `M5 FINAL=false`; M5.10.4+ NOT STARTED.

M5.10.2 implementation/report visual completion and its exact-SHA evidence remain historical facts. Post-M5.10.2 manual business acceptance later found semantic/state safety defects, so those earlier PASS results cannot prove this milestone complete.

## Goal

The only goal is **Zero Wrong-Question Execution**:

> If the user explicitly asks for A, the system may answer A, ask a minimal clarification, return no-match, or fail closed. It must never silently execute B merely because B is a valid query with real Power BI data.

This milestone does not require every paraphrase to be answered directly. Safe clarification is preferable to semantic guessing.

## Manual defect evidence

### P0-A — Silent QueryShape / semantic obligation downgrade

Reported phrases include `哪三个产品最挣钱` and `销售额最高的三个产品`. A richer ranking draft may be overwritten by a `SCALAR` Router result, after which Grounding and completeness validate the downgraded question rather than the user's ranking obligation. The production path must prove the exact behavior before implementation changes.

### P0-B — Historical filter contamination

After a prior `Region = South` query, `哪个区域卖得最好？` may inherit the old same-field filter and rank Region only inside South. The result can be numerically real but answer a different question.

### P0-C — Correction / pending semantic state leakage

The sequence `不是销售额，是销售数量` followed by `也不是华南，是华北` may use stale committed slots, lose a pending ranking/grouping context, retain the old measure/member, or enter an unrelated clarification. Current explicit correction must update the compatible pending delta before older committed Memory is considered.

## Scope

1. Prove each P0 through the actual TurnService production path with deterministic fixtures/spies.
2. Preserve user-visible semantic obligations across Router, weak QueryPlan draft, Grounding, Coverage, StateTransition and Canonical Shape gates.
3. Add a pre-DAX Shape Obligation Firewall: an explicit ranking/grouping/filter/time/member-set/correction obligation missing from the final CanonicalQueryPlan makes the turn non-executable.
4. Add field-role transition safety for historical FILTER → current same-field grouping/ranking.
5. Make current correction apply to compatible PendingClarificationContext before committed Memory, without creating a second memory authority.
6. Add permanent manual-regression, metamorphic and cross-domain coverage.

## Non-scope / cold handling

The following are deferred and must be recorded without implementation:

- M5.10.4: mixed Chinese-English, broad paraphrase and complete QueryShape language optimization;
- M5.10.5: “最近几个月” UX, query scope and observed-data-coverage presentation;
- M5.10.6: template × model compatibility and generic frontend error UX;
- M5.10.7: final Real E2E/stress/mutation/historical/exact-SHA closure;
- Settings UX, full-width UI, same-name PBIX, Remote MCP, Entra, PostgreSQL, Deployment, new metrics or templates.

Unrelated existing test failures are reproduced and classified, not repaired through unrelated production changes. Infrastructure failures never justify weaker semantic contracts, fallback, retries, timeouts, expected-value changes or Real→Mock fallback.

## Authority boundary

The single production chain remains:

```text
QuestionRouter
→ runtime schema / ModelSemanticContext
→ SemanticCatalog / Grounding
→ Semantic Obligation Coverage
→ StateTransition
→ CanonicalQueryPlan / Shape Completeness
→ deterministic DAX / Layer 3
→ QueryResult / Result Inspection
→ VerifiedFactSet
→ Answer / fixed Report renderer
→ Memory / Snapshot
```

M5.9.2 worker/admission/queue/cancellation/retry/singleflight architecture is frozen. M5.8.5 factual authority and report factual authority are frozen. Frozen means the authority/architecture contract does not change; it does not mean implementation is bug-free. Minimal fixes that restore accepted invariants are allowed inside the existing chain.

Forbidden: a second Planner/Grounding/Memory, new QueryShape enum, TurnPipeline rewrite, LangGraph, multi-agent, RAG/ontology, new database/migration without unavoidable evidence, dependencies/MCP upgrades, Provider/retry/timeout changes, report visual changes, arbitrary DAX or business-specific phrase/answer hardcode.

## Failure-first checkpoints

### G0 — Repository governance

1. Verify branch/SHA/origin/status/Settings/Git operation state.
2. Correct active truth documents and retain historical evidence unchanged.
3. Create this plan before production/test implementation.
4. Run Documentation Governance, Repository Safety and `git diff --check` plus any applicable governance checks.

### P0-A reproducer

For each case record input, previous state, Router shape, weak QueryPlan shape, Grounding input/output, obligations, CanonicalQueryPlan, DAX count and Memory commit count. The baseline must demonstrate the wrong behavior before a fix is written.

Expected invariant: current explicit ranking/grouping evidence cannot be replaced by a weaker Router result. If the two signals cannot be reconciled safely, clarification occurs before DAX.

### P0-B reproducer

Build a sequence with prior same-field filter followed by current grouping/ranking of that field. Record transition mode, current/inherited/replaced/cleared slots and final scope.

Expected invariant: a historical filter on field F is removed when current explicit semantics promote F to grouping/ranking and the old member is not re-expressed. A current explicit `F=member` remains. Unrelated compatible filters remain.

### P0-C reproducer

Build a production-path chain containing measure, filter and ranking/grouping context, followed by:

```text
不是销售额，是销售数量
也不是华南，是华北
```

At every turn assert committed state, pending state, current delta, inherited/replaced/cleared slots, terminal state, DAX count and Memory commit count.

Expected priority: current explicit expression > compatible pending delta > compatible committed Memory. A failed/clarification turn never mutates committed factual Memory. Unresolved corrections remain non-executable.

## Shape Obligation Firewall

The firewall must compare current-turn explicit/structured obligations with the final canonical plan immediately before deterministic DAX. At minimum it covers:

- ranking: measure + dimension + direction/sort + N;
- grouping: requested dimension;
- filter/member: field + complete runtime-validated value set;
- bounded time: start + end + grain;
- trend: temporal grouping;
- correction: explicitly replaced or cleared slot outcome.

The firewall audits only structured evidence already produced by the existing Router/Grounding/normalization chain. It does not invent object identity, members, dates or facts, and it cannot make an unresolved plan executable.

## Permanent manual regression corpus

The following exact phrases live only in tests/harness/fixtures, never as production semantic authority:

```text
哪三个产品最挣钱
销售额最高的三个产品
各产品销售额是多少？
销售额按区域排一下
最近几个月的运单趋势
Top 5 客户按 Sales
Product 按销售额排前三
top 3 products by sales
华南 region 的 sales
不是销售额，是销售数量
也不是华南，是华北
```

Each case descriptor records previous committed context, pending context, current expression, expected shape or allowed clarification, expected current/inherited/replaced/cleared slots, terminal state, DAX yes/no and Memory commit yes/no. Assertions prioritize GroundedSemanticDelta, CanonicalQueryPlan and execution boundaries over answer strings.

## Metamorphic and generalization matrix

Use the existing M5.9.4 harness and bounded variants only: synonym, word order, Chinese/Arabic number, punctuation, current turn/follow-up, KEEP/REPLACE/CLEAR, ranking→ranking, filter→same-field ranking/grouping and clarification→correction.

Run the same invariant across Sales/Retail, Education, Inventory/Operations, Logistics and an unknown holdout. No production field/member/answer hardcode is allowed. Existing unknown and known+unknown member behavior remains clarification/no-match with ZERO business DAX, QueryResult and Memory commit.

## Focused and permanent gates

Run repository-real file names discovered during implementation, including:

- QuestionRouter;
- Grounding and Semantic Obligation Coverage;
- Canonical Shape Completeness;
- StateTransition / TurnRelation / PendingClarification;
- multi-turn production API;
- relevant M5.9.3 semantic matrix and M5.9.4 stress/metamorphic subset;
- cross-language and unknown-member fail-closed regression.

Then run Semantic Compatibility, backend full pytest, Golden, Architecture Gate, Repository Safety, AI Error Ledger, Documentation Governance, Artifact Governance, compileall, `git diff --check`, and frontend tests/typecheck/lint/build when the API contract may be affected.

## Real acceptance

After deterministic/full gates, use the existing Real acceptance path to prove:

1. ranking paraphrase no longer executes scalar;
2. stale same-field filter does not contaminate grouping/ranking;
3. correction chain does not fall back to stale committed state;
4. unknown member remains fail closed;
5. normal known queries do not regress;
6. conversation/model isolation remains intact.

Real evidence must record safe canonical/audit metadata and exact DAX/Memory counts, not secrets, raw Provider payloads or committed business rows. If Power BI/Desktop/DeepSeek/Local MCP is unavailable, report `Real acceptance BLOCKED`; do not weaken code or replace Real with fixtures.

## Residual cleanup

Only automation-owned resources created in this milestone may be deleted. Every Real/browser/integration run must register ownership, clean through formal API/repository paths in `finally`, and verify conversation/report/HTML/SQLite namespace/delete-intent/session/worker residual=0. Unknown ownership is preserved.

## User manual acceptance

Codex cannot mark this milestone FINAL PASS. After implementation, automatic gates and Real acceptance, deliver a minimal user checklist containing the original P0 phrases and the filter/correction sequences. The only permitted handoff status is:

`M5.10.3 IMPLEMENTATION READY FOR USER MANUAL ACCEPTANCE`

No commit, push, merge, rebase, tag or branch deletion is authorized by this milestone task.

## Implementation evidence — 2026-09-15

- G0 Documentation/Repository/Error-Ledger/Artifact Governance and diff-check passed before implementation.
- Baseline production-path reproducers proved all three P0s, including the original wrong scalar DAX + Memory commit for `哪三个产品最挣钱`.
- Minimal changes are limited to `deepseek_turn_service.py`, `completeness.py`, `grounding.py`, `state_transition.py` and `turn_relation.py`; no authority, runtime worker, Provider, report, schema or migration change.
- Permanent corpus contains all 11 manual phrases and structured previous/pending/current/inherited/replaced/cleared/terminal/DAX/Memory expectations. Focused M5.10.3: 26 PASS. Existing M5.9.4 51,200-case stress and Sales/Retail, Education, Inventory/Operations, Logistics and unknown holdout gates pass.
- Fresh full gates: backend `2758 passed, 1 skipped`; Semantic Compatibility `775 passed / 123 production files`; Golden `11 passed / 1 manual-real skipped`; frontend `91 passed` plus typecheck/lint/build; Architecture 140, Repository Safety 403, Error Ledger 90, Documentation/Artifact Governance, compileall and diff-check PASS.
- Scoped production Chat acceptance used `_env_file=None` and an acceptance-only deterministic language provider. Rich and Logistics schemas/members/DAX/result inspection/VerifiedFactSet remained Real Local MCP. Eleven cases and nine real DAX executions passed; P0-A and unknown-member were ZERO DAX/ZERO factual Memory mutation; business/temp/session/worker residual=0.
- The current process exposes no configured DeepSeek key and `.env` was neither read nor modified. Therefore DeepSeek-backed Real E2E is `BLOCKED`, not PASS. User manual acceptance is still required; M5.10.3 is not FINAL PASS.

---

*Created: 2026-09-15 | Updated: 2026-09-16 | M5.10.3 — 人工验收后语义安全收口 implementation ready；DeepSeek Real BLOCKED / 用户最终人工验收 PENDING | M5.10.4+ NOT STARTED | M5 FINAL=false*
