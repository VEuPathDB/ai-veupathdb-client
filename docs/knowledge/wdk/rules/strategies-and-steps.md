---
type: Rules
title: Strategy and step rules
description: What WDK requires of a step tree, what it requires of a step, and the two places it accepts a wrong shape without saying so.
tags: [wdk-alignment, rules, strategy, steps, boolean]
generated: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
status: stable
---

# WDK-STRAT - the strategy and its tree

### WDK-STEP-001 - A step's kind is the number of answer parameters its search declares, and primary against secondary is their order

- class: CONTRACT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/Step.java#L440-L472
- anchor: src/veupathdb/domain/strategy/graph_model.py:StepKind
- status: ENFORCED by tests/unit/wdk/test_wdk_models.py::test_wdk_step_001_an_input_parameter_has_no_naming_convention

There is no kind field on a step. `findAnswerParamsStep` takes an ordinal, and
[the two accessors](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/Step.java#L651-L667)
are ordinal 0 for the primary input parameter and ordinal 1 for the secondary. A maximum
of two is supported, which the comment states. So zero answer parameters is a leaf, one is
a transform, two is a combined step, and
[`getLeafAndTransformStepCount`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/Strategy.java#L449-L465)
does exactly that arithmetic to produce the step count a researcher sees.

The consequence that bites: **there is no naming convention identifying an input
parameter.** `bq_left_op_*` looks like one but is specific to the generated boolean query;
`GenesByOrthologs` calls its input `gene_result`, confirmed live on plasmodb.org on
2026-08-10, where its `paramNames` are `["gene_result", "organism", "isSyntenic"]` and
`gene_result` is the only one of type `input-step`. A client that needs a search's input
parameter names must read the search's parameter list and take the `input-step` entries in
declaration order. Guessing by prefix works until it silently does not.

### WDK-STEP-002 - Every answer parameter of a newly created step must be the empty string

- class: HARD
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/request/strategy/StepRequestParser.java#L81-L87
- anchor: src/veupathdb/wdk/strategy_api/steps.py:_empty_answer_params
- status: ENFORCED by tests/unit/wdk/test_strategy_api_steps.py::test_empty_answer_params_forces_input_step_params_empty

`newStepFromJson` walks the answer parameters of the new step's search and throws
`Answer Params in new steps must have the null value (empty string).` on any that is not
[`AnswerParam.NULL_VALUE`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/AnswerParam.java#L44-L46),
which is `""`. `DataValidationException`, so 422. The parameter's own
[`isAllowEmpty` comment](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/AnswerParam.java#L192-L205)
records the reason: empty is allowed precisely because that is how combiner steps are
constructed before they are incorporated into a strategy.

This is the ordering constraint that shapes every build sequence. A combined step is
created with both operands empty and an operator, and only becomes a combination when a
step tree names its inputs. There is no call that creates a wired step. Any client that
tries to POST a step with its inputs already filled in is working against the grain and
will be refused.

`_empty_answer_params` forces the empty string over whatever the caller supplied, which is
stronger than omitting the key and is deliberately so: the named test passes a stale
`gene_result` of `999` and asserts it comes back `""`.

### WDK-STEP-003 - `PUT .../search-config` cannot change a step's inputs

- class: HARD
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/request/strategy/StepRequestParser.java#L157-L170
- anchor: src/veupathdb/wdk/_analyses.py:update_step_filters
- status: UNENFORCED
- reason: enforced in the consuming application, at apps/api/src/pathfinder/tests/unit/platform/test_wdk_analyses.py::test_wdk_step_003_an_answer_parameter_survives_a_filter_write

Answer parameters live in the same flat `searchConfig.parameters` map as everything else, so
a search-config replacement looks like it could rewire a step. It cannot.
`assertAnswerParamsUnmodified` compares every answer parameter in the incoming spec against
the step's current value and throws `Changes to answer param values are not allowed.` on
any difference. The comment above it says why: the strategy service owns the tree.

Both branches of
[`putAnswerSpec`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/user/StepService.java#L314-L364)
run the check, including the undocumented `allowInvalid=true` developer path, so there is
no way around it.

Practically this makes any search-config write a read-modify-write. You must fetch the
step, keep its answer parameter values byte for byte, change the parameters you meant to
change, and PUT the whole thing. Dropping an answer parameter is changing it. PathFinder's
filter update does the round trip correctly - it copies `step.search_config.parameters`
wholesale - though nothing tests that it keeps doing so.

Source-only: read off the pinned sha, not confirmed against a running site. See
[the pin-versus-deployment note](../sources.md).

### WDK-STEP-004 - A step inside a strategy must have every answer parameter filled; a half-wired combine is not a degraded combine

- class: HARD
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/Step.java#L392-L402
- anchor: src/veupathdb/domain/strategy/graph_model.py:pushable_root_id
- status: UNENFORCED
- reason: enforced in the consuming application, at apps/api/src/pathfinder/tests/unit/domain/strategy/test_graph_model.py::TestComputability::test_the_pushable_root_walks_past_a_half_wired_combine

`Step`'s constructor asserts the biconditional directly: no strategy implies every answer
parameter is null, and a strategy implies none of them is. Either violation throws
`WdkModelException`.

Note the class. `WdkModelException` is not one of the types
[the exception mapper assigns a status to](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/provider/ExceptionMapper.java#L118-L127),
so it lands in the catch-all and comes back **500 with body `Internal Error`**, not the 422
that a malformed request usually earns ([WDK-HTTP-002](auth-and-transport.md)). A tree that
gives a two-input step only one input is therefore indistinguishable, from the response
alone, from WDK having a bug. That is the whole reason this rule is worth writing down: the
error tells you nothing, so the client has to know.

Source-only: read off the pinned sha, not confirmed against a running site. See
[the pin-versus-deployment note](../sources.md).

PathFinder never sends one. `pushable_root_id` walks down past a step that is not
computable and hands WDK the surviving branch instead, which is what keeps a
mid-rewiring canvas from becoming a 500. The named test cuts an edge and asserts the
projection roots at the surviving input rather than at the broken combine.

### WDK-STEP-005 - A step that is not part of a strategy cannot be run

- class: HARD
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/user/StepService.java#L253-L259
- anchor: src/veupathdb/wdk/strategy_api/reports.py:get_step_count
- status: UNENFORCED
- reason: enforced in the consuming application, at veupathdb-mcp/tests/unit/wdk/test_step_results_reports.py::test_wdk_step_005_a_step_count_addresses_a_step_in_a_strategy

Both report paths check `if (!step.getStrategy().isPresent())` and throw
`Step <id> is not part of a strategy, so cannot run.` - 422 - and the
[column reporter](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/user/StepService.java#L408-L413)
repeats it verbatim. The comment on both says the step is refused *even if otherwise
runnable*, so this is a deliberate service-level restriction rather than a consequence of
validation.

Two things follow. Counting a step requires a strategy to exist around it, whether or not a
strategy is what you wanted; a freshly created step has no count and cannot be given one.
And a step that has just been orphaned by a tree replacement stops being runnable at that
moment, so a count fetched for it afterwards is a 422 rather than a stale number.

The unpersisted equivalent is `POST /record-types/{rc}/searches/{name}/reports/standard`,
which runs a search with no step and no strategy at all.

### WDK-STEP-006 - The boolean operand parameter names embed the record class full name, which is not the `recordClassName` a step reports

- class: HARD
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/BooleanQuery.java#L85-L110
- anchor: src/veupathdb/wdk/strategy_api/steps.py:_get_boolean_param_names
- status: ENFORCED by tests/unit/wdk/test_wdk_models.py::test_wdk_step_006_the_operand_names_carry_the_record_class_full_name

`setRecordClass` builds three parameters:
`bq_left_op_<full name with dots replaced by underscores>`,
`bq_right_op_<same>`, and
[`bq_operator`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/BooleanQuery.java#L57-L61),
which is a bare constant shared by every record class. Confirmed live on 2026-08-10:
`GET /record-types/transcript/searches/boolean_question_TranscriptRecordClasses_TranscriptRecordClass?expandParams=true`
returns `paramNames` of exactly
`["bq_left_op_TranscriptRecordClasses_TranscriptRecordClass", "bq_right_op_TranscriptRecordClasses_TranscriptRecordClass", "bq_operator"]`
on plasmodb.org and on toxodb.org.

The trap is that a step's `recordClassName` is the record class's **url segment** -
`transcript` -
[not its full name](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/StepFormatter.java#L86-L90).
There is no string transformation from one to the other; the pairing is site model data. So
the operand names cannot be constructed from anything on the step and must be read from the
boolean search's own parameter list, which is what `_get_boolean_param_names` does.

The operator's accepted values are the vocabulary **terms**, and four of the six differ
from their display labels because
[`prepareOperatorParam`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/BooleanQuery.java#L172-L197)
sets display from the
[enum constant name and term from the base operator](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/BooleanOperator.java#L14-L21):
send `MINUS`, not `LEFT_MINUS`. The default is `INTERSECT`.

### WDK-STEP-007 - Deleting a step that is part of a strategy is a 409; remove it from the tree first

- class: HARD
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/user/StepService.java#L148-L169
- anchor: src/veupathdb/wdk/strategy_api/steps.py:delete_step
- status: UNENFORCED
- reason: enforced in the consuming application, at apps/api/src/pathfinder/tests/unit/services/strategies/test_orphan_delete_after_sync.py::TestTheDeleteFollowsThePush::test_the_strategy_is_pushed_before_any_delete
`deleteStep` throws `ConflictException` - 409 - with `Steps that are part of strategies
cannot be deleted. Remove the step from strategy <id> and try again.` The deletion itself is
a soft one: it sets a deleted flag and updates the row.

So removing a step is two calls in a fixed order. First `PUT .../step-tree` with a tree that
omits it, which
[orphans it](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/user/StrategyService.java#L239-L248)
rather than deleting it, clearing its strategy and its answer parameter values. Then
`DELETE`. Reversing the order is the 409, and the step survives.

The tree you send in the first call has to be a legal tree, which is where re-parenting
comes in: omitting a non-leaf step leaves its parent an input short, and a two-input step
with one input is [WDK-STEP-004](#wdk-step-004---a-step-inside-a-strategy-must-have-every-answer-parameter-filled-a-half-wired-combine-is-not-a-degraded-combine),
a 500. The parent must either be given a replacement input or be omitted too. There is no
call that removes one step and leaves WDK to work out the rest.

The consuming application's own ordering is currently the wrong way round.
`pathfinder: apps/api/src/pathfinder/services/strategies/commit.py` deletes the WDK steps
for dropped nodes before `sync_strategy_for_site` pushes the new tree, so every such DELETE
hits a step that is still referenced by the strategy in WDK. `delete_step` only swallows
404, so the 409 propagates, `delete_orphaned_steps` catches it and logs `Failed to delete
orphaned WDK step`, and the row is left behind. It is not a data-loss bug - the tree push that follows orphans the
step anyway - but the cleanup never runs and the orphans accumulate.

Source-only: read off the pinned sha, not confirmed against a running site. See
[the pin-versus-deployment note](../sources.md).

### WDK-STEP-008 - Both operands of a boolean step are the same record class, and so is its result

- class: HARD
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/BooleanQuery.java#L149-L170
- anchor: src/veupathdb/domain/strategy/ops.py:BOOLEAN_OPERATORS
- status: ENFORCED by tests/unit/wdk/test_wdk_models.py::test_wdk_step_008_the_allowed_inputs_are_the_same_single_class

**The operands.** `prepareOperand` is called twice with the same `recordClass` argument and
adds a single `RecordClassReference` to each, so both accept exactly one record class and it
is the same one.

**The result.** Established by code rather than by inference:
[`prepareColumns`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/BooleanQuery.java#L199-L206)
builds the query's output columns from that same record class's primary key definition, so
the rows it emits are keyed as that record class and nothing else. Live confirmation on both
verification sites on 2026-08-10: the transcript boolean question reports
`outputRecordClassName` of `transcript`.

Both halves are also stated in the class comment, whose exact words at
[`#L32-L34`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/BooleanQuery.java#L31-L36)
are `The left and right operands have to be of the same recordClass type, and the result of
the boolean will be that same type as well.` A comment is weaker evidence than the code
above it, which is why it is cited last rather than first.

Enforcement is
[`AnswerParam.validateValue`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/AnswerParam.java#L140-L145),
`A step with record type '<name>' is not allowed` - but only at `RUNNABLE`, which is why
this arrives as a step validation failure and not as a rejected tree push
([WDK-STRAT-005](#wdk-strat-005---a-204-from-put-step-tree-says-the-tree-is-well-formed-not-that-the-strategy-runs)).

Live on both verification sites on 2026-08-10, the transcript boolean question reports
`allowedPrimaryInputRecordClassNames` and `allowedSecondaryInputRecordClassNames` of
`["transcript"]` and nothing else.

This is a property of the boolean question, not of two-input steps in general.
`GenesBySpanLogic` accepts `transcript`, `snp`, `popsetSequence` and `genomic-segment` on
either side - plus `snp-chip` on plasmodb.org, which toxodb.org does not have - because
colocation genuinely relates different kinds of thing. That asymmetry is why colocation is
excluded from the boolean operator set, for reasons recorded in
the boolean-operator decision (`pathfinder: docs/knowledge/decisions/boolean-operator-is-a-type.md`).

### WDK-STRAT-001 - A step tree node carries a step id and nothing else

- class: CONTRACT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/StepFormatter.java#L129-L140
- anchor: src/veupathdb/wdk/wdk_models.py:WDKStepTree
- status: ENFORCED by tests/unit/wdk/test_wdk_models.py::test_wdk_strat_001_a_leaf_node_serializes_to_one_key

`formatAsStepTree` puts exactly one key on a node, `stepId`, and then recurses into
`primaryInput` and `secondaryInput` where those steps exist. Structure and data are two
fields of the response, never one:
[`getDetailedStrategyJson`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/StrategyFormatter.java#L56-L67)
emits the tree and then a `steps` map keyed by the same ids. `wdk-client` declares the
same three-field
[`StepTree`](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkUser.ts#L145-L149).

The rule is worth stating because the tempting shape is the other one - a tree of whole
steps - and adopting it means every read has two copies of a step's data and every write
has to decide which copy won. PathFinder made that mistake once and unmade it; the
reasoning is in
the nested-tree decision (`pathfinder: docs/knowledge/decisions/nested-tree-at-the-wire-boundary.md`).

What the rule does not say is that the tree is the storage. It is not: WDK reconstructs it
from each step's answer parameter values on every load, and writes it back into them on
every PUT. See [strategies-and-step-trees](../model/strategies-and-step-trees.md).

### WDK-STRAT-002 - A strategy has exactly one root step

- class: HARD
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/Strategy.java#L202-L208
- anchor: src/veupathdb/domain/strategy/tree.py:root_ids
- status: UNENFORCED
- reason: enforced in the consuming application, at apps/api/src/pathfinder/tests/unit/services/strategies/test_wdk_pushed_step_tree.py::test_wdk_strat_002_the_pushed_tree_has_exactly_one_root

`StrategyBuilder.build` throws `Root step ID is required but has not been set.` before
constructing anything, so a strategy without a root cannot exist. The root is named twice
in the wire representation, as the scalar `rootStepId` and as the outermost node of
`stepTree`, and
[`treeToSteps` derives it from the tree](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/request/strategy/StrategyRequest.java#L143-L151)
- the first node it polls in a breadth-first walk, which is the node at the top of the JSON
you sent. A tree with two tops is not expressible; the outer object is the root by
construction.

The named test asserts `root_ids(steps) == {node.id}` over 100 generated trees, where a
root is a step no other step names as an input.

**The uncovered half is the wire boundary, and it is the half that matters.** Every tree
the test sees came out of `flatten_tree` on a single node, so single-rootedness holds *by
construction* - the test constrains `root_ids` against `flatten_tree`, not against
anything WDK requires. The consuming application genuinely does build multi-root step
maps: `pathfinder: apps/api/src/pathfinder/services/strategies/session_factory.py` loads
`flatten_tree(payload.root)` and then merges `flatten_tree(detached)` for every entry in
`payload.detached_roots`, which is a map with as many roots as the canvas has disconnected
subtrees. What keeps that off the wire is
`pathfinder: apps/api/src/pathfinder/services/strategies/sync.py`, which calls
`pushable_root_id` and then
`rebuild_tree` on the single id it returns
([WDK-STEP-004](#wdk-step-004---a-step-inside-a-strategy-must-have-every-answer-parameter-filled-a-half-wired-combine-is-not-a-degraded-combine)).
No test asserts that selection. This is the same gap
WDK-MAP-003 (`pathfinder: docs/knowledge/wdk/pathfinder/rules/pathfinder-mapping.md`) names: the projection to WDK's shape is untested,
and pure invertibility does not reach it.

### WDK-STRAT-003 - Every step a strategy holds is reachable from its root

- class: HARD
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/Strategy.java#L290-L301
- anchor: src/veupathdb/domain/strategy/tree.py:subtree_ids
- status: UNENFORCED
- reason: enforced in the consuming application, at apps/api/src/pathfinder/tests/unit/services/strategies/test_wdk_pushed_step_tree.py::test_wdk_strat_003_no_step_outside_the_pushed_subtree_appears

Reachability is enforced by exhaustion rather than by a traversal check.
[`buildTree`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/Strategy.java#L353-L387)
runs over a working copy of the step map and removes each step as it visits it; whatever
is still in the map afterwards is reported as `assigned the following steps which are not
referenced in its tree`. So a strategy cannot hold a detached step. There is no floating
state, and nothing to garbage-collect later.

The same mechanism means a step id appearing twice in one tree fails on the second visit,
with `has either not been assigned to that strategy or has been assigned more than once` -
a message that names two different faults because the check cannot tell them apart.
The explicit cycle check next to it is
[written and commented out](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/Strategy.java#L293-L296),
so do not read a rejected cycle as WDK detecting cycles; it is the same removal-from-map
side effect, reported under the wrong name.

The named test asserts that `subtree_ids` from the root yields exactly the keys of the step
map, with no duplicates - which is this rule and its double-visit corollary together. Note
what the anchor is: the traversal the test exercises, not `rebuild_tree`, which is the
projection that consumes it.

**The uncovered half is that projection**, for the reason set out under
[WDK-STRAT-002](#wdk-strat-002---a-strategy-has-exactly-one-root-step). The test's step
maps all come from `flatten_tree` on one node, so total reachability holds by
construction; the assertion pins `subtree_ids` against `flatten_tree` rather than against
WDK's exhaustion check. The map PathFinder actually holds can contain detached subtrees
that are unreachable from the pushed root by design, and what makes the push legal is
`sync.py` sending only `rebuild_tree(pushable_root_id(...))`. Nothing asserts that the
tree handed to `PUT .../step-tree` contains no step outside it.

### WDK-STRAT-004 - The strategy's record class is the root step's record class, not its leaves'

- class: CONTRACT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/Strategy.java#L483-L485
- anchor: src/veupathdb/domain/strategy/graph_model.py:record_class_of
- status: UNENFORCED
- reason: enforced in the consuming application, at apps/api/src/pathfinder/tests/unit/services/strategies/test_record_class_comes_from_the_root.py::TestTheStrategysClassIsTheRoots::test_a_class_crossing_transform_makes_the_strategy_its_own_class

`Strategy.getRecordClass` delegates to `getRootStep().getRecordClass()`, and
[`StrategyFormatter`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/StrategyFormatter.java#L29-L37)
serializes its url segment, or `null` when the root's search does not resolve. The root
also supplies `estimatedSize` and, through the primary-input chain, `nameOfFirstStep`.

This matters because a transform changes record class. `TranscriptsFromGenes` takes a
`gene` input and produces transcripts; `GenesByPathwaysTransform` takes a `pathway`. Both
were confirmed on plasmodb.org and toxodb.org on 2026-08-10 from
`allowedPrimaryInputRecordClassNames`. A strategy whose leaves are genes and whose root is
a transform is a transcript strategy.

**A step carries its own record class.** `StrategyStep.record_class` holds the record type
WDK lists that step's own search under; `assign_step_record_classes` fills it from the
site catalog and `validate_parameters` reports the class it resolved, so the push
addresses each step's search URL from the step's own class rather than from one value per
graph. `record_class_of` reads a step's class, taking a combine's from the steps it
consumes, and `sync_strategy_for_site` sets the strategy's class from the root through it. The
former leaf-first read is deleted.

The pin is `GenesByMolecularWeight` under a `GenesFromTranscripts` root on plasmodb.org
on 2026-08-30: the leaf is listed under `transcript` and the transform under `gene`, and
each 404s under the other record type - `There is no search "GenesByMolecularWeight"
associated with record type "GeneRecordClass"` and `There is no search
"GenesFromTranscripts" associated with record type "TranscriptRecordClass"`
([WDK-SEARCH-001](searches-and-answers.md)). The strategy is a gene strategy, and a class
read off its leaf would send both pushes to `transcript`.

### WDK-STRAT-005 - A 204 from `PUT .../step-tree` says the tree is well-formed, not that the strategy runs

- class: SILENT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/user/StrategyService.java#L222-L248
- anchor: src/veupathdb/wdk/strategy_api/strategies.py:update_strategy
- status: UNENFORCED
- reason: enforced in the consuming application, at apps/api/src/pathfinder/tests/unit/services/strategies/test_tree_push_is_not_a_checkpoint.py::TestTheReadIsWhatReportsValidity::test_an_accepted_tree_can_still_hold_an_invalid_step

`overwriteStepTreeAndSave` builds the replacement strategy at `ValidationLevel.NONE`. At
that level nothing about parameter values is examined. What the endpoint does check is
structural: the ids exist, the steps are yours, none belongs to another strategy, the
searches accept the inputs the tree gives them, there is a root, and everything is
reachable from it.

Everything else is deferred. An answer parameter pointing at a step of the wrong record
class is only rejected at `ValidationLevel.RUNNABLE`, in
[`AnswerParam.validateValue`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/AnswerParam.java#L110-L145),
which explicitly skips the record-type check below that level. So the request that
assembled a nonsensical strategy succeeds, and the failure arrives later, attached to
whichever step you happened to run.

**The success code is 204, not 200.** `replaceStepTree` is declared
`public void replaceStepTree(@PathParam(ID_PARAM) long stratId, JSONObject body)`, and a
JAX-RS resource method returning `void` produces an empty 204. A client asserting 200 on
this endpoint fails on a correct response.

The operational consequence: a successful tree push is not a checkpoint. The next thing
after it must be a read that carries validation - `GET .../strategies/{id}` validates at
`RUNNABLE` - or a run. Treating the 204 as confirmation is how a broken strategy gets
reported to a researcher as built.

Confirmed live on plasmodb.org and toxodb.org on 2026-08-10, as a side effect of the
[WDK-VALID-004](validation.md) experiment: a leaf was invalidated through
`PUT .../search-config?allowInvalid=true`, a combined step was then wired over it with
`PUT .../strategies/{id}/step-tree`, and the tree push returned **204** - accepting a
strategy whose parameters are invalid, which is this rule. The step then read
`isValid: false` at `RUNNABLE`.

### WDK-STRAT-006 - `A INTERSECT (B UNION C)` is not `(A INTERSECT B) UNION C`, and WDK accepts both

- class: SILENT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/request/strategy/StrategyRequest.java#L177-L201
- anchor: src/veupathdb/domain/strategy/operational_spec.py:build_step_tree
- status: ENFORCED by tests/unit/domain/strategy/test_operational_spec.py::TestNestedBranchesReachWdk::test_the_union_stays_on_the_secondary_input

`treeToSteps` recurses into `secondaryInput` exactly as it does into `primaryInput`, so a
branch hanging off the second input is as ordinary to WDK as one hanging off the first.
Both shapes above are well-formed trees, both are accepted, and neither produces a warning.
Only one of them answers the question the researcher asked.

This was measured on live WDK, not reasoned about. The same eight-criterion drug-target
question returned **3 genes** under the nested shape and **2** under the flattened one, and
the gene the fold dropped was reachable through only one of the two unioned evidence
sources. The per-set counts, the gene, and the full account are in
the structure-is-a-tree decision (`pathfinder: docs/knowledge/decisions/structure-is-a-tree.md`), which owns those
figures.

The failure mode is entirely a client-side one, and it has a single cause: modelling a
strategy as an ordered list of operations. A list can only be folded, a fold can only
produce a left spine, and a left spine cannot put a branch on a secondary input. Anything
that accepts criteria plus operators and assembles them itself is this bug waiting for a
strategy with two evidence sources for one property.

### WDK-STRAT-007 - A step that belongs to another strategy cannot be placed in this tree

- class: HARD
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/request/strategy/StrategyRequest.java#L162-L172
- anchor: src/veupathdb/wdk/strategy_api/strategies.py:get_duplicated_step_tree
- status: ENFORCED by tests/unit/wdk/test_strategy_api_strategies.py::test_wdk_strat_007_reusing_a_branch_asks_for_new_ids

`treeToSteps` looks up every id in the incoming tree and rejects any step already carrying
a different strategy id: `belongs to strategy <id> so cannot be assigned to`. The same
constraint is re-checked when the strategy is built, in
[`buildSteps`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/Strategy.java#L275-L288),
alongside owner and project matching.

So a step belongs to at most one strategy, ever, and two strategies cannot share a subtree.
Reusing work means copying it: `POST .../strategies/{id}/duplicated-step-tree` returns a
tree of newly created step ids, which is the only supported way to graft one strategy's
branch into another. Note what that costs - the copies are independent, so a later edit to
the source does not reach them.

# WDK-STEP - the step
