---
type: Backlog
title: Every test file passes the strict type check
description: The mypy gate covers src and the test files that install an observer; a strict run over all of tests/ finds 129 errors in 27 other files.
tags: [testing, typing, gates]
status: draft
---

# What is missing

The mypy gate in CI and pre-commit checks `src`, `tests/unit/test_errors.py` and the six test
files that install an `Observer`. A strict run over all of `tests/` reports 129 errors in 27
other test files.

# What it blocks

A protocol or signature change in `src` can break a test helper that no gate checks. The
observer test files were added to the gate because a new `Observer` method left two test
observers incomplete with no failure.

# Done when

`uv run mypy src tests` passes under the strict settings, and the CI and pre-commit gates
name `tests` in place of the file list.
