---
type: Backlog
title: The package declares no public surface, so a consumer reads the import graph of another repository
description: 7 of 93 modules carry __all__ and no test reads one; the two in-house consumers import 62 veupathdb modules, 53 of them named nowhere in README, and both import a private one.
tags: [public-surface, generality, gates]
status: draft
---

# The package declares no public surface, so a consumer reads the import graph of another repository

**What I did.** Listed every module that declares `__all__` in `src/veupathdb`,
opened the three package roots, collected every `from veupathdb.<module>` import
in the two in-house consumers (`pathfinder: apps/api/src/pathfinder` and
`veupathdb-mcp: src`), and compared that set with the modules README names.
Read the tool server's gate, `veupathdb-mcp: tests/unit/test_public_surface.py`
and `veupathdb-mcp: tests/unit/published_surface.json`.

**What I got.** 7 of 93 modules declare `__all__`: `wdk/factory.py`,
`wdk/strategy_api/__init__.py`, `wdk/strategy_api/helpers.py`,
`testing/fixture_store.py`, `testing/wdk_fixtures.py`, `devtools/fixtures.py`,
`devtools/eda_schemas.py`. `src/veupathdb/__init__.py` exports `__version__`
only, `src/veupathdb/wdk/__init__.py` is a one-line docstring, and
`src/veupathdb/domain/__init__.py` is empty. The two consumers import 62
distinct `veupathdb.*` modules between them (58 and 37); 53 of the 62 appear
nowhere in README, and both import `veupathdb.wdk._failures`, which is private
by name. The tool server gates 13 surfaces holding 269 names against a
checked-in `published_surface.json`, with six assertions: the surface is listed,
it is the checked-in one, every name resolves, no name is private, every name is
declared in that package, and no name is a submodule. This package has no such
file and no such test.

**Why that's wrong.** A second consumer learns the entry points by reading
PathFinder's imports, and copies a private module while doing it: `_failures`
already crosses the repository boundary twice. Because nothing here states what
is published, a rename inside any module can break a consumer while every gate
in this checkout stays green, and the release that ships it carries no signal
that it is breaking.

**Why it happens.** No package module declares the names it publishes, so there
is no declaration for a test to read. The only copy of the gate lives in the
tool server.

**Fix.** In this repository. Declare `__all__` on `veupathdb`, `veupathdb.wdk`,
`veupathdb.eda`, `veupathdb.domain`, `veupathdb.domain.parameters`,
`veupathdb.domain.strategy`, `veupathdb.testing` and
`veupathdb.wdk.strategy_api`; check in `tests/unit/published_surface.json` and a
copy of the tool server's six assertions beside it; and give whatever
`wdk/_failures.py` publishes to both consumers a public home, so no surface
names a private module. README's quickstart then points at the declared surface
instead of listing modules by hand. The tool server's copy is the model, and the
two stay comparable the way the gate scripts do
([the gate scripts are copies](../conventions/gate-scripts-are-copies.md)).

**What you'd get.** A rename that drops a name a consumer reads fails in this
checkout, before a release. A second consumer reads one list of entry points
instead of another repository's import graph.
