---
type: Reference
title: Dependent parameters and vocabularies
description: What a vocabulary is, why a tree vocabulary has a fake root and counts only leaves, and why a dependent parameter's value is meaningless without the parent it was read under.
tags: [wdk-alignment, parameters, vocabularies, dependent-params, model]
generated: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
status: stable
---

Every permalink below is pinned to the sha recorded in [sources.md](../sources.md).

# A vocabulary is a list of triples, or a tree

Both vocabulary types come out of the same formatter method.
[`EnumParamFormatter.addEnumFields`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/param/EnumParamFormatter.java#L25-L50)
writes `displayType`, `maxSelectedCount`, `minSelectedCount` and `vocabulary`,
and the flat form is an array of three-element rows - `term`, `display`,
`parent` - built from `getFullVocab()` with an explicit three-column assertion.
`wdk-client` types it as
[`[VocabTerm, VocabDisplay, null][]`](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkModel.ts#L103-L109)
and that type is wrong: the third column is the parent term, populated whenever
the vocabulary is nested, and the client's own unused `VocabParent` alias says so
([WDK-VOCAB-007](../rules/parameters-and-vocabularies.md)). `GenesByOrthologPattern`
sends 903 rows with parents on plasmodb.org and toxodb.org.

**The term is what goes on the wire; the display is what goes on the screen.**
The two differ often enough to matter - `bq_operator` sends `MINUS` and displays
`LEFT_MINUS` ([steps and search config](steps-and-search-config.md)), and a
typeahead vocabulary such as `GenesByInterproDomain.domain_typeahead` carries
terms like `PF00069 : Pkinase` where the accession is only a prefix of the term.

A `treeBox` parameter gets a different serialization from a subclass.
[`TreeBoxEnumParamFormatter`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/param/TreeBoxEnumParamFormatter.java#L23-L51)
adds `countOnlyLeaves` and `depthExpanded` and replaces the array with a single
[`TreeBoxVocabNode`](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkModel.ts#L111-L124)
- `{data: {term, display}, children: [...]}`, recursively.

Two of its details are traps.

**The root may be synthetic.** `getVocabularyObject` uses the single real root
only when there is exactly one and it has children; otherwise it wraps every
root in a new node whose term is the literal string `@@fake@@`. Live on
plasmodb.org, `GenesByMolecularWeight.organism` has two real roots
(`Haemoproteidae`, `Plasmodiidae`) so the tree it returns is rooted at
`@@fake@@` - a term that is not in the vocabulary and that WDK will not accept
([WDK-VOCAB-001](../rules/parameters-and-vocabularies.md)).

**`depthExpanded` and `countOnlyLeaves` are not both presentation.**
`depthExpanded` is how far the client should open the tree. `countOnlyLeaves` is
a validation rule: it decides whether `minSelectedCount` and `maxSelectedCount`
count leaves only or leaves and branches, which
[the accessor says outright](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/AbstractEnumParam.java#L267-L284).
`getNumSelected`
[builds the tree, marks the selected terms on it, and returns the selected
leaves](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/AbstractEnumParam.java#L457-L467)
when `countOnlyLeaves` is set. A branch term therefore contributes **zero** to
the count, so selecting only branches is indistinguishable from selecting
nothing ([WDK-VOCAB-002](../rules/parameters-and-vocabularies.md)). That is the
platform-side reason this client expands parent terms to leaves before pushing,
and the reason its tree widget had to learn the same rule
(`pathfinder: docs/knowledge/decisions/parent-term-is-a-selection.md`).

The counts themselves are computed, not stored.
[`getMinSelectedCount`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/AbstractEnumParam.java#L214-L230)
falls back to `allowEmpty ? 0 : 1`, and
[`getMaxSelectedCount`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/AbstractEnumParam.java#L241-L256)
returns `1` for any single-pick parameter whatever the model said. So
`maxSelectedCount: -1` on a multi-pick parameter means unlimited, and there is
no configuration under which a single-pick parameter takes two terms.

# `dependentParams` points the other way from what it depends on

WDK holds the edge twice under two nearly identical names.
[`AbstractDependentParam`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/AbstractDependentParam.java#L70-L90)
holds `dependedParams` - the parameters **this** one needs - and resolving them
[registers the back-link on each parent](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/AbstractDependentParam.java#L125-L153)
via `addDependentParam`. Only the back-link is published:
`ParamFormatter.getBaseJson` writes `dependentParams` from
[`getDependentParams()`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/Param.java#L875-L894).

So a parameter's `dependentParams` is the list of parameters that go stale when
**it** changes, not the list it depends on. Live on plasmodb.org,
`GenesByInterproDomain.domain_database` has
`dependentParams: ["domain_typeahead"]` and `domain_typeahead` has `[]` - the
one that actually depends on something reports nothing
([WDK-VOCAB-003](../rules/parameters-and-vocabularies.md)). To find a
parameter's parents you must invert the whole map.

The backing field is a `HashSet`, so the array's order carries no information.
Live on plasmodb.org the same three-way dependency appears as
`["hard_floor", "samples_fc_ref_generic", "samples_fc_comp_generic"]` on one
microarray search and as
`["samples_fc_comp_generic", "samples_fc_ref_generic", "hard_floor"]` on
another. Dependencies are common rather than exotic: **245 of the 320 transcript
searches that resolve on plasmodb.org declare at least one.**

Declared is not the same as refreshed.
[`Param.isStale`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/Param.java#L896-L918)
returns `false` by default and is overridden per class: an enum parameter
[always goes stale](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/AbstractEnumParam.java#L706-L710),
while a `FilterParamNew` goes stale
[only when the changed parameter feeds its ontology or background query](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/FilterParamNew.java#L1012-L1030).
`getStaleDependentParams` walks that transitively.

# The refresh endpoint, and what it does not return

`POST /record-types/{rc}/searches/{name}/refreshed-dependent-params` takes
`{"contextParamValues": {...}, "changedParam": {"name": ..., "value": ...}}`.
[`QuestionService.getQuestionChange`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/QuestionService.java#L233-L280)
requires `changedParam`, builds a spec with
`FILL_PARAM_IF_MISSING_OR_INVALID`, and then checks whether the changed value
survived that build. If it did not, the value was invalid and the request is a
422 rather than a silently corrected 200.

**The response is a JSON array of parameters, and it holds only the stale
ones.** The service takes `changedParam.getStaleDependentParams()` and
[tells the formatter to emit those and nothing else](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/QuestionService.java#L295-L302),
under a comment explaining that the other parameters' values may have been
changed by the fill and are therefore not to be trusted. Live on plasmodb.org,
changing `profileset_generic` on the DeRisi percentile search returns exactly
`["samples_percentile_generic"]`; changing `any_or_all`, which has no
dependents, returns **200 with `[]`**. An empty array is not an error and is not
a refreshed vocabulary; it means there was nothing to refresh
([WDK-VOCAB-005](../rules/parameters-and-vocabularies.md)).

The request shape is checked in two places with two different outcomes, verified
live on plasmodb.org on 2026-08-10:

| Request | Result |
|---|---|
| no `changedParam` | 400 `'changedParam' property is required at this endpoint` |
| no `contextParamValues` | 400 `JSONObject["contextParamValues"] not found.` |
| `changedParam.value` not a JSON string | 400 `JSONObject["value"] is not a string` |
| `changedParam.value` not in the vocabulary | 422 `The passed changed param value 'Nope' is invalid.` |
| `changedParam.name` not a parameter | 422 `Parameter 'nope' is not in container ...` |

The 400s come from
[`ParamValueSetRequest.parse`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/request/ParamValueSetRequest.java#L32-L64),
which reads `value` with `getString`, so a client that sends a multi-pick array
as a real JSON array here - rather than as the stringified array the wire
format demands - gets a 400 rather than a wrong vocabulary.

**The refresh endpoint can refuse a value the run endpoint accepts.** Measured on
plasmodb.org against `GenesByOrthologPattern`: a refresh carrying
`organism: ["Plasmodium falciparum 3D7"]` together with a `profile_pattern`
answered **500**, while running the search with the same values answered 200 with
a large `totalCount`. Narrowing a vocabulary is an enrichment, not a
precondition. A client that loses the narrowing loses vocabulary precision and
must not lose the search, which is the platform-side reason the consuming
application gives that operation one owner and one fallback policy
(`pathfinder: docs/knowledge/decisions/contextualizing-params-is-an-enrichment.md`).

# The ordering constraint, which is the whole point

A dependent parameter's vocabulary is a function of its parents' values. Read it
under the wrong parent and you get a real vocabulary for a different question,
and nothing in the response says so.

Measured on plasmodb.org on 2026-08-10 through the refresh endpoint, on
`GenesByMicroarraypfal3D7_microarrayExpression_Derisi_TimeSeries_RSRCPercentile`:

| `profileset_generic` | leaves in `samples_percentile_generic` |
|---|---|
| DeRisi HB3 Smoothed (the search default) | 46 |
| DeRisi 3D7 Smoothed | 46 |
| DeRisi Dd2 Smoothed | 45 |

HB3 and 3D7 share **44 of those terms**. The two that are only in HB3 are
`47 Hour` and `48 Hour`; the two only in 3D7 are `23 Hour` and `29 Hour`. So a
value taken from one list and applied under the other is accepted 96 percent of
the time and means a different experiment every time
([WDK-VOCAB-004](../rules/parameters-and-vocabularies.md)). Confirmed by
sending both combinations to the revise endpoint: `20 Hour` is `isValid: true`
under HB3 and under 3D7 alike, while `47 Hour` under 3D7 is an error.

Reading a dependent vocabulary with no context returns the search's
**defaults** rather than the bound parent's list, so a criterion bound to one
strain is shown another strain's time points and nothing reports the swap. What
a consumer does about that is its own
(`pathfinder: docs/knowledge/wdk/pathfinder/`).
The `INTERPRO` vocabulary is 5,405 terms on plasmodb.org and 6,592 on
toxodb.org, against thousands and 2,916 for `PFAM` - re-measured on both sites on
2026-08-10, and the plasmodb figure matches the one recorded when that bug was
diagnosed.

The operational rule is an ordering, not a validation: bind parents first, read
the dependent vocabulary under those exact parents, and re-read it whenever a
parent changes. There is no request that will tell you afterwards that you got
it wrong.
