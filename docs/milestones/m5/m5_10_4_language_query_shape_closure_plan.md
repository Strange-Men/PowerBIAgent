# M5.10.4 — 语言理解与 QueryShape 收口

## Status and baseline

- Status: COMPLETE — local automated + configured DeepSeek + Real Local MCP acceptance passed; exact-SHA CI is the release evidence.
- Repository baseline: clean `main@0c8b0984c507d0a595e319d0a7c5dd7918863df0`.
- Product version at start: `M5.10.3`.
- M5.10.3: COMPLETE / 用户人工验收通过（由本轮用户明确确认）。
- Configured DeepSeek and Real Local MCP acceptance: PASS, 14/14 with residual=0.
- `M5.10.5 NOT STARTED`; `M5 FINAL=false`.

## Goal

Release the existing Intent / QueryPlan LLM draft to interpret open Chinese,
English and mixed-language expressions while keeping all execution authority in
the existing deterministic chain:

```text
QuestionRouter capability + high-confidence/fallback evidence
→ existing bounded LLM Intent / QueryPlan language draft
→ runtime SemanticCatalog / Grounding canonical identity
→ StateTransition canonical state
→ Completeness execution firewall
```

No second LLM call, Planner, Grounding, Memory or QueryShape is permitted.

## Failure-first evidence

The baseline audit found three bounded defects to prove through permanent tests
before production changes:

1. QueryPlan already exposes optional `query_shape`, but its production prompt
   neither lists the field nor defines its bounded language-only authority.
2. When Router returns inheritance fallback `None`, the application overwrites
   a richer current QueryPlan draft with `None`, allowing pending/committed or
   scalar fallback to replace the current language interpretation.
3. Grounding derives ranking bound/direction only from finite deterministic
   wording and discards the existing QueryPlan draft's current structural
   fields. Open paraphrases can retain `RANKING` yet still lose TopN/sort.
4. A vague recent-month expression is not a concrete time range, but its
   unresolved obligation is currently liable to surface as a filter/member
   residue instead of an incomplete-time clarification.

## Bounded reconciliation policy

- Router continues to own capability routing, safety floor and explicit
  deterministic structural evidence.
- `SCALAR` and inheritance `None` are weak fallbacks; they cannot erase a
  richer current LLM draft.
- A stronger deterministic shape keeps precedence unless the Router evidence
  is only generic grouping and a current, internally coherent richer ranking
  draft carries an explicit current bound.
- LLM structural suggestions remain non-canonical. Object IDs and members must
  be rebound to the current runtime Catalog and runtime member snapshot.
- A draft TopN is accepted only when the same bounded number is evidenced in
  the current input. A missing ranking bound remains clarification.
- Any unresolved or conflicting obligation remains ZERO DAX / ZERO factual
  Memory commit.

## Required coverage

- Chinese grouping/ranking/word-order/vague measure/correction.
- English grouping/ranking/trend.
- Mixed object/measure/member/ranking language.
- Bounded metamorphic variants for synonym, punctuation, word order,
  Chinese/Arabic/English number, current/follow-up and object language.
- Sales/Retail, Education, Inventory/Operations, Logistics and unknown holdout.
- M5.10.3 correction/pending/current priority and unknown-member invariants.

## Frozen boundaries

QueryShape enum, TurnPipeline architecture, semantic object/member authority,
StateTransition/Memory authority, deterministic DAX, VerifiedFactSet, M5.9.2
runtime, Provider architecture, report, persistence and frontend UX remain
unchanged. M5.10.5 time-range interpretation/presentation is not implemented.

## Gates

Failure reproducers → focused Router/Intent/QueryPlan/Grounding/Completeness/
multi-turn/cross-language → M5.9.4 stress/metamorphic entry → Semantic
Compatibility → full backend → Golden → frontend test/typecheck/lint/build →
Architecture/Repository Safety/Error Ledger/Documentation/Artifact Governance
→ compileall/diff-check → configured DeepSeek + Real Local MCP → whitelist
commit/push → exact-SHA CI → remote audit.

## Completion evidence

- Failure-first baseline: `11 failed, 2 passed` before the minimal implementation.
- Focused/current semantic: `307 passed`; adjacent semantic sweep: `703 passed`.
- M5.9.4 stress entry: `29 passed`, retaining 51,200 generated cases and Logistics coverage.
- Semantic Compatibility: `775 passed`, 123 production files.
- Full backend: `2798 passed, 1 skipped`.
- Golden: `11 passed, 1 manual-real skipped`; frontend: `91 passed` plus typecheck/lint/build.
- Architecture 140, Repository Safety 406, AI Error Ledger 95, Documentation/Artifact Governance, compileall, version consistency 47 and diff-check all passed.
- Configured DeepSeek + Real Local MCP: `14/14` across Rich and Logistics PBIX, with 10 real DAX/VerifiedFactSet witnesses; ambiguity, incomplete ranking, vague trend and unknown member all stopped safely; business/temp residual=0.
- QueryShape enum remains unchanged; no second Planner/Grounding/Memory, no runtime/Provider/report/frontend/persistence change, and no M5.10.5 implementation.
- Per the user's acceptance strategy, M5.10.4 does not wait for a separate manual round. Semantic Layer FINAL ACCEPTANCE remains scheduled after M5.10.5.

---

*Updated: 2026-09-16 | M5.10.4 COMPLETE | M5.10.5 NOT STARTED | Semantic Layer FINAL ACCEPTANCE 尚未进行 | M5 FINAL=false*
