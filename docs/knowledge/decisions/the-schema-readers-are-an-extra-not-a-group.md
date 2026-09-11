---
type: Decision
title: The schema readers are an extra, not a dependency group
description: jsonschema and referencing move to a devtools extra, so an installed copy can run the five commands README advertises. Removing veupathdb/devtools from the wheel was rejected.
tags: [packaging, devtools, release]
generated: { by: claude-code/opus-5, at: 2026-09-11T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-11T00:00:00Z }
status: stable
---

# What was decided

`[project.optional-dependencies] devtools` holds `jsonschema` and `referencing`. The
`dev` group resolves that extra (`veupathdb-py[devtools]`) rather than naming the two
distributions again, so the checkout and an installed copy read one list. README names
the extra in the line above the five commands.

# The alternative that was rejected

Remove `veupathdb/devtools` from the wheel and leave the readers in the `dev` group.
That is not open: a consumer imports `veupathdb.devtools.wdk_capture` from an installed
copy and that module needs neither reader. Dropping the package would break a working
import to fix two that do not work.

Leaving the two readers as runtime dependencies was also rejected: nothing the client
sends or parses at runtime reads a JSON schema, so every install would carry a
validator it never calls.

# What a consumer does at the next tag

The application imports `veupathdb.devtools.wdk_capture`, which needs neither reader, and
twelve names from `veupathdb.devtools.eda_schemas`, which needs both. It takes the extra
when it raises the tag: `veupathdb-py[devtools]` in `pathfinder: apps/api/pyproject.toml`.
The tool server imports neither module and changes nothing.

# What holds it

`tests/packaging/test_the_devtools_extra_carries_their_readers.py` builds the wheel,
installs `<wheel>[devtools]` into a fresh interpreter, imports both devtools there, and
runs `python -m veupathdb.devtools.fixtures verify` in it. The case carries the `wheel`
marker, so it runs in the packaging lane CI already invokes.
