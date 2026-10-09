---
type: Decision
title: A search waits in line, and the host owns the gate
description: Every request that runs a search passes a gate the host installs, inside a per-turn line and outside the per-site slots; the client names the High Speed SNP searches, learns the searches of the steps it creates and reads, and starts a caller's budget at the send. A refusal at the limit, a gate in the client that reaches a database, and a per-process line for expensive searches were rejected.
tags: [wdk, load, http, searches]
generated: { by: claude-code/opus-5, at: 2026-10-09T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-10-09T00:00:00Z }
status: stable
---

# What was decided

**Three lines, nested.** A request that runs a search (`runs_a_search`) takes, in order:
the line of its turn on its site, the host's gate, then one of the site's
`veupathdb_concurrent_searches_per_site` slots. Each one waits first come first served
(`asyncio.Lock` and `asyncio.Semaphore` wake their waiters in order), and none refuses. A
request cancelled while it waits leaves the line, and the HTTP timeout starts when the
request is sent, so time in line never counts against it.

**The turn is a context the host sets.** `search_turn()` sets a `SearchTurn` on a context
variable for the block. A task inherits the variable by reference, so every
`asyncio.gather` of the turn shares one lock per site, and two searches of one turn on one
site run one after the other. Two turns hold two `SearchTurn` objects and do not wait for
each other. A request outside a turn takes no turn line.

**The gate is the host's.** `use_search_gate` installs a factory of async context managers,
called with a `SearchRequest`: the client's `site_id`, the kind (`report`, `step`,
`strategy`, `analysis`) and every search the request runs. The default gate adds nothing.
A host whose processes share a site installs one line across all of them.

**The client names what it can.** `HIGH_SPEED_SNP_SEARCHES` is the list WDK-HTTP-006 derives
from ApiCommonModel, and `runs_an_expensive_search` reads a request against it. A search
report names its search in the path. A step's search is learned from the request that
created it and from every read of it, and a strategy's tree and its steps' searches from
the request that created or replaced it and from every read of it, so a request on a
step or a strategy names every search of its tree once this client has built or read it.
The first read of a step another process built names nothing: that read is itself the
request that runs the search.

**A budget starts at the send.** `post(..., budget_seconds=...)` and
`run_search_report(..., budget_seconds=...)` bound a request from the moment it is sent,
inside every line, so time in line never counts against a caller's budget.

**Waits are reported.** `Observer.on_wdk_search_wait` receives each wait with the site and
the line (`turn`, `site`); the host's gate reports its own.

# What was rejected

- **A refusal at the limit.** A researcher would see an error for load that another turn
  caused; a wait costs only time.
- **A gate in the client that reaches a database.** The client knows no database, and a
  deployment with one process needs none. The line that spans processes belongs to the
  host that runs them.
- **A per-process line for expensive searches.** A deployment runs several processes
  against one site, so a per-process line bounds each process and not the site.
- **A gate on the search name alone.** A step report and a strategy read run every search
  of the tree, and their paths name no search; without the learned names, the first run
  of a SNP step would pass the gate unnamed.
