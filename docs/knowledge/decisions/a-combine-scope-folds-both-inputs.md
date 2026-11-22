---
type: Decision
title: The organism scope of a combine folds both of its inputs
description: extract_output_organisms reads a combine from both inputs by its operator, and an INTERSECT takes the union of both scopes; the primary input alone, the set intersection of the two scopes and the known side alone were rejected.
tags: [strategy, organism, boolean]
generated: { by: claude-code/opus-5, at: 2026-11-12T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-11-12T00:00:00Z }
status: stable
---

# What was decided

`extract_output_organisms` reads the scope of a step with two inputs from both inputs:

| operator | scope |
|---|---|
| `UNION` | the union of both scopes; unknown if either is unknown |
| `INTERSECT` | the union of both scopes; unknown if either is unknown |
| `MINUS`, `LONLY` | the primary scope |
| `RMINUS`, `RONLY` | the secondary scope |
| `COLOCATE` | the primary scope for `output` `a`, the secondary scope for `b` |

A step with one input keeps its rule: `GenesByOrthologs` states its target organism, and
any other transform has the scope of its input. A leaf reads the parameter its search
marks as its organism parameter (WDK-PARAM-013). A leaf whose search marks none reads its organisms from
`leaf_organisms`, a map by step id that the host fills, for example from the dataset a
study search runs on.

The operator sides follow WDK. The boolean query's left operand is its first answer
parameter, so it is the primary input
([WDK-STEP-001](../wdk/rules/strategies-and-steps.md)).
[`BooleanQueryInstance`](https://github.com/VEuPathDB/WDK/blob/6f261f77f52456b4ceded0693b4baca36fa96838/Model/src/main/java/org/gusdb/wdk/model/query/BooleanQueryInstance.java#L59-L82)
returns the left operand alone for `LONLY`, the right operand alone for `RONLY`, and swaps
the operands for `RMINUS`. `GenesBySpanLogic` declares `span_a` before `span_b`
([spanQueries.xml](https://github.com/VEuPathDB/ApiCommonModel/blob/d9ac98738c6b69349178e5083d389af41de83a39/Model/lib/wdk/model/questions/queries/spanQueries.xml#L331-L345)),
so region A is the primary input, and `span_output` names the side whose records the
step returns.

# Why

A record is in an `INTERSECT` only if both inputs hold it, so its organism is in the
scope of each input. The two scopes can name that organism at different ranks: a study
step names `Plasmodium knowlesi strain H` and an ortholog profile names `Apicomplexa`.
The library holds no taxonomy, so it cannot tell that one name holds the other. The union
holds every name either input uses for a record the intersection can return, so a check
that compares names never calls such a record out of scope. The union does not depend on
the order of the operands. When one input is unknown, the names it would add are unknown,
so the scope is unknown and a check makes no claim.

# What was rejected

**The primary input alone.** This was the rule before. The scope of
`INTERSECT(UNION(T. gondii GT1, T. gondii GT1, P. knowlesi H, P. knowlesi A1H1),
GenesByOrthologPattern[Apicomplexa])` was `{Toxoplasma gondii GT1}`, the first leaf of
the primary path, and a check called every P. knowlesi gene of the result out of scope.
With the operands swapped the scope was `{Apicomplexa}`. The answer followed the operand
order, not the strategy.

**The set intersection of the two scopes.** Without a taxonomy, names at two ranks never
match: `{Toxoplasma gondii GT1, Plasmodium knowlesi strain H, Plasmodium knowlesi strain
A1H1} & {Apicomplexa}` is empty, and a check then calls every record out of scope.

**The known side when the other side is unknown.** Each input holds every record of the
intersection, so the known side is a true scope. But a check compares names, and the
known side can name a rank above the records (`Apicomplexa`) while only the unknown side
names them at their own rank. The result then calls true records out of scope.

**The narrower side.** The library cannot tell which side is narrower without a taxonomy.
A host that holds one can intersect the expanded scopes itself.
