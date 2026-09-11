---
type: Backlog
title: 36 of the 78 rules name a test this checkout cannot run, and one of those tests has already moved
description: Every UNENFORCED rule says "enforced in the consuming application" and names a path in another repository; the checker never resolves those paths, and WDK-VALID-011 already names a file that no longer exists.
tags: [rules, gates, coupling, knowledge-bundle]
status: draft
---

# 36 of the 78 rules name a test this checkout cannot run, and one of those tests has already moved

**What I did.** Ran `node scripts/check-wdk-rules.mjs` from the repository root
and read its coverage line and its `UNENFORCED` list. Then resolved each named
test path by hand against the checkout it names, `~/repos/pathfinder` for
`apps/api` and `apps/web`, `~/repos/ai-wdk-mcp` for `veupathdb-mcp`.

**What I got.** `78 rules: 42 enforced, 0 partial, 36 unenforced, 0 withdrawn, 0
anchored in a cited repository`. All 36 unenforced rules carry the same reason,
`enforced in the consuming application, at <path>`, and the paths split 19 to
`veupathdb-mcp/tests`, 14 to `apps/api` and 3 to `apps/web`. The 36, by file:

| File | Rule ids |
|---|---|
| `docs/knowledge/wdk/rules/auth-and-transport.md` | WDK-HTTP-002 |
| `docs/knowledge/wdk/rules/filters.md` | WDK-FILTER-001, WDK-FILTER-003 |
| `docs/knowledge/wdk/rules/parameters-and-vocabularies.md` | WDK-PARAM-007, WDK-PARAM-008, WDK-PARAM-011, WDK-VOCAB-001, WDK-VOCAB-003, WDK-VOCAB-004, WDK-VOCAB-005 |
| `docs/knowledge/wdk/rules/searches-and-answers.md` | WDK-ANS-001, WDK-ANS-002, WDK-ANS-003, WDK-ANS-005, WDK-ANS-007, WDK-SEARCH-001, WDK-SEARCH-002, WDK-SEARCH-003, WDK-SEARCH-004 |
| `docs/knowledge/wdk/rules/site-model-params.md` | WDK-SITE-001, WDK-SITE-002, WDK-SITE-004, WDK-SITE-007 |
| `docs/knowledge/wdk/rules/strategies-and-steps.md` | WDK-STEP-003, WDK-STEP-004, WDK-STEP-005, WDK-STEP-007, WDK-STRAT-002, WDK-STRAT-003, WDK-STRAT-004, WDK-STRAT-005 |
| `docs/knowledge/wdk/rules/validation.md` | WDK-VALID-006, WDK-VALID-007, WDK-VALID-008, WDK-VALID-010, WDK-VALID-011 |

The 36 reasons name 19 distinct files. 18 exist where the reason says; one
does not:
WDK-VALID-011 names `veupathdb-mcp/tests/unit/wdk/enrichment/test_analysis_defaults.py`,
and that file is gone. `TestAMissingFormStopsTheRun::test_the_analysis_is_not_run_without_its_parameters`
now lives at `veupathdb-mcp: tests/unit/wdk/enrichment/test_analysis_form.py:37,39`.
The run still reports zero violations, because
`check-wdk-rules.mjs` reads a status prefixed with a repository name as a
citation and does not resolve it
([the gate scripts are copies](../conventions/gate-scripts-are-copies.md)).

**Why that's wrong.** The bundle's premise is that a rule is admissible because
something can falsify it. For 36 rules nothing in this checkout can, and the
first proof of the cost is already measurable: a test rename in another
repository silently detached a rule from its evidence, and both repositories'
gates stayed green. A reader here cannot tell a rule proven elsewhere from a
rule proven nowhere, and every one of the 36 anchors a symbol this package owns,
so the claim is about this package's own behaviour.

**Why it happens.** The rules were written where the WDK knowledge lives and the
tests where the consumer code lives. `check-wdk-rules.mjs` treats a prefixed
status as an unresolvable citation by design, so a cross-repository status is
counted and printed but never checked.

**Fix.** In this repository, rule by rule, one of two outcomes and no third.
Either the rule states something this package can prove, and a test in
`tests/unit` proves it against the anchor the rule already names, so the status
becomes `ENFORCED by tests/unit/...` and the checker resolves it. Or the rule
states something only a host can break, in which case the rule is not this
bundle's and moves to the consumer's mapping tree, where its test already lives.
The 19 rules whose tests sit in `veupathdb-mcp` are the first batch: the shapes
they assert (report configs, search listings, parameter adapters, vocabularies)
are this package's models, so most of them are provable here from the recorded
fixtures without a network. WDK-VALID-011's stale path is fixed in the same
change that converts or moves it.

**What you'd get.** `check-wdk-rules.mjs` reports 78 rules with no unresolvable
status, a rename in another repository cannot detach a rule from its evidence,
and "UNENFORCED" in this bundle means unproven rather than proven out of sight.
