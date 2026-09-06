---
type: Reference
title: The three filter mechanisms
description: Filter parameters, step filters and column filters live in three different places and mean three different things - and view filters, the fourth name, are none of them.
tags: [wdk-alignment, filters, view-filters, column-filters, model]
generated: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
status: stable
---

Every permalink below is pinned to the sha recorded in [sources.md](../sources.md).

# Four names, three places, and they are not variants of one idea

"Filter" names four different things in WDK, three of which can appear in one
request. Getting them confused does not usually produce an error; it produces a
number.

| Name | Where it goes | What it is |
|---|---|---|
| `filter` **parameter** | `searchConfig.parameters["<name>"]` | a parameter whose value is a set of faceted clauses |
| `filters` | `searchConfig.filters` | named, model-declared filters applied to the answer, part of the step |
| `columnFilters` | `searchConfig.columnFilters` | per-attribute predicates, also part of the step |
| `viewFilters` | the **top level** of a report request body | applied to this one response |

The first three are in
[`SearchConfig`](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkModel.ts#L377-L385)
alongside `viewFilters`, which is the source of most of the confusion. The
fourth is not in `searchConfig` at all - see the last section.

# A `filter` parameter is a parameter

`FilterParamNew` is an ordinary entry in `parameters` whose stable value is a
JSON object holding faceted clauses. The class's own header comment
[is the format specification](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/FilterParamNewStableValue.java#L29-L62):
a `filters` array of `{field, value}` objects where `value` is either a
`{min, max}` object or a list of strings, plus optional `includeUnknown`,
`isRange` and `type`. Note that the comment's sample writes `includeUnknowns`
while the constant beside it is `includeUnknown`; the constant is what is read.

Its parameter document is the largest of any type.
[`FilterParamNewFormatter`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/param/FilterParamNewFormatter.java#L20-L49)
adds an `ontology` array - one entry per filterable field, with `term`,
`parent`, `type`, `isRange`, `precision` and `units` - and a `values` map from
field to the values seen. So the vocabulary of a filter parameter is
two-dimensional: which field, and then which value within it.

Live on 2026-08-10, 26 filter parameters appear across plasmodb.org's transcript
searches and 10 across toxodb.org's, all with `initialDisplayValue` of
`{"filters":[]}` - an empty clause list, which means include everything rather
than exclude everything.

The important thing about this mechanism is what it is not: it is a parameter,
so it participates in parameter validation, in `dependentParams`, and in the
step's identity. Changing it changes what the step *is*.

# `filters` is a set of model-declared filters on the answer

These are not parameters. A record class or question declares them, and a step
records which are applied with what value:
`[{name, value, disabled?}]`. Each is a `Filter` in the model, carrying
[a `FilterType` of `STANDARD` or `VIEW_ONLY`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/filter/Filter.java#L17-L32)
and an `isAlwaysApplied` flag,
[both set from the XML definition](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/filter/FilterDefinition.java#L120-L136).
A search document advertises the ones it has:
[`QuestionFormatter.getFiltersJson`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/QuestionFormatter.java#L110-L118)
emits `name`, `displayName`, `description` and `isViewOnly`.

Live on 2026-08-10, every search in `GET /record-types/transcript/searches`
advertises exactly three - `organismFilter`, `genesByPathway`, and
`matched_transcript_filter_array` (or `gene_boolean_filter_array` on the boolean
question) - on **all 325** searches plasmodb.org lists and **all 234** on
toxodb.org. The count is the full listing rather than the 320 whose own document
resolves, because `filters` are carried in the list response and need no
per-search fetch.

**All 975 of those entries, and all 702 on toxodb.org, report `isViewOnly:
false`.** So on these two deployments the view-only kind of filter is declared by
the platform and used by nothing a transcript search exposes.

**An always-applied filter arrives whether you asked for it or not.** Creating a
step on plasmodb.org with `searchConfig` carrying only `parameters` returns a
step whose `searchConfig.filters` is
`[{"name": "matched_transcript_filter_array", "disabled": false, "value": {"values": ["Y"]}}]`.
Sending `filters: []` back is a 204 and changes nothing - the filter is there
again on the next read
([WDK-FILTER-002](../rules/filters.md)). Same on toxodb.org. Removing such a
filter means setting `disabled: true`, not omitting it.

That one filter is worth 4 transcripts on plasmodb.org and 8 on toxodb.org
against the `GenesByMolecularWeight` step measured here, which is exactly the
size of difference nobody notices.

`Step.isFiltered` reflects `filters` and `columnFilters` and nothing else, and
it is not "has filters" but "differs from the default":
[the check skips disabled options and options still at their default value](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/answer/spec/FilterOptionList.java#L106-L114).
Live, the step above reports `isFiltered: false` while carrying its
always-applied filter, and flips to `true` the moment the value is changed away
from `["Y"]`.

# `columnFilters` is per-attribute and its availability is not what the record type says

`columnFilters` is `{column: {tool: config}}`. The only tool on these
deployments is `byValue`, and its config takes exactly one of three shapes -
[`values`, `range`, or `pattern`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/columntool/byvalue/filter/ByValueConfigStyle.java#L14-L21)
- selected by which key is present. It is parsed against the **question**, not
the record class:
[`ColumnFilterServiceFormat.parse`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/request/filter/ColumnFilterServiceFormat.java#L11-L37)
documents four rejection reasons, among them "referencing columns that are not
filterable".

That distinction has teeth. `GET /record-types/transcript` on plasmodb.org lists
`byValue` under `tools.filters` for 3,021 attributes including `primary_key`,
`gene_source_id` and `source_id`. Applying any of those three to a
`GenesByMolecularWeight` step is a **400** reading
`column "primary_key" does not have have configured filter "byValue"` (the
doubled "have" is verbatim). `gene_product` on the same step is accepted, drives
the count to 0 for a pattern that matches nothing, and flips `isFiltered` to
true. Identical on toxodb.org
([WDK-FILTER-006](../rules/filters.md)).

# View filters are real, are validated, and are not in `searchConfig`

This is the mechanism that is documented in two places and implemented in a
third.

`wdk-client`'s `SearchConfig` declares `viewFilters`, and
[`StepFormatter`'s class comment](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/StepFormatter.java#L39-L46)
lists it too. Neither is true of the wire.
[`AnswerSpecServiceFormat.parse`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/request/answer/AnswerSpecServiceFormat.java#L49-L83)
has the view-filter line commented out with a dated note, and
[`format`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/request/answer/AnswerSpecServiceFormat.java#L100-L117)
carries the mirror image, so a step never holds one - the finding recorded in
[steps and search config](steps-and-search-config.md).

The deployed sites go further than that: they do not ignore the key, they
**reject** it. `PUT /users/{id}/steps/{id}/search-config` with `viewFilters` in
the body is a 400 from the JSON-schema filter on both plasmodb.org and
toxodb.org, reading
`object instance has properties which are not allowed by the schema:
["viewFilters"]` ([WDK-FILTER-003](../rules/filters.md)). So the key is
unusable in `searchConfig` in both directions and by two independent
mechanisms.

Where it *is* read is the top level of a report request body, beside
`searchConfig` and `reportConfig` rather than inside either.
[`parseViewFilters`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/request/answer/AnswerSpecServiceFormat.java#L85-L98)
is called on the request body by
[`AnswerService.parseAnswerRequest`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/AnswerService.java#L282-L304)
and by
[`StepService.createCustomReportAnswer`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/user/StepService.java#L239-L282),
which layers them onto the step's own spec for that one call. And they are
validated: live on both sites and on both report endpoints, an unknown view
filter name is a **422**, and a `viewFilters` that is an object rather than an
array is a 400.

A `STANDARD` filter is legal in the view-filter slot -
[`containerSupports`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/filter/Filter.java#L17-L32)
lets the `VIEW_ONLY` container take either kind, and
[`buildValidated`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/answer/spec/FilterOptionList.java#L68-L87)
only errors the other way round. That is what makes the next section
measurable at all.

# Which of them moves which number

`AnswerValue.getIdSql` applies all three to the same SQL, in order:
[`filters`, then view filters, then column filters](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/answer/AnswerValue.java#L678-L705).
So all three change the records. They do **not** all change the same counts,
because the reporter deliberately computes the metadata twice.
[`DefaultJsonReporter.getMetaData`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/report/reporter/DefaultJsonReporter.java#L123-L143)
emits four counts, two from a
[clone of the answer with the view filters stripped](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/report/reporter/DefaultJsonReporter.java#L145-L152):

| `meta` key | View filters applied? | Which size |
|---|---|---|
| `totalCount` | no | result size |
| `displayTotalCount` | no | record class's display size |
| `viewTotalCount` | yes | result size |
| `displayViewTotalCount` | yes | record class's display size |

Measured on one guest step per site on 2026-08-10, `GenesByMolecularWeight`
with `organism` set to one leaf and the molecular-weight bounds at their
defaults:

| Configuration | `totalCount` | `displayTotalCount` | `viewTotalCount` | `displayViewTotalCount` | strategy `estimatedSize` |
|---|---|---|---|---|---|
| plasmodb, `filters` `["Y"]` | 2403 | 2365 | 2403 | 2365 | 2365 |
| plasmodb, `filters` `["Y","N"]` | 2407 | 2365 | 2407 | 2365 | 2365 |
| plasmodb, `filters` `["Y","N"]` + view filter `["N"]` | 2407 | 2365 | **4** | **4** | 2365 |
| plasmodb, `filters` `["N"]` | 4 | 4 | 4 | 4 | 4 |
| toxodb, `filters` `["Y"]` | 3378 | 3336 | 3378 | 3336 | 3336 |
| toxodb, `filters` `["Y","N"]` | 3386 | 3336 | 3386 | 3336 | 3336 |
| toxodb, `filters` `["Y","N"]` + view filter `["N"]` | 3386 | 3336 | **8** | **8** | 3336 |

Three things fall out of that table and each is a way to be wrong.

**`totalCount` ignores view filters.** In the third row the response carried two
records out of a possible four and announced 2407. Asked for three records, the
same request returned an empty `records` array while still reporting a total of
four in `totalCount` - the view filter had removed every row on the page
([WDK-FILTER-004](../rules/filters.md)). `viewTotalCount` is the count that
matches what came back.

**`estimatedSize` is `displayTotalCount`, not `totalCount`.** It matched
exactly in every row, on both sites, and it moved with `filters` and with
`columnFilters` but never with a view filter. The 2403-against-2365 gap is not
staleness: the record class's display size plugin is counting a different thing
from the id query ([WDK-FILTER-005](../rules/filters.md)).

That a view filter leaves it alone is the one result here with **no mechanism
behind it.** `createCustomReportAnswer` writes `estimatedSize` on every run from
`result.getFirst().getResultSizeFactory().getDisplayResultSize()`, and
`result.getFirst()` is the answer value built from the spec carrying the
request's view filters - so the number written ought to be the
`displayViewTotalCount` column, 4 rather than 2365. `lastRunTime` advanced on
each of these calls, so the write did happen and did choose the unfiltered
figure.

Note which explanation the fourth column rules **out**. The obvious candidate -
that the record class's display-size plugin simply ignores view filters, making
2365 the correct output of that expression - is false: `displayViewTotalCount`
is itself `getDisplayResultSize()` on the view-filtered answer, and it reads 4.
The plugin honours view filters. Two calls to the same method on what the source
says is the same object returned 4 and 2365 in the same request.

Where the answer would live, since it is not in pinned WDK source: see
[WDK-FILTER-005](../rules/filters.md), which names the two leads.

**`estimatedSize` is not on the step where you would look for it.** On both
sites `GET /users/current/steps/{id}` omitted the key entirely for a step whose
containing strategy reported `estimatedSize: 2365` for that same step in the
same minute. Read it from the strategy.
