---
type: Backlog
title: The consumer import record is measured again
description: tests/unit/consumer_imports.json no longer matches what the two consumers import, so the gate that holds a consumer's names on the surface misses names both read today.
tags: [public-surface, gates, testing]
status: draft
---

# What is missing

`tests/unit/consumer_imports.json` records the names each in-house consumer reads, surface
by surface. Measured from the trees on 2026-10-22 it differs from both:

- `veupathdb-mcp` (`src` and `tests`) reads seventeen names from `veupathdb.jbrowse`,
  which the record does not list, and new names from `veupathdb`, `veupathdb.wdk`,
  `veupathdb.domain.parameters`, `veupathdb.testing` and `veupathdb.errors`.
- `pathfinder` (`apps/api/src`) reads new names from `veupathdb.wdk`, `veupathdb.eda`,
  `veupathdb.domain.parameters`, `veupathdb.errors`, `veupathdb.guest_token` and
  `veupathdb.jbrowse`.
- Both import from modules that are no surface: `veupathdb.jbrowse.tabix`,
  `veupathdb.devtools.wdk_capture`, `veupathdb.domain.parameters.values`,
  `veupathdb.domain.strategy.graph_model`, `veupathdb.settings`,
  `veupathdb.testing.fixture_store` and others.

# What it blocks

A rename of a name a consumer reads, but the record does not list, passes here and fails
in the consumer after the release.

# Done when

Each consumer imports only from published surfaces, the record is measured again from
both trees, and every recorded name resolves on the surface it is read from.
