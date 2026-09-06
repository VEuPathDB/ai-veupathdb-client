---
type: Reference
title: Steps and search configuration
description: What a step is, the three kinds WDK distinguishes and how it tells them apart, what is inside searchConfig, and the four states a step can be in.
tags: [wdk-alignment, steps, search-config, boolean, model]
generated: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
status: stable
---

Every permalink below is pinned to the sha recorded in [sources.md](../sources.md).

# A step is a search plus the values it was given

[`StepFormatter.getStepJson`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/StepFormatter.java#L70-L99)
builds the whole of it. The fields that carry meaning rather than presentation are few:

| Field | Note |
|---|---|
| `id` | Assigned by WDK at `POST /users/{userId}/steps`. The only stable handle. |
| `searchName` | Which question. Cannot be changed after creation - see below. |
| `searchConfig` | Every value the search was given. |
| `recordClassName` | The record class **url segment**, for example `transcript` - [not its full name](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/StepFormatter.java#L88). This distinction has teeth; see the boolean section. |
| `strategyId` | The containing strategy, or `null`. Null means orphan, and orphan is a state with rules. |
| `estimatedSize` | Last known result count. [Omitted entirely when negative or unset](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/StepFormatter.java#L118-L121), so absent and zero are different things. |
| `validation` | Level, validity, and errors by parameter key. |

Everything else the formatter emits is presentation, and a smaller set of it is writable.
[`updateStepMeta`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/request/strategy/StepRequestParser.java#L113-L137)
reads exactly four keys off the patch body and ignores anything else:

| `PATCH /users/{userId}/steps/{stepId}` accepts | `JsonKeys` constant |
|---|---|
| `customName` | `CUSTOM_NAME` |
| `expanded` | [`IS_EXPANDED`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/core/api/JsonKeys.java#L200-L201) - the constant's name is not the wire key |
| `expandedName` | `EXPANDED_NAME` |
| `displayPreferences` | `DISPLAY_PREFERENCES` |

`displayName` and `shortDisplayName` are **not** in that set. They are derived and
output-only; sending them changes nothing and reports nothing. The split is otherwise
clean: PATCH for how a step looks, PUT `/search-config` for what it computes, and nothing
at all for which search it runs.

Changing the search means deleting the step. `getReplacementAnswerSpec` says so in the
error it throws when the existing step's question cannot be resolved:
[`changing question names is not currently supported. You must delete this step`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/request/strategy/StepRequestParser.java#L139-L155).

# `searchConfig` is four things, not the six the type says

One class both parses and serializes it, so its two methods are the definition:

```
searchConfig: {
  parameters:    { [paramName]: string },   // required
  filters:       [{ name, value, disabled? }],
  columnFilters: { [column]: { [tool]: any } },
  wdkWeight:     number
}
```

`parameters` values are strings, always, whatever the parameter's declared type - WDK calls
this the stable value.

`wdk-client`'s
[`SearchConfig`](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkModel.ts#L377-L390)
declares two more, `viewFilters` and `legacyFilterName`, and
[`StepFormatter`'s class comment](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/StepFormatter.java#L39-L46)
lists both too - though it calls the second one `legacyFilter`, while
[`JsonKeys.LEGACY_FILTER_NAME`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/core/api/JsonKeys.java#L189-L191)
and the client both say `legacyFilterName`. The disagreement is moot: at the pinned sha
neither field is real under either name.
[`AnswerSpecServiceFormat.parse`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/request/answer/AnswerSpecServiceFormat.java#L49-L83)
reads neither spelling - the key appears only in that method's own doc comment - and its
view-filter line is commented out with a dated note,
`As of 8/20/19 we do not parse view filters with other answer spec properties`.
[`format`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/request/answer/AnswerSpecServiceFormat.java#L108-L117)
emits the same four keys and carries the mirror-image commented-out line. So at this sha
nothing on the write path would act on a `viewFilters` inside a `searchConfig`, and
`viewFilters` read back is always absent - a good reminder that the reference client is
evidence of intent, not of behavior.

**On the deployed sites it is not ignored, it is refused.** On 2026-08-10 a
`PUT /users/current/steps/{id}/search-config` carrying the key returned **400** from the
JSON-schema filter on both plasmodb.org and toxodb.org - `object instance has properties
which are not allowed by the schema: ["viewFilters"]` - so the request never reaches the
parser above. Both facts are true and they are about different layers; the measurement is
in [WDK-FILTER-003](../rules/filters.md). This is a second instance of
[the pin-versus-deployment gap](../sources.md), and a sharper one than the first, because
here the deployment is stricter than the pin rather than merely different. An earlier
version of this paragraph said "silently ignored" without qualification, which was true of
the source and false of every site a researcher will ever use.

View filters are per-request instead. Both report endpoints call
[`parseViewFilters`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/request/answer/AnswerSpecServiceFormat.java#L85-L98)
on the *request body*, not on the step, and apply them to a spec built for that one call.
That is the distinction the two names were always for: `filters` change what the step is and
what it counts, view filters change only what this response shows.
[`Step.isFiltered`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/Step.java#L632-L649)
counts `filters` and `columnFilters` and has nothing to say about view filters, because at
this sha a step never holds any.

**The entry in `parameters` that is not yours is the answer parameter.** A step's inputs
live in this same flat map, as step ids in string form, and PUT `/search-config` refuses to
change them:
[`assertAnswerParamsUnmodified`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/request/strategy/StepRequestParser.java#L157-L170)
compares every answer parameter in the incoming spec against the step's current value and
throws `Changes to answer param values are not allowed.` on any difference, with a comment
saying outright that the strategy service owns the tree. So `parameters` is one map with two
owners: you own the search's own parameters, and the step tree owns the answer parameters
([WDK-STEP-003](../rules/strategies-and-steps.md)).

That is also why a read-modify-write of `searchConfig` is safe only if you keep the answer
parameters exactly as you found them. Dropping them changes them.

# Three kinds of step, told apart by counting

WDK has no `kind` field. A step's kind is the number of answer parameters its search
declares, and every part of the system derives it that way rather than storing it.

| Answer parameters | Kind | Example on plasmodb.org |
|---|---|---|
| 0 | leaf search | `GenesByMolecularWeight` |
| 1 | transform | `GenesByOrthologs`, `TranscriptsFromGenes` |
| 2 | combined | `boolean_question_TranscriptRecordClasses_TranscriptRecordClass`, `GenesBySpanLogic` |

[`Strategy.getLeafAndTransformStepCount`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/Strategy.java#L449-L465)
is the clearest statement of it: a step counts as leaf-or-transform when its question's
`getAnswerParamCount() < 2`, and a step whose question does not resolve is counted too, on
the reasoning that an unknown search is more likely a leaf than a boolean.

**Primary and secondary are ordinals, not names.**
[`getPrimaryInputStepParam`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/Step.java#L651-L667)
returns the answer parameter at index 0 of the question's answer parameter list and
`getSecondaryInputStepParam` returns index 1;
[`findAnswerParamsStep`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/Step.java#L440-L472)
notes that a maximum of two are supported. There is no naming convention to rely on and
no field that says which is which. A client that wants to know a step's input parameter
names must ask the search for its parameters and take them in order.

Transform inputs are typed and they cross record classes. A search declares
`allowedPrimaryInputRecordClassNames` and `allowedSecondaryInputRecordClassNames`, and the
transcript searches on plasmodb.org and toxodb.org agree exactly on which searches have
them - 7 with a primary input, 2 with a secondary, verified on both sites on 2026-08-10:

| Search | Accepts as primary | Accepts as secondary |
|---|---|---|
| `TranscriptsFromGenes` | `gene` | - |
| `GenesByOrthologs` | `transcript` | - |
| `GenesByPathwaysTransform` | `pathway` | - |
| `GenesByCompoundsTransform` | `compound` | - |
| `GenesByWeightFilter` | `transcript` | - |
| `boolean_question_TranscriptRecordClasses_TranscriptRecordClass` | `transcript` | `transcript` |
| `GenesBySpanLogic` | `transcript`, `snp`, `popsetSequence`, `genomic-segment`, and `snp-chip` on plasmodb only | the same set |

`TranscriptsFromGenes` takes genes and produces transcripts; `GenesByPathwaysTransform`
takes pathways. So "everything in a gene strategy is a gene" is false, and the record class
that matters at a join is the one the *input step* produces, which the search must list.

# The boolean triple

A combined step is not a special object. It is an ordinary step whose search is the
per-record-class boolean question WDK generates, and whose three parameters are two
operands and an operator.
[`BooleanQuery`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/BooleanQuery.java#L85-L110)
builds them:

```
bq_left_op_<RecordClass full name, dots replaced by underscores>   answer parameter
bq_right_op_<same>                                                 answer parameter
bq_operator                                                        enum parameter
```

Verified live on 2026-08-10, `GET /record-types/transcript/searches/boolean_question_TranscriptRecordClasses_TranscriptRecordClass?expandParams=true`
returns exactly those three names on plasmodb.org and on toxodb.org.

**The two operand names embed the record class full name; the operator name does not.**
`bq_operator` is a
[bare constant](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/BooleanQuery.java#L57-L61)
shared by every record class. And the full name in the operand names is not the
`recordClassName` a step reports: that field is the url segment, `transcript`, while the
operand is `bq_left_op_TranscriptRecordClasses_TranscriptRecordClass`. The mapping between
the two is site model data, not a string transformation, so the names must be read off the
search ([WDK-STEP-006](../rules/strategies-and-steps.md)).

Both operands are declared against the *same* record class - `prepareOperand` is called
twice with the one `recordClass` argument and adds a single
[`RecordClassReference`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/BooleanQuery.java#L149-L170)
to each - and the class comment states the consequence:
[the operands have to be of the same record class, and so is the result](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/BooleanQuery.java#L31-L36).
`GenesBySpanLogic` is the counter-example that proves it is a property of the boolean
question rather than of two-input steps in general: it accepts five record classes on
either side, because colocation genuinely relates different things. That asymmetry is why
PathFinder treats colocation as outside the boolean set, for reasons recorded in
the boolean-operator decision (`pathfinder: docs/knowledge/decisions/boolean-operator-is-a-type.md`).

**The value stored in `bq_operator` is the term, not the display name.**
[`prepareOperatorParam`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/BooleanQuery.java#L172-L197)
builds the vocabulary from
[`BooleanOperator`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/BooleanOperator.java#L14-L21)
by setting each item's display to the enum constant name and its term to the base operator,
and those differ for four of the six:

| Term - what you send | Display |
|---|---|
| `UNION` | `UNION` |
| `INTERSECT` | `INTERSECT` |
| `MINUS` | `LEFT_MINUS` |
| `RMINUS` | `RIGHT_MINUS` |
| `LONLY` | `LEFT_ONLY` |
| `RONLY` | `RIGHT_ONLY` |

The live vocabulary on plasmodb.org matches, and the default is `INTERSECT`. Sending
`LEFT_MINUS` is sending a display label where a term belongs.

# The four states of a step, and which of them can run

A step's state is not stored either. It is the combination of whether it has a strategy and
whether it validates, and it is worth naming because three of the four states answer
requests differently.

**Unattached.** Created by `POST /users/{userId}/steps` and belonging to no strategy. Every
answer parameter must be the null value at creation - `newStepFromJson`
[rejects a non-null one](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/request/strategy/StepRequestParser.java#L81-L87)
with `Answer Params in new steps must have the null value (empty string).` So a combined
step is created empty and wired afterwards, by a tree
([WDK-STEP-002](../rules/strategies-and-steps.md)).

**In a strategy.** Reached by naming the step in a tree. Now the invariant flips: `Step`'s
constructor asserts
[null inputs if and only if no strategy](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/Step.java#L392-L402),
so a step inside a strategy must have *every* answer parameter filled. A combine with one
input is not a degraded combine, it is an error
([WDK-STEP-004](../rules/strategies-and-steps.md)).

**Orphaned.** Removed from a tree by a replacement that did not mention it. It keeps its id
and its parameters, loses its strategy and its inputs, and loses the ability to run: both
report endpoints check
[`if (!step.getStrategy().isPresent())`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/user/StepService.java#L253-L259)
and answer 422 `is not part of a strategy, so cannot run`, before any validation of the step
itself. Counting a step therefore requires a strategy around it, whether or not the count is
what the strategy is for ([WDK-STEP-005](../rules/strategies-and-steps.md)).

**Deleted.** `DELETE /users/{userId}/steps/{stepId}` sets a flag; the row survives. It only
works on an orphan:
[a step that is part of a strategy is a 409](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/user/StepService.java#L148-L169),
`Steps that are part of strategies cannot be deleted.` Deletion is therefore two calls in a
fixed order - replace the tree without the step, then delete it - and doing them the other
way round is the 409 ([WDK-STEP-007](../rules/strategies-and-steps.md)).

Validity is orthogonal to all four and is reported per step in `validation`. PathFinder
derives its own step status from wiring, WDK id and validation together rather than storing
one, for reasons recorded in
the step-status decision (`pathfinder: docs/knowledge/decisions/step-status-is-derived.md`); a WDK push rejection
is likewise carried per step rather than raised, as recorded in
the local-edit decision (`pathfinder: docs/knowledge/decisions/local-edit-is-the-truth.md`).
