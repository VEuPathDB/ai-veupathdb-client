# Knowledge log

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
