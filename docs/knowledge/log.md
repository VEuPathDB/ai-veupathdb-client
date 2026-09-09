# Knowledge log

## 2026-09-09 - The refusal base takes the host's code enum, and the strategy prefix leaves

`VEuPathDBError` is generic in its code enum, so a host application puts its own
error hierarchy under this base instead of maintaining a parallel one. The client's
own refusals name `VEuPathDBErrorCode`; a handler that takes any refusal names the
bound.

The reserved prefix that marks a helper strategy is now a settings field with a
neutral default. It named one product and was written into the user's real VEuPathDB
account. A deployment that already wrote helper strategies states its historical
prefix in the same change that takes this release, or those strategies stay in the
account unmatched.

`env_ignore_empty=True` is stated in the settings docstring and asserted in the
suite, because a blank environment variable resolving to the field default is the
behaviour that keeps a validator unnecessary.

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
