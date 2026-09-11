---
type: Backlog
title: Three docstrings describe a caller's layers, an agent and an LLM
description: SearchContext, bundle_rows and param_value_from_raw explain themselves by naming the catalog service, the transport and the AI tool layers, the agent tools and the LLM; no code depends on any of it, and the shapes are general.
tags: [docstrings, coupling, generality]
status: draft
---

# Three docstrings describe a caller's layers, an agent and an LLM

**What I did.** Grepped `src/veupathdb` for host vocabulary and opened every
hit: `src/veupathdb/domain/search.py:11`, `src/veupathdb/wdk/_failures.py:28`,
`src/veupathdb/domain/parameters/value_codec.py:159`. Checked whether any
behaviour reads the vocabulary.

**What I got.** Three docstrings, and no code behind them.

- `SearchContext` is described as the triplet "passed throughout the catalog
  service, transport, and AI tool layers". The catalog service and the transport
  are two other repositories' layers; the class itself is a frozen dataclass of
  `site_id`, `record_type` and `search_name`.
- `bundle_rows` is described as "One row per refused parameter. The agent tools
  read this shape." It turns `StepValidation.errors.by_key` into rows.
- `param_value_from_raw` builds a typed value "from a raw scalar/list/dict the
  LLM supplied".

Nothing in the tree branches on any of it: the three functions behave the same
whoever calls them.

**Why that's wrong.** A second consumer reading its own stack trace into these
modules is told the shape was designed for someone else's layers, and has to
decide whether the docstring describes a requirement (must I have an agent
layer? does `param_value_from_raw` assume a model produced the value?) or a
habit. Each is a habit, but the reader cannot know that without reading the
body, which is the work the docstring exists to save.

**Why it happens.** The three docstrings were written where the callers were
visible and were not re-read when the package was split out. Nothing gates host
vocabulary in `src/`, and `tests/unit/test_package_boundary.py` gates imports,
not prose.

**Fix.** In this repository. Rewrite each docstring to state what the symbol is
and what it takes, with no caller named: the search triplet a client addresses,
one row per refused parameter keyed by parameter name, and a typed value built
from an untyped scalar, list or dict. Extend the package-boundary test with a
case that fails on host vocabulary in `src/veupathdb` docstrings, using the same
word list the import case already carries in spirit, so the next one is caught
at the gate rather than by a reader.

**What you'd get.** Three docstrings that answer the question a reader arrived
with, and a gate that keeps the next caller's name out of this package.
