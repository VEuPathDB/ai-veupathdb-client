---
type: Decision
title: A rule is proven in this checkout, or it says so
description: Every rule status names a test this repository runs. A status naming another repository's test was rejected, because a rename there detaches a rule from its evidence with every gate green.
tags: [rules, gates, knowledge-bundle]
generated: { by: claude-code/opus-5, at: 2026-09-11T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-11T00:00:00Z }
status: stable
---

# What was decided

No rule status names a test outside this repository. The 36 rules that did now name a
test here: 29 hermetic cases under `tests/unit/rules/`, two live cases the nightly lane
already ran, and five that are `PARTIAL` - four hermetic and one live - where the named
case holds the half that can be held and the other half is a deployment's behaviour. A
rule whose claim is a deployment's own publication names a live case, because a
hand-written body proves only that the parse carries it.

`check-wdk-rules.mjs` resolves every named path, so a rename inside this checkout fails
the gate. The run reports `78 rules: 73 enforced, 5 partial, 0 unenforced`.

The hermetic cases read the recorded bodies under `veupathdb.testing.fixtures`, so a
rule about a wire shape is proven against what the sites actually sent, with no network.

# The alternative that was rejected

Keep the cross-repository statuses and teach the checker to resolve a sibling checkout.
The checker already refuses to do that on purpose, because the sibling is not present in
CI, and the cost was already paid once: WDK-VALID-011 named
`veupathdb-mcp/tests/unit/wdk/enrichment/test_analysis_defaults.py`, that file moved, and
both repositories stayed green. A gate that passes when the evidence is gone is not a gate.

Moving the 36 rules to the consumer's mapping tree was also rejected for all but none of
them: each one anchors a symbol in `src/veupathdb`, so the claim is about this package's
own behaviour and the rule belongs where the symbol is.
