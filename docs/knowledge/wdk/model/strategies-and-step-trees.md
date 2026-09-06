---
type: Reference
title: Strategies and step trees
description: Why WDK sends structure and step data as two separate things, what the root step decides, and why the only way to change a strategy's shape is to replace the whole tree.
tags: [wdk-alignment, strategy, step-tree, model]
generated: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
status: stable
---

Every permalink below is pinned to the sha recorded in [sources.md](../sources.md).

# A strategy is a tree of step ids plus a map of step data

`GET /users/{userId}/strategies/{strategyId}` returns two fields that describe the same
steps in two different ways, and keeping them apart is the whole of this page.

```
stepTree: { stepId, primaryInput?, secondaryInput? }   // structure, nothing else
steps:    { "<stepId>": Step, ... }                    // data, keyed by id
```

[`StrategyFormatter.getDetailedStrategyJson`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/StrategyFormatter.java#L56-L67)
builds them in that order: it walks the root step into a tree, accumulating the steps it
passes, and then formats each accumulated step into the map. The tree builder
[`StepFormatter.formatAsStepTree`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/StepFormatter.java#L129-L140)
puts exactly one key on each node - `stepId` - and then recurses into
`primaryInput` and `secondaryInput` if those steps exist. No name, no search, no count.
`wdk-client` declares the same three-field
[`StepTree`](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkUser.ts#L145-L149)
and the same
[`StrategyDetails`](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkUser.ts#L120-L123)
pairing.

PathFinder's in-memory graph makes the same split for its own reasons, which are recorded
in the nested-tree decision (`pathfinder: docs/knowledge/decisions/nested-tree-at-the-wire-boundary.md`) and are
not repeated here.

# The tree is a projection of answer parameter values

This is the fact that makes the rest of WDK's step behavior predictable, and it is not
visible from the JSON.

There is no step-tree table. A step's inputs are ordinary parameter values on that step:
answer parameters, whose stable value is a step id as a decimal string. Read
[`Strategy.buildTree`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/Strategy.java#L376-L387):
to find a step's children it looks up the step's question, takes that question's answer
parameters in order, reads each one's value out of the step's own parameter map, and
recurses on the id it finds there. The tree is reconstructed on every load from parameter
values.

The reverse direction is
[`StrategyRequest.treeToSteps`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/request/strategy/StrategyRequest.java#L177-L201).
When you PUT a tree, WDK walks it breadth-first and, for each node that carries a
`primaryInput`, writes the child's id into that step's first answer parameter; a
`secondaryInput` goes into the second. So sending a tree is not describing a structure to
WDK. It is a compact way of setting parameter values on several steps at once.

Two consequences follow immediately, and both of them are things that surprise clients.

**Nesting a node under a step whose search has no answer parameter is rejected**, with
`Step <id> does not allow a primary input step.` - there is no parameter to write the child
id into. The same message exists for the secondary input.

**A step outside a strategy has no inputs at all.** Its answer parameters carry
[`AnswerParam.NULL_VALUE`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/AnswerParam.java#L44-L46),
which is the empty string, and `Step` asserts that null-inputs and no-strategy go together in both directions
([WDK-STEP-004](../rules/strategies-and-steps.md)).

# Exactly one root, and nothing may hide outside it

The root is named twice. `rootStepId` is a scalar on the strategy, and the outermost node
of `stepTree` is the same step;
[`treeToSteps` returns the id of the first node it polls](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/request/strategy/StrategyRequest.java#L143-L151)
as the root, and that is the node at the top of the JSON you sent.

A strategy cannot be built without one:
[`StrategyBuilder.build`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/Strategy.java#L202-L208)
throws before doing anything else if `rootStepId` is zero. And the tree must account for
every step the strategy holds: `buildTree` removes each step it visits from a working copy
of the step map, and
[whatever is left over is an error](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/Strategy.java#L297-L301)
- `has been assigned the following steps which are not referenced in its tree`. A step is
either reachable from the root or it is not in the strategy. There is no third state
([WDK-STRAT-003](../rules/strategies-and-steps.md)).

WDK does not check for cycles. The check is
[written and commented out](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/Strategy.java#L293-L296),
with a note that what is wanted is a directed tree rather than any other graph. In
practice a cycle is caught anyway, because `buildTree` removes each visited step from the
map before recursing, so revisiting one reports it as unassigned rather than looping. That
is a side effect, not a guarantee, and the message it produces names the wrong problem.

# What the root step decides

The root is not merely the last step. Several of the strategy's own fields are read off it.

| Strategy field | Comes from |
|---|---|
| `recordClassName` | [`Strategy.getRecordClass`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/Strategy.java#L483-L485) delegates to the root step's record class, and [`StrategyFormatter`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/StrategyFormatter.java#L29-L37) serializes its url segment, or `null` when the root's search is invalid |
| `estimatedSize` | the root step, both ways: [`getEstimatedSize`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/Strategy.java#L521-L527) for the summary, and `getResultSize` - which falls back to `0` on exception - written over it in the detail response |
| `nameOfFirstStep` | [`getMostPrimaryLeafStep`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/Strategy.java#L467-L477), which walks primary inputs down from the root and stops where there is no primary input |
| `leafAndTransformStepCount` | [every step whose search has fewer than two answer parameters](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/Strategy.java#L449-L465), which is the count a researcher sees in the UI |

`leafAndTransformStepCount` is worth pausing on because it is the number a scientist reads
as "how many steps is this". It excludes combined steps deliberately: the UI renders a
strategy as a linear list of things that were done, and a boolean is the joining of two of
them rather than one more of them. A tree of seven steps with three booleans shows as four.

`nameOfFirstStep` encodes the same linear reading. The primary input chain is the spine of
the strategy - what you started from - and everything hanging off a secondary input is a
branch that was brought in later. WDK does not enforce that reading; it is a convention the
formatters bake in, and it is why putting the scientifically-primary set on the secondary
input produces a strategy that reads backwards even though it computes the same answer.

# Structure changes only by replacing the whole tree

There is no endpoint that adds a step to a strategy, removes one, or re-parents one. There
is
[`PUT /users/{userId}/strategies/{strategyId}/step-tree`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/user/StrategyService.java#L211-L220),
which takes a whole tree, and `POST /users/{userId}/strategies`, which takes a whole tree
for a new strategy. Every structural edit is expressed as the tree you want afterwards.

The replacement is not additive.
[`overwriteStepTreeAndSave`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/user/StrategyService.java#L230-L248)
clears the step map, sets the new root, adds the parsed steps, and then diffs the old
strategy's steps against the new tree. Anything that fell out is **orphaned**, not deleted:
`Step.builder(orphan).removeStrategy()` detaches it from the strategy and clears its answer
parameter values, and the row stays. An orphan is a real step that belongs to the user,
belongs to no strategy, has no inputs, and cannot be run
([WDK-STEP-005](../rules/strategies-and-steps.md)).

Two things about the replacement are easy to get wrong.

It **validates structure, not values**. The new strategy is built at `ValidationLevel.NONE`,
so a success from this endpoint says the tree is a tree and the steps are yours; it says
nothing about whether any step will run
([WDK-STRAT-005](../rules/strategies-and-steps.md)). That success is a **204**, not a 200 -
`replaceStepTree` returns `void`, and 204 was what both sites answered on 2026-08-10.

It **will not steal a step from another strategy**.
[`treeToSteps` rejects](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/request/strategy/StrategyRequest.java#L162-L172)
any node whose step already carries a different strategy id, with `belongs to strategy <id>
so cannot be assigned to`. Sharing a subtree between two strategies is not possible; copying
one is, through `POST .../duplicated-step-tree`, which returns a tree of freshly-created
step ids.

# Why the shape is the science

`A INTERSECT (B UNION C)` and `(A INTERSECT B) UNION C` are both well-formed trees, both
accepted, and both answer a different question. That is not a hypothetical - it was measured
on live WDK, and the numbers and the gene that went missing are in
the structure-is-a-tree decision (`pathfinder: docs/knowledge/decisions/structure-is-a-tree.md`).

What matters here is that WDK is the reason the distinction survives at all. A step carries
up to two answer parameters, the second of which is a whole subtree's worth of structure,
and `treeToSteps` recurses into `secondaryInput` exactly as it does into `primaryInput`. A
client that models a strategy as an ordered list of operations and left-folds it can only
ever produce a left spine, and WDK will accept that spine without complaint
([WDK-STRAT-006](../rules/strategies-and-steps.md)).
