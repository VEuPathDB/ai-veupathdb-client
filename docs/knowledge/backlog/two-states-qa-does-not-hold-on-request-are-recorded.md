---
type: Backlog
title: Two states QA does not hold on request are recorded
description: A cached AI expression summary and a crashed VDI import have no QA recording, so the tests that read them are skipped with NEEDS_QA_RECORDING.
tags: [testing, recording, sites]
status: draft
---

# What is missing

`wdk/ai_expression_summary_present.json`: QA holds no cached AI expression summary, and
asking for one with `populateIfNotPresent` starts the site's summary job, which no test or
recorder may do. `vdi/rnaseqrc_import_failed.json`: no upload makes a VDI import crash on
demand; an upload the importer rejects is `import_invalid`, a different state.

# What it blocks

The five AI expression tests in `tests/unit/wdk/test_ai_expression.py` and the three VDI
tests that read a crashed import (`uv run pytest tests/unit -rs` lists them).

# How to finish

Record each body when QA holds the state: a summary the site built for a gene on its own,
read with `populateIfNotPresent` false, and a crashed import found in the account's own
listing. Re-measure what the skipped tests pin, and remove this item and its line.
