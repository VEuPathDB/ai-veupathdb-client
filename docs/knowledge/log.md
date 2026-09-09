# Knowledge log

## 2026-09-08 - The small client moves arrive, and the app prose leaves

`GET /users/current` and its typed profile, the two EDA validation predicates, the
OpenTelemetry observer adapter, the WDK capture transport and the orphaned-step delete
moved in from the consuming application. `veupathdb_oauth_url` moved in from the MCP
server's settings, because the function that reads it is this client's.

Four sections that spoke about the consuming application left: the three EDA
"what this means" sections and the step-analysis usage note. What names a module in
another repository is now written as a citation - `pathfinder:` or `veupathdb-mcp:` -
and every path that still spelled the pre-split `integrations/veupathdb/` tree names
this package instead. WDK-AUTH-004 is enforced here now that `password_logout` has a
test in this suite.

## 2026-09-08 - ruff format owns the bundle's Python blocks

`ruff format` formats Python code blocks inside markdown from ruff 0.16, so
`uv run ruff format --check .` now covers every file in this bundle as well as
`src` and `tests`. A Python block here is formatted code, not free text.

## 2026-09-05 - The bundle arrives with the client

The WDK model, REST and rule bundles and the whole EDA bundle moved here from
PathFinder's `docs/knowledge/`, with every anchor and every named test repointed at
this tree. A rule whose enforcement lives in the consuming application is `UNENFORCED`
here, with a `reason` naming the consumer's test: 37 of the 78 rules are in that state,
and the count is the honest measure of what this repository's own suite holds.

PathFinder keeps the eight `WDK-MAP` rules, because a mapping rule is an invariant of
the application rather than a fact about WDK.
