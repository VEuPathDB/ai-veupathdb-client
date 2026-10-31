---
type: Decision
title: A request on a strategy waits in the host's strategy line
description: Every request the client sends on one strategy (a read, a PATCH, a DELETE, a PUT of its step tree, a copy of its tree) passes a gate the host installs, keyed by site and strategy id, around each attempt and inside the search gates. The default gate adds nothing. A lock in the client, a lock around whole StrategyAPI methods, and a version check were rejected.
tags: [wdk, http, strategy]
generated: { by: claude-code/opus-5.5, at: 2026-10-31T00:00:00Z }
verified: { by: claude-code/opus-5.5, at: 2026-10-31T00:00:00Z }
status: stable
---

# What was decided

WDK saves a strategy on every read, `PATCH` and `DELETE`
([WDK-STRAT-008](../wdk/rules/strategies-and-steps.md)), so a request that overlaps a
`PUT .../step-tree` on the same strategy can restore the tree the PUT replaced.

`HTTPClient._request_attempt` matches the path against `/users/{user}/strategies/{id}` and
anything below it, and holds `strategy_gate()(StrategyRequest(site_id, strategy_id))` for
the attempt. `use_strategy_gate` installs the host's gate; the default,
`open_strategy_gate`, adds nothing. The gate is entered inside the turn line and the search
gate, so every request takes the locks in one order. A list of strategies and a new
strategy name no one strategy and pass no gate.

Each request holds the gate alone. WDK's load and save happen inside one request, so a
request that holds the line cannot straddle another request's write. `update_strategy`
sends its PUT, its PATCH and its read as three requests, each in the line.

# What was rejected

- **A lock in the client.** One process cannot order another; the host owns its database,
  as with the search gate
  ([the search gate decision](a-search-waits-in-line-and-the-host-owns-the-gate.md)).
- **A lock around whole `StrategyAPI` methods.** A request sent through the client without
  `StrategyAPI`, such as a copy of a tree inside a tool server, would pass unlined.
- **A version check.** WDK has none to compare against; the strategy row holds no version.
