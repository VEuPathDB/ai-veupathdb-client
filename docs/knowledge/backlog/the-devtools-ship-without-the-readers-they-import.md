---
type: Backlog
title: The devtools ship in the wheel and their schema readers do not
description: veupathdb.devtools.fixtures and veupathdb.devtools.eda_schemas import jsonschema and referencing, which are dev-group only, so the five commands README advertises cannot run from an installed copy.
tags: [packaging, devtools, generality, release]
status: draft
---

# The devtools ship in the wheel and their schema readers do not

**What I did.** Read the imports of the two shipped devtools and the
distribution's declared dependencies: `src/veupathdb/devtools/fixtures.py:35,37,38`,
`src/veupathdb/devtools/eda_schemas.py:36`, `pyproject.toml` `[project]
dependencies` (6-15), `[project.optional-dependencies]` (17-19),
`[dependency-groups] dev` (35-46) and `[tool.hatch.build.targets.wheel]`
(25-26). Read the commands README advertises at lines 193-197 and the packaging
lane at `tests/packaging/test_wheel_carries_the_fixtures.py`.

**What I got.** `fixtures.py` imports `jsonschema.Draft4Validator`,
`referencing.Registry` and `referencing.jsonschema`; `eda_schemas.py` imports
`jsonschema.Draft7Validator`. The runtime dependencies are pydantic,
pydantic-settings, httpx, tenacity, pyjwt, pyyaml, json5 and structlog. Neither
`jsonschema` nor `referencing` is among them: both sit in the `dev` group only
(`pyproject.toml:38,43`), and the sole extra is `otel` (`pyproject.toml:19`).
The wheel packs `src/veupathdb` whole, so `veupathdb/devtools` is installed.
README:193-197 advertises five commands over those two modules: `fixtures
record`, `fixtures vendor`, `fixtures verify`, `eda_schemas vendor` and
`eda_schemas verify`.

**Why that's wrong.** An installed copy carries two modules that cannot import.
The five commands README tells a consumer to run fail at import with
`ModuleNotFoundError` for `jsonschema`, so the consumer cannot verify the
recorded fixtures it was shipped, which is the one procedure that proves its own
copy of the wire shapes still matches the sites. The failure is a missing
dependency, not a missing tool, so it reads as a broken install.

**Why it happens.** The two schema readers are declared in `[dependency-groups]
dev`. A dependency group is for this checkout and never reaches an installed
copy, while `[tool.hatch.build.targets.wheel] packages` ships the modules that
import it.

**Fix.** In this repository. Declare a `devtools` extra holding `jsonschema` and
`referencing`, keep the `dev` group resolving it, and have README name the extra
in the line above the commands. Removing `veupathdb/devtools` from the wheel is
not open: `pathfinder: apps/api/src/pathfinder/devtools/chat.py` imports
`veupathdb.devtools.wdk_capture` from an installed copy, and that module needs
neither reader. A case in the packaging lane
(`tests/packaging/`, marker `wheel`) imports
`veupathdb.devtools.fixtures` and `veupathdb.devtools.eda_schemas` from the
built wheel with the extra installed, so the gap cannot come back. The
packaging change rides the next release of `veupathdb-py` (`0.1.0a8`), which the
consuming application takes by raising the `tag` in
`pathfinder: apps/api/pyproject.toml` and relocking.

**What you'd get.** `uv add "veupathdb-py[devtools]"` followed by `python -m
veupathdb.devtools.fixtures verify` reports the recorded bodies against the
vendored schemas, on an installed copy, with no checkout of this repository.
