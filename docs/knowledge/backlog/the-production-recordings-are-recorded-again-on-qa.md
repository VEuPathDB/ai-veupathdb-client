---
type: Backlog
title: The production recordings are recorded again on QA
description: The WDK, EDA and VDI bodies recorded on production sites moved to fixtures-production-backup-2026-10-09/, and every test that reads one is skipped with NEEDS_QA_RECORDING until the QA sites are recorded.
tags: [testing, recording, sites]
status: draft
---

# What is missing

`fixtures-production-backup-2026-10-09/` holds 21 WDK bodies, 20 EDA bodies with their
`provenance.json`, and 17 VDI bodies with theirs, all recorded on production. The store
under `src/veupathdb/testing/fixtures/` holds the vendored WDK schemas and the pinned EDA
RAML only.

# What it blocks

Every test marked with `NEEDS_QA_RECORDING` (`uv run pytest tests/unit -rs` lists them),
the two recording reads in `tests/packaging/`, the recording comparisons in
`tests/live/`, and the WDK rules those tests enforce. A consumer that reads
`veupathdb.testing` recordings finds them missing.

# How to finish

QA answers automated clients first: outside the VEuPathDB network the QA sites answer
with a pre-release login. Then run `fixtures record`, `eda_capture record` and one
`vdi_capture record` per install the backup holds, re-measure every count, identifier
and vocabulary a test or a knowledge page pins, drop the skip markers, delete the backup
directory, and remove this item and its line.
