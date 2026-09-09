---
type: Decision
title: The prefix that tags a helper strategy belongs to the deployment
description: A helper strategy's reserved name prefix is a VEuPathDBSettings field with a neutral default, not a constant naming one product, because the name is written into a real VEuPathDB account.
tags: [wdk, strategies, settings, api-surface]
generated: { by: claude-code/opus-5, at: 2026-09-09T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-09T00:00:00Z }
status: stable
---

# What was decided

WDK carries no metadata on a strategy, so a strategy created for a step count or a
control test is recognised later by a reserved prefix on its name. That prefix is
`VEuPathDBSettings.veupathdb_internal_strategy_name_prefix`, default `__internal__:`
(environment variable `VEUPATHDB_INTERNAL_STRATEGY_NAME_PREFIX`), read by
`is_internal_wdk_strategy_name`, `tag_internal_wdk_strategy_name` and
`strip_internal_wdk_strategy_name`.

The default names no product. A deployment that wants its own states it, and one
value both writes and matches, so a run always recognises its own strategies.

# Why it is not a constant

The name reaches the user's real VEuPathDB account. A shared client that writes one
application's name into every deployment's account is wrong on its face, and a second
deployment reading the same account would then claim the first one's strategies as
its own.

# Why there is no dual-prefix compatibility read, and what the deployment owes

A reader that accepted two prefixes would carry a second value forever to serve one
upgrade. The client keeps one value, which both writes and matches, and the
obligation moves to the deployment.

A deployment that has already written internal strategies MUST set
`VEUPATHDB_INTERNAL_STRATEGY_NAME_PREFIX` to the prefix it has always written, in
the same change that takes this release. A deployment that takes the release without
setting it writes and matches `__internal__:` from that moment, and every helper
strategy already in a researcher's VEuPathDB account under the old value is
permanently unmatched: no run recognises it, and no run removes it.

# What holds it

`tests/unit/wdk/test_internal_strategy_names.py`: the default carries no product
name, a stated prefix tags and strips, a process that states no prefix tags with the
default, and a name under a different prefix is not recognised as internal.
