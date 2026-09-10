---
type: Decision
title: An unbound parameter is a parameter, and the criterion that holds it is not
description: the authoring model and the step build lifecycle left domain/strategy for the consuming application, and OpenSlot split on the way out - the parameter name, question and vocabulary are UnboundParameter under domain/parameters, while the criterion id went with the spec.
tags: [architecture, strategy, parameters, placement, packaging]
generated: { by: claude-code/opus-5, at: 2026-09-10T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-10T00:00:00Z }
status: stable
---

# What was decided

`src/veupathdb/domain/strategy/` keeps the shapes WDK states and nothing else.

| module | verdict | why |
| --- | --- | --- |
| `ast` | stays | the nested step tree, with WDK's step filters, analyses, reports, weight and collapsed saved strategy |
| `graph_model` | stays | WDK states structure twice; this is the keyed step map and the projection between the two forms |
| `graph_model.StepStatus` and `step_status` | left | a build lifecycle over the keyed map: whether a step has reached WDK yet |
| `tree` | stays | traversal of both forms |
| `ops` | stays | WDK's combine operator set and the span-logic parameter names |
| `validation` | stays | the validation bundle a WDK refusal carries |
| `strategy_ast` | stays | `root` is WDK's step tree; the sync maps beside it are the consumer's |
| `organism` | stays | reads WDK's organism parameters and the `GenesByOrthologs` scope rule |
| `operational_spec` | left | a goal split into criteria, with roles, confidence and assumptions |
| `constraints` | left | the requirements read out of the user's prose |
| `session` | left | working state of a strategy under construction in a chat |
| `operations/` | left | the edit algebra over that working state |
| `spec_diff` | left | what one turn did to a spec |
| `combination_check` | left | whether a tree honors a combination stated in prose |
| `build_outcome` | left | a build result the consumer surfaces to its own reader |
| `types.SyncStateProtocol` | left | the consumer's per-step sync state |
| `strategy_ast.PersistedStrategyGraph` | left | the consumer's stored row around a snapshot |
| `types.WireParams` | moved | a WDK wire alias, now stated by `veupathdb.wdk.value_decoding` |

`tests/unit/domain/strategy/test_the_authoring_model_is_not_here.py` asserts the
module set, names every module that may not come back, names `StepStatus` and
`step_status` as definitions `graph_model` may not hold, and asserts the fields of
the model that replaced the half of `OpenSlot` worth keeping.

# Where the split runs

`OpenSlot` carried four fields. Three of them - `param_name`, `question` and
`options` - describe a parameter of a search that holds no value, and they are what
the MCP server's parameter binding writes and reads: `catalog/_param_binding.py`,
`catalog/_param_filters.py` and `catalog/param_dag.py` set the name, the question and
the vocabulary, and name no criterion. The fourth, `criterion_id`, addresses a
criterion of an operational spec, which only the authoring caller has.

So the three are `UnboundParameter` in `veupathdb.domain.parameters.unbound`, beside
the parameter values and specs they talk about, and `criterion_id` left with the spec
that defines a criterion. The consuming application states its own model over the
library's one.

# What was rejected

**Keep the whole model here because `veupathdb-mcp` imports one name from it.** That
holds 474 lines of an authoring model in a WDK client to satisfy three import lines.
The imports name a parameter concept, so the name moves and the three lines follow.

**Move the name unchanged.** `OpenSlot` says nothing about a parameter, and the
criterion field is unreadable in a package that has no criteria.

**Keep a re-export at the old path.** A module that exists only to forward a name is
the shim this project does not ship. `veupathdb-mcp` names the new path in the
release that takes this one; the two versions move together.

# What it changes upstream

`veupathdb-mcp` swaps one import in each of its three catalog modules and the symbol
they use. It names nothing of the step lifecycle, so that move costs it nothing. The
consuming application takes `operational_spec` and `constraints` into its own
`domain/strategy/`, where `OpenSlot` states `criterion_id` over `UnboundParameter`,
and takes `StepStatus` and `step_status` beside them; `StrategyStep` and
`is_computable` stay here and the lifecycle reads them across the seam.

The consuming application's backlog card said the cut costs 47 edges from
`veupathdb.wdk`. Measured in this checkout the whole edge set was four lines into
three modules, all of them WDK shapes; the split had already cut the rest.
