---
type: Rules
title: Filter rules
description: Three filter mechanisms in three places plus a fourth name that is none of them, and the four counts a report returns of which only one honours a view filter.
tags: [wdk-alignment, rules, filters, view-filters, column-filters, counts]
generated: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
status: stable
---

# WDK-FILTER - three mechanisms, one word

### WDK-FILTER-001 - `filter` parameters, `filters` and `columnFilters` are three unrelated mechanisms in three places

- class: CONTRACT
- upstream: https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkModel.ts#L377-L385
- anchor: src/veupathdb/wdk/wdk_models.py:WDKSearchConfig
- status: UNENFORCED
- reason: enforced in the consuming application, at veupathdb-mcp/tests/unit/catalog/test_param_adapters_from_search.py::test_wdk_filter_001_the_search_config_keeps_them_apart

A `filter` parameter is an entry in `searchConfig.parameters` whose stable value
is a JSON object of faceted clauses; its format is
[specified in the header comment of the class that parses it](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/FilterParamNewStableValue.java#L29-L62),
and its parameter document carries an `ontology` array and a `values` map that
no other type has
([`FilterParamNewFormatter`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/param/FilterParamNewFormatter.java#L20-L49)).
It is a parameter, so it validates like one and it is part of the step's
identity.

`searchConfig.filters` is a list of `{name, value, disabled?}` naming filters the
model declares on the question, published by
[`QuestionFormatter.getFiltersJson`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/QuestionFormatter.java#L110-L118)
with an `isViewOnly` flag.

`searchConfig.columnFilters` is `{column: {tool: config}}`, parsed against the
question rather than the record class
([`ColumnFilterServiceFormat.parse`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/request/filter/ColumnFilterServiceFormat.java#L11-L37)).

Live on 2026-08-10, all three appear on the same searches. Two different
denominators, because they come from two different endpoints: **the 320
plasmodb.org transcript searches whose own document resolves** carry 26 `filter`
parameters between them, while **all 325 listed by
`GET /record-types/transcript/searches`** advertise exactly three named filters
each. Parameters need the per-search document and five of those return 500;
`filters` are in the list response, so nothing is missing from that count.
Nothing in either name tells you which
mechanism a given "filter" belongs to, which is exactly why this is a
`CONTRACT` rule - a client that models one "filter" concept will put the value
in the wrong place and get a 400 at best.

The fourth name, `viewFilters`, is in none of these places -
[WDK-FILTER-003](#wdk-filter-003---viewfilters-belongs-at-the-top-level-of-a-report-body-and-is-rejected-outright-inside-searchconfig).

### WDK-FILTER-002 - An always-applied filter is injected into every step and cannot be removed by omitting it

- class: SILENT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/filter/FilterDefinition.java#L120-L136
- anchor: src/veupathdb/wdk/strategy_api/filters.py:set_step_filter
- status: ENFORCED by tests/unit/wdk/test_strategy_api_steps.py::TestAWriteKeepsTheFiltersItDidNotSet::test_a_disabled_filter_stays_disabled

`FilterDefinition` carries an `isAlwaysApplied` flag onto every `Filter` it
builds, documented on the interface as
[true when the filter will always be applied to steps whose questions include it](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/filter/Filter.java#L60-L73).

Confirmed on plasmodb.org and toxodb.org on 2026-08-10 with an anonymous guest
session. `POST /users/current/steps` for `GenesByMolecularWeight` with a
`searchConfig` containing only `parameters` returns a step whose `searchConfig`
holds
`filters: [{"name": "matched_transcript_filter_array", "disabled": false, "value": {"values": ["Y"]}}]`.
`PUT .../search-config` with `filters: []` answers **204** and the filter is
present again on the next read. Setting `disabled: true` is the only way to
turn it off, and that is stored.

Two consequences. A read-modify-write of `searchConfig` that drops `filters`
does not remove the filter, so the 204 is not confirmation of anything. And a
step you never filtered is filtered: on this step the always-applied filter is
worth 4 transcripts on plasmodb.org and 8 on toxodb.org, a difference small
enough to look like rounding and large enough to be a different answer.

`isFiltered` will not warn you either. It reports whether any option differs
from its default, [skipping disabled and default-valued options](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/answer/spec/FilterOptionList.java#L106-L114),
so the step above reports `isFiltered: false` while carrying the filter.

### WDK-FILTER-003 - `viewFilters` belongs at the top level of a report body, and is rejected outright inside `searchConfig`

- class: HARD
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/request/answer/AnswerSpecServiceFormat.java#L85-L98
- anchor: src/veupathdb/wdk/_analyses.py:update_step_filters
- status: UNENFORCED
- reason: enforced in the consuming application, at apps/api/src/pathfinder/tests/unit/platform/test_wdk_analyses.py::TestTheFiltersAreReplaced::test_view_filters_are_not_sent
`parseViewFilters` reads `viewFilters` from whatever object it is handed, and it
is handed the **request body** - by
[`AnswerService.parseAnswerRequest`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/AnswerService.java#L282-L304)
for the search-report endpoint and by
[`StepService.createCustomReportAnswer`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/user/StepService.java#L239-L282)
for the step-report endpoint. So it is a sibling of `searchConfig` and
`reportConfig`, never a member of either.

Inside `searchConfig` it is dead twice over. The parser
[does not read it](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/request/answer/AnswerSpecServiceFormat.java#L49-L83)
and the formatter
[does not write it](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/request/answer/AnswerSpecServiceFormat.java#L100-L117),
both lines commented out with the same dated note - the finding recorded in
[steps and search config](../model/steps-and-search-config.md). The deployed
sites add a third refusal ahead of both: on 2026-08-10,
`PUT /users/current/steps/{id}/search-config` carrying `viewFilters` returned
**400** from the JSON-schema filter on plasmodb.org and on toxodb.org, reading
`object instance has properties which are not allowed by the schema:
["viewFilters"]`. So this key is not ignored in `searchConfig`; it fails the
whole request.

At the top level it is real and it is validated. Live on both sites and on both
report endpoints, an unknown view-filter name is a **422** and a `viewFilters`
that is a JSON object rather than an array is a **400**
(`JSONObject["viewFilters"] is not a JSONArray`). A `STANDARD` filter is legal
there: [`containerSupports`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/filter/Filter.java#L17-L32)
lets the view-filter slot take either kind, and only the reverse is an error.

**PathFinder's `FilterMixin` is named for the wrong mechanism.**
`list_step_filters` and `set_step_filter` say `viewFilters` throughout, and the
client methods behind them are `get_step_view_filters` and
`update_step_view_filters`. What they actually read and write is
`searchConfig.filters`, which is correct behaviour under a set of names that
describe something else - and something that would 400 if it were attempted.

### WDK-FILTER-004 - `totalCount` ignores view filters; only `viewTotalCount` matches the rows you got

- class: SILENT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/report/reporter/DefaultJsonReporter.java#L123-L143
- anchor: src/veupathdb/wdk/strategy_api/reports.py:get_step_count
- status: ENFORCED by tests/unit/wdk/test_wdk_models.py::TestTheCountMatchesTheRecords::test_the_view_filtered_display_count_wins
`getMetaData` emits four counts and computes two of them from a
[clone of the answer with the view filters stripped out](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/report/reporter/DefaultJsonReporter.java#L145-L152).
`totalCount` and `displayTotalCount` are the unfiltered pair; `viewTotalCount`
and `displayViewTotalCount` are the filtered pair. The records themselves are
filtered - `getIdSql`
[applies `filters`, then view filters, then column filters](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/answer/AnswerValue.java#L678-L705).

Measured on a guest step on 2026-08-10, `GenesByMolecularWeight` with one
organism leaf:

| | `totalCount` | `viewTotalCount` |
|---|---|---|
| plasmodb, `filters` `["Y","N"]`, no view filter | 2407 | 2407 |
| plasmodb, same + view filter `["N"]` | **2407** | **4** |
| toxodb, `filters` `["Y","N"]`, no view filter | 3386 | 3386 |
| toxodb, same + view filter `["N"]` | **3386** | **8** |

The sharpest form of it: with the step's own `filters` set to `["N"]` (4 rows on
plasmodb, 8 on toxodb) and a view filter of `["Y"]`, the request returned
`totalCount: 4` and an **empty `records` array**. The two halves of one response
disagree, and nothing flags it.

So a client that paginates on `totalCount` reads past the end of a view-filtered
result, and a client that shows `totalCount` to a researcher shows the count of
the thing that was filtered away. Read `viewTotalCount` whenever the request
carried a view filter; the two are equal when it did not, so reading it always
costs nothing.

### WDK-FILTER-005 - `estimatedSize` is `displayTotalCount`, not `totalCount`, and it lives on the strategy rather than the step

- class: SILENT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/user/StepService.java#L239-L282
- anchor: src/veupathdb/wdk/wdk_models.py:WDKStep
- status: ENFORCED by tests/unit/wdk/test_wdk_models.py::TestAbsenceIsNotZero::test_all_absent_raises_rather_than_reporting_zero
Running a step report writes `getResultSizeFactory().getDisplayResultSize()` back
onto the step, and `getDisplayResultSize`
[delegates to the record class's own result-size plugin](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/answer/ResultSizeFactory.java#L44-L58)
rather than counting the id query. `DefaultJsonReporter` publishes the same two
numbers side by side as `totalCount` and `displayTotalCount`.

They are not equal. Measured on 2026-08-10 on the guest step above, with the
step's `filters` at their always-applied default:

| Site | `totalCount` | `displayTotalCount` | strategy `estimatedSize` |
|---|---|---|---|
| plasmodb | 2403 | 2365 | **2365** |
| toxodb | 3378 | 3336 | **3336** |

`estimatedSize` matched `displayTotalCount` in every configuration measured, and
it does track the step: setting `filters` to `["N"]` moved all of
`totalCount`, `displayTotalCount` and `estimatedSize` to 4 on plasmodb and 8 on
toxodb, and a `columnFilters` entry that matched nothing moved all three to 0.

**A view filter moved none of them, and the pinned source predicts that it
should.** The write is unconditional - `createCustomReportAnswer` sets
`estimatedSize` from `result.getFirst().getResultSizeFactory().getDisplayResultSize()`
on every run - and `result.getFirst()` is
[the answer value built from the spec carrying the request's view filters](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/AnswerService.java#L411-L428),
so that expression ought to yield the same number the reporter published as
`displayViewTotalCount`. Measured on both sites on 2026-08-10, a report whose
`displayViewTotalCount` was **4** (8 on toxodb) left `estimatedSize` at 2365
(3336) while `lastRunTime` advanced to the second of that request - **so the
write ran and chose the unfiltered number.**

The tempting explanation is wrong. "The display-size plugin ignores view
filters, so 2365 was correct" would dissolve this - except `displayViewTotalCount`
is that same `getDisplayResultSize()` call on the view-filtered answer, and it
reads 4. The plugin honours view filters. So the same method on what the source
says is the same object yielded 4 and 2365 within one request.

**Where the answer would live, since it is not in pinned WDK source.** Two
places, both outside what this bundle can falsify:

- **The record class's result-size plugin.**
  [`getDisplayResultSize`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/answer/ResultSizeFactory.java#L44-L58)
  delegates to `recordClass.getResultSizePlugin()`, which for the transcript
  record class is site model configuration rather than WDK code - the same reason
  no enrichment column name is knowable from this repository
  ([WDK-ANS-007](searches-and-answers.md)). If that plugin caches per answer
  spec, or keys a cache in a way that collapses the two specs, it would produce
  exactly this.
- **Ordering.** `updateStep` runs at
  [line 275, before the method returns the streaming response](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/user/StepService.java#L239-L282),
  and the body is
  [a stream the container consumes afterwards](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/AnswerService.java#L411-L428).
  So `estimatedSize` is computed *before* the reporter has written a byte, and
  `displayViewTotalCount` *during*. Whatever state the reporter establishes in
  between is a candidate.

Both are leads, not findings. What the rule asserts is only what was measured: a
view filter does not change `estimatedSize` on these deployments. The gap is
recorded in [sources.md](../sources.md). That measurement is
[WDK-FILTER-004](#wdk-filter-004---totalcount-ignores-view-filters-only-viewtotalcount-matches-the-rows-you-got)
seen from the step side.

So `estimatedSize` is a correct number about a different population from the one
`totalCount` counts, and quoting one where the other was measured is a 38-record
error on this step. Neither is wrong; they are answers to different questions.

**And `estimatedSize` is not where a client looks for it.** On both sites,
`GET /users/current/steps/{id}` omitted the key entirely for a step whose
containing strategy reported `estimatedSize: 2365` for that same step seconds
later. The step formatter
[returns null - and so omits the key - when the value is negative or unset](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/StepFormatter.java#L118-L121),
so absence is not zero and is not staleness - see
[WDK-STEP-001](strategies-and-steps.md). Read the size from the strategy.

### WDK-FILTER-006 - A column advertising the `byValue` tool is not a column a step will accept it on

- class: HARD
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/request/filter/ColumnFilterServiceFormat.java#L11-L37
- anchor: src/veupathdb/wdk/wdk_models.py:WDKSearchConfig
- status: ENFORCED by tests/unit/wdk/test_strategy_api_records.py::test_wdk_filter_006_a_refusal_is_not_treated_as_a_broken_request

The parse method's contract lists four rejection reasons and two of them are
about the column: unknown, and not filterable.

**"Against the question, not the record class" is inference, not pinned fact.**
What the pinned source shows is a `Question` parameter whose javadoc says it is
used "to provide context when validating the input configuration", and a
delegation to `FilterConfigParser`, whose body is not cited here. The
question-scoping is the reading that fits the live 400 below; a per-column model
flag that the record-type formatter reports differently would fit it too. The
rule's operative half - **do not trust the record-type document** - rests on the
measurement, which is unambiguous either way.

Live on 2026-08-10, `GET /record-types/transcript` on plasmodb.org advertises
`tools.filters: ["byValue"]` on 3,021 attributes, `primary_key`,
`gene_source_id` and `source_id` among them. Applying any of those three to a
`GenesByMolecularWeight` step is a **400**:
`column "primary_key" does not have have configured filter "byValue"` - the
doubled word is verbatim. `gene_product` on the same step is accepted with 204,
and a `pattern` matching nothing drove every count to 0 and flipped
`isFiltered` to true. Identical results on toxodb.org.

The config itself takes exactly one of three shapes -
[`values`, `range`, or `pattern`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/columntool/byvalue/filter/ByValueConfigStyle.java#L14-L21)
- chosen by which key is present, so sending two of them is ambiguous rather
than additive.

**The status of the refusal has since moved, and the refusal has not.** Re-run
on plasmodb.org on 2026-08-22 against a freshly created
`GenesByMolecularWeight` step, `primary_key`, `gene_source_id`, `source_id` and
`organism` all answer **500 `Internal Error`** rather than the 400 above, while
`gene_product` still answers 200. So the message naming the column is gone and
the diagnosis is now indistinguishable from a WDK bug, which makes the operative
half of this rule stronger rather than weaker. The nightly lane asserts a
refusal and records the status, so the next move is dated.

The operational consequence is that the record-type document cannot be used to
decide what a step will take. Try it against the step, and treat a refusal here
as "not on this search" rather than as a malformed request. One cost follows
from the change: a 500 is retried three times before
`get_column_distribution` returns an empty result, where the 400 was refused at
once.
