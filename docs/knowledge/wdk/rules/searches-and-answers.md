---
type: Rules
title: Search and answer rules
description: What a search is bound to, how it is addressed, and the several ways a report request comes back 200 with the wrong thing in it.
tags: [wdk-alignment, rules, searches, answers, reports, attributes, enrichment]
generated: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
status: stable
---

# WDK-SEARCH - the search and the record class it belongs to

### WDK-ANS-001 - The unpersisted report endpoint requires both `searchConfig` and `reportConfig`; the step report endpoint requires only `reportConfig`

- class: HARD
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/AnswerService.java#L282-L304
- anchor: src/veupathdb/wdk/strategy_api/base.py:_standard_report
- status: UNENFORCED
- reason: enforced in the consuming application, at veupathdb-mcp/tests/unit/wdk/test_step_results_reports.py::TestTheStepReportEndpointTakesOnlyAReportConfig::test_the_report_config_is_the_whole_body
There are two ways to run a reporter and they take different bodies.

`POST /record-types/{rc}/searches/{name}/reports/{reporter}` runs a search that no step
holds. `parseAnswerRequest` rejects a body that lacks either key before doing anything else:
`Request body must not be null and must contain 'searchConfig' and 'reportConfig'
properties.` The answer spec comes from `searchConfig`, so there is nowhere else for the
parameter values to come from.

`POST /users/{userId}/steps/{stepId}/reports/{reporter}` runs a step, so the answer spec is
already on the step. [`createCustomReportAnswer`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/user/StepService.java#L239-L282)
still demands a body - `A request body is required at this endpoint.` - and still reads
`reportConfig` out of it, but takes no `searchConfig`. It also refuses a step with no
strategy first ([WDK-STEP-005](strategies-and-steps.md)).

Confirmed live on plasmodb.org on 2026-08-10: omitting `reportConfig` from the search-report
body returns **400**, and the body is not WDK's usual error JSON but a JSON-schema report,
`object has missing required properties (["reportConfig"])`. So this particular refusal
happens in the schema filter ahead of the code cited above, and a client matching on WDK's
error shape will not recognize it.

The step-report half is source-only: read off the pinned sha, not confirmed against a running
site. See [the pin-versus-deployment note](../sources.md).

`reportConfig: {}` satisfies both endpoints. It is also a trap - see the next rule.

### WDK-ANS-002 - A `reportConfig` that omits `attributes` returns every record with no attributes, and returns 200

- class: SILENT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/report/config/AnswerDetailsFactory.java#L165-L191
- anchor: src/veupathdb/wdk/strategy_api/reports.py:get_step_records
- status: UNENFORCED
- reason: enforced in the consuming application, at veupathdb-mcp/tests/unit/wdk/test_step_results_reports.py::TestAttributesAreOnlyWhatWeAskFor::test_asking_for_none_sends_no_attributes_key

`parseAttributeJson` ends with `// if unspecified, do not include any attributes; user could
just be requesting tables` and returns an empty map. Tables behave the same way. The
[method's own javadoc](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/report/config/AnswerDetailsFactory.java#L47-L58)
says it outright - `If attributes or tables properties are omitted, none are returned` - so
this is deliberate, not a bug. It is still the single easiest way to get a plausible empty
table in front of a researcher.

Confirmed live on 2026-08-10 on both plasmodb.org and toxodb.org: `reportConfig: {}` against
`GenesByMolecularWeight` returns **200** with the right number of records, each
`"attributes":{}`.

The asymmetry is the dangerous part. A **wrong** attribute name is loud - live on toxodb.org,
`attributes: ["not_a_real_attribute"]` is a 400 reading `Could not configure reporter
'standard' with passed formatConfig. Attribute 'not_a_real_attribute' is not available for
question 'GeneQuestions.GenesByMolecularWeight'`. A **missing** `attributes` key is silent.
Getting the name wrong is safer than forgetting to ask.

Note what does not happen: there is no fallback to the search's default attributes.
`createDefault` does use `question.getSummaryAttributeFieldMap()`, but
[it is only reached when the whole config is null](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/report/config/AnswerDetailsFactory.java#L91-L97),
and [WDK-ANS-001](#wdk-ans-001---the-unpersisted-report-endpoint-requires-both-searchconfig-and-reportconfig-the-step-report-endpoint-requires-only-reportconfig)
means you cannot omit the key. The search document's `defaultAttributes` is a suggestion to
the client, and the client has to act on it. If you want the defaults, send them.

One caller relies on this deliberately -
`veupathdb-mcp: src/veupathdb_mcp/wdk/step_preview.py` retries
with no attributes to get an id-only preview when a record class rejects the ones it asked for
- and
that works because record identity is not an attribute (see
[WDK-ANS-004](#wdk-ans-004---recordclassname-means-the-full-name-inside-records-and-the-url-segment-inside-meta)).

### WDK-ANS-003 - `numRecords: 0` returns no records; only a negative value means all

- class: SILENT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/report/config/AnswerDetailsFactory.java#L101-L111
- anchor: src/veupathdb/wdk/strategy_api/reports.py:get_step_count
- status: UNENFORCED
- reason: enforced in the consuming application, at veupathdb-mcp/tests/unit/wdk/test_step_results_reports.py::TestACountAsksForZeroRecords::test_the_count_page_is_exactly_zero_records

The factory reads `numRecords` and replaces it with
[`ALL_RECORDS`, which is `-1`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/report/config/AnswerDetails.java#L13-L32),
only when the value is `< 0`. Zero survives, and
[`getConfiguredAnswer`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/report/reporter/AnswerDetailsReporter.java#L96-L106)
then computes `endIndex = startIndex + 0 - 1`, one short of the start, which is an empty
page.

**The javadoc says the opposite** - `Zero or negative values for numRecords will return all
records` - so the comment and the code disagree by one value, and it is the value a client
is most likely to send by accident.

Confirmed live on 2026-08-10. `pagination: {offset: 0, numRecords: 0}` returns 200 with
`records: []` and `responseCount: 0` while `totalCount` is 19 on plasmodb.org and 43 on
toxodb.org. So the counts in `meta` are right and the rows are gone, which is exactly the
shape that looks like "the search found nothing" to anything reading `records`.

The useful corollary: a zero-record report is the cheap way to ask WDK for a count, because
`meta.totalCount` is computed regardless. PathFinder's `get_step_count` does this.

The other half of the rule is the default. `AnswerDetails` starts at `_numRecords =
ALL_RECORDS`, so a `reportConfig` with no `pagination` key streams the **entire** result -
on a 300,000-gene answer, all of it. Pagination is opt-in and its absence is not a small
page.

### WDK-ANS-004 - `recordClassName` means the full name inside `records[]` and the url segment inside `meta`

- class: SILENT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/report/util/RecordFormatter.java#L41-L52
- anchor: src/veupathdb/wdk/wdk_models.py:WDKRecordInstance
- status: ENFORCED by tests/unit/wdk/test_wdk_models.py::TestTheTwoRecordClassNames::test_one_is_not_the_other

`RecordFormatter.getRecordJson` writes `JsonKeys.RECORD_CLASS_NAME` from
`record.getRecordClass().getFullName()`.
[`DefaultJsonReporter.getMetaData`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/report/reporter/DefaultJsonReporter.java#L123-L143)
writes the same key from `question.getRecordClass().getUrlSegment()`. Both appear in one
response body.

Confirmed live on 2026-08-10 on both plasmodb.org and toxodb.org, in a single standard
report: `records[0].recordClassName` is `TranscriptRecordClasses.TranscriptRecordClass` and
`meta.recordClassName` is `transcript`.

So a comparison between the two is always false, and code that reads "the record class" out
of a report has to know which half of the document it read. There is no string
transformation between the forms ([WDK-STEP-006](strategies-and-steps.md)); the pairing is
site model data.

The rest of the record shape is worth stating alongside it, because it is the part that
survives [WDK-ANS-002](#wdk-ans-002---a-reportconfig-that-omits-attributes-returns-every-record-with-no-attributes-and-returns-200):
identity is not an attribute. `id` is an array of `{name, value}` pairs, one per primary-key
column in `getPrimaryKeyDefinition().getColumnRefs()` order - three of them for transcripts,
live: `gene_source_id`, `source_id`, `project_id` - and `displayName` comes from the id
attribute. Those are present even when `attributes` is `{}`.

### WDK-ANS-005 - `pagination` and `sorting` are honored by the `standard` reporter and discarded by the others

- class: SILENT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/report/reporter/StandardReporter.java#L52-L66
- anchor: src/veupathdb/wdk/strategy_api/reports.py:get_step_records
- status: UNENFORCED
- reason: enforced in the consuming application, at veupathdb-mcp/tests/unit/wdk/test_step_results_reports.py::TestOnlyTheJsonReporterHonoursThePage::test_records_go_through_the_standard_reporter

Two reporter base classes take the same `reportConfig` and treat it differently.

`AnswerDetailsReporter` - which `standard` is, via `DefaultJsonReporter` - applies the
config, [cloning the answer with the requested paging and setting the requested
sort](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/report/reporter/AnswerDetailsReporter.java#L96-L106).

`StandardReporter` - the tabular and full-record family - calls `standardizeAnswerValue` in
its `setAnswerValue` override, which sets the page to `1, UNBOUNDED_END_PAGE_INDEX` under
the comment `always return all records; user cannot select a subset of records`, and clears
the sorting map under `disable custom sorting`. It does this before any config is parsed, so
there is nothing a `reportConfig` can do about it.

The name collision is the trap. **The reporter named `standard` is not `StandardReporter`.**
`standard` is
[`DefaultJsonReporter.RESERVED_NAME`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/report/reporter/DefaultJsonReporter.java#L49-L58),
and the class called `StandardReporter` is the one that ignores your pagination.

Confirmed live on plasmodb.org on 2026-08-10 with `pagination: {offset: 0, numRecords: 1}`
on a two-record answer: `standard` returned 1 record; `fullRecord` returned 2; `json`
returned `"count":2`. Same request body, same search, three reporters, two of them ignoring
the page size.

The operational consequence: paging is not a way to keep a download small. If you need a
subset from a non-JSON reporter you have to make the *answer* smaller, with filters or a
narrower search, because the reporter will stream whatever the step returns.

### WDK-ANS-006 - A reporter's `scopes` control where a client should offer it, not whether WDK will run it

- class: CONTRACT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/AnswerService.java#L448-L461
- anchor: src/veupathdb/wdk/wdk_models.py:WDKReporter
- status: ENFORCED by tests/unit/wdk/test_call_sites.py::test_wdk_ans_006_nothing_but_the_model_reads_scopes

`getConfiguredReporter` checks one thing before dispatching: whether the name is a key in
`question.getReporterMap()`. It never reads `scopes`. Scope is only ever consulted when the
record type document is *rendered* -
[`getAnswerFormatsJson`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/RecordClassFormatter.java#L89-L106)
takes a `FieldScope` and reports each reporter's
[`getScopesList()`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/report/ReporterRef.java#L134-L153),
a comma-separated string split into a list, documented as the scopes the reporter is
*visible* in.

Confirmed live on plasmodb.org on 2026-08-10. `GET /record-types/transcript` lists
`standard` with `scopes: ["results"]`, `gff3` with `["results", "record"]`, and `fullRecord`
and `json` with `[]`. Posting to `.../reports/fullRecord` and `.../reports/json` both
returned **200** with data. An empty `scopes` array is not a closed door.

Two things follow. A client picking reporters to show a user should filter on `scopes`,
because that is what it is for. A client picking a reporter to *call* should not, because
the emptiness of the list says nothing about the call. And `scopes` is a per-deployment
model attribute, so the same reporter can be scoped differently on two sites - which makes
it doubly wrong to treat as availability.

`FieldScope` itself is the same idea applied to fields:
[three values](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/record/FieldScope.java#L16-L46)
built from the `internal` and `inReportMaker` flags of
[`ScopedField`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/record/ScopedField.java#L9-L19),
surfaced on attributes and tables as `isDisplayable` and `isInReport`. Those are advice to
the client too.

### WDK-ANS-007 - Enrichment column names belong to the analysis plugin, not to WDK, and the word plugin does not use the key you expect

- class: SILENT
- upstream: https://github.com/VEuPathDB/ApiCommonWebsite/blob/830bb57fe07fc2e4dd37b6ea2e3baae0eaee5bee/Model/src/main/java/org/apidb/apicommon/model/stepanalysis/WordEnrichmentPlugin.java#L169-L182
- anchor: src/veupathdb/wdk/strategy_api/analyses.py:list_analysis_types
- status: UNENFORCED
- reason: enforced in the consuming application, at veupathdb-mcp/tests/unit/wdk/enrichment/test_parser.py::test_word_rows_map_word_to_id_and_pathway_name_to_description

**The word plugin's description column is `pathwayName`.** `WordEnrichmentPlugin.ResultRow.toJson`
writes it literally:

```java
json.put("word", _word);
json.put("pathwayName", _descrip);
```

There is no `descrip` key on the wire. The field is called `_descrip` in Java and the pathway
plugin's key name is emitted for it. Any client reading `descrip` gets nothing, silently,
forever, which is what makes this a `SILENT` rule rather than a note.

The reason the column is *labelled* correctly while being *keyed* wrongly is that the manifest
and the data rows share one serializer. `headerRow` is itself a `ResultRow`, constructed as
[`new ResultRow("Word", "Description", ...)`](https://github.com/VEuPathDB/ApiCommonWebsite/blob/830bb57fe07fc2e4dd37b6ea2e3baae0eaee5bee/Model/src/main/java/org/apidb/apicommon/model/stepanalysis/WordEnrichmentPlugin.java#L33-L34)
and put through the same `toJson`. So `"Description"` arrives under the key `pathwayName`, and
the mismatch is structural rather than a typo in one place.

**Nothing else in the body is WDK's either.** WDK runs the plugin and
[returns `result.get().getResultJson()`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/user/StepAnalysisInstanceService.java#L272-L284)
with four keys added - `contextHash`, `accessToken`, `downloadUrl`, `propertiesUrl`. The
envelope around the rows, including where `resultData` sits, is
[the plugin's view model](https://github.com/VEuPathDB/ApiCommonWebsite/blob/830bb57fe07fc2e4dd37b6ea2e3baae0eaee5bee/Model/src/main/java/org/apidb/apicommon/model/stepanalysis/WordEnrichmentPlugin.java#L118-L128).
So no column name here is knowable from the WDK repository, which is why
[sources.md](../sources.md) pins a fourth one.

The three plugins, each `toJson` read at the pinned sha:

| Plugin | Identity columns | Shared statistics |
|---|---|---|
| [`go-enrichment`](https://github.com/VEuPathDB/ApiCommonWebsite/blob/830bb57fe07fc2e4dd37b6ea2e3baae0eaee5bee/Model/src/main/java/org/apidb/apicommon/model/stepanalysis/GoEnrichmentPlugin.java#L326-L339) | `goId`, `goTerm` | `bgdGenes`, `resultGenes`, `percentInResult`, `foldEnrich`, `oddsRatio`, `pValue`, `benjamini`, `bonferroni` |
| [`pathway-enrichment`](https://github.com/VEuPathDB/ApiCommonWebsite/blob/830bb57fe07fc2e4dd37b6ea2e3baae0eaee5bee/Model/src/main/java/org/apidb/apicommon/model/stepanalysis/PathwaysEnrichmentPlugin.java#L327-L341) | `pathwayId`, `pathwayName`, `pathwaySource` | same eight |
| [`word-enrichment`](https://github.com/VEuPathDB/ApiCommonWebsite/blob/830bb57fe07fc2e4dd37b6ea2e3baae0eaee5bee/Model/src/main/java/org/apidb/apicommon/model/stepanalysis/WordEnrichmentPlugin.java#L169-L182) | `word`, `pathwayName` | same eight |

Every field of every `ResultRow` is
[declared `String`](https://github.com/VEuPathDB/ApiCommonWebsite/blob/830bb57fe07fc2e4dd37b6ea2e3baae0eaee5bee/Model/src/main/java/org/apidb/apicommon/model/stepanalysis/WordEnrichmentPlugin.java#L132-L145),
so every value on the wire is a JSON string - p-values included, in scientific notation.

**Confirmed live**, independently of the source above, on 2026-08-10 on plasmodb.org and
toxodb.org, each through an anonymous **guest** session (`GET /service/users/current`, no
credential) running all three plugins over a `GenesByMolecularWeight` step. The key sets
matched this table exactly on both sites, and every value was a string.

**The word plugin can no longer be read live.** On 2026-09-04 a `word-enrichment`
analysis over the same kind of step validates `RUNNABLE` on both sites and its result
status settles on `ERROR`, so the table's word row now rests on the source alone
([transport-quirks](../rest/transport-quirks.md)). GO and pathway still run.

`resultGenes` is not one type. GO and pathway rows return an HTML anchor whose text is the
count and whose href carries the gene ids; word rows return a bare count string (`"2054"`).
A parser must handle both.

**The response carries its own manifest, so nothing needs hardcoding.** `headerRow` and
`headerDescription` are objects keyed by exactly the `resultData` keys, giving each column a
display label and a long description. Read the manifest instead of a table like the one
above, and a plugin that renames a column degrades to an unrecognized column rather than an
empty one.

**`percentInResult` is result genes over background genes, and no column carries the size of
the analyzed set.** The plugin names the quantity in its own manifest:
[`HEADER_ROW`](https://github.com/VEuPathDB/ApiCommonWebsite/blob/830bb57fe07fc2e4dd37b6ea2e3baae0eaee5bee/Model/src/main/java/org/apidb/apicommon/model/stepanalysis/GoEnrichmentPlugin.java#L50-L51)
labels it `Percent of bkgd Genes in your result`, and
[`COLUMN_HELP`](https://github.com/VEuPathDB/ApiCommonWebsite/blob/830bb57fe07fc2e4dd37b6ea2e3baae0eaee5bee/Model/src/main/java/org/apidb/apicommon/model/stepanalysis/GoEnrichmentPlugin.java#L53-L64)
reads `Of the genes in the background with this term, the percent that are present in your
result`. So `percentInResult = resultGenes / bgdGenes * 100`, and
`resultGenes * 100 / percentInResult` returns `bgdGenes`, not the input size.

Measured on plasmodb.org: a 46-gene set's top GO:BP row was `resultGenes` 46,
`bgdGenes` 217, and `46 * 100 / 217 = 21.2`, which is the value on the wire. A client that
inverts the percentage to recover "genes analyzed" prints 217, a term's genome-wide count,
under a label that promises the researcher's own set size.

There is no result-level total anywhere in the envelope, so the analyzed size comes from the
caller: the step's own count, or the size of the gene list that built the step.

### WDK-ANS-008 - An attribute value is a string, an object, or null, and `attributeFormat: text` does not strip HTML

- class: SILENT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/report/util/RecordFormatter.java#L110-L140
- anchor: src/veupathdb/wdk/wdk_models.py:WDKRecordInstance
- status: ENFORCED by tests/unit/wdk/test_wdk_models.py::TestComparingAnAttributeToText::test_a_link_value_compares_by_its_display_text

`getAttributeValueJson` branches on the attribute's Java class before it branches on the
requested format. A `LinkAttributeValue` becomes a `{url, displayText}` **object** under
`DISPLAY`, or `JSONObject.NULL` when the display text is empty, and a bare url string under
`TEXT`. A `TextAttributeValue` returns its display under `DISPLAY` and its value otherwise.
Everything else returns the value, or `JSONObject.NULL` when it is empty.

So `records[].attributes` is `{string | object | null}` and never uniformly typed. Confirmed
live on 2026-08-10 in a single record on plasmodb.org: `primary_key` a string, `ec_numbers`
`null`, `gene_entrez_link` the object
`{"displayText": "812594,812594", "url": "http://www.ncbi.nlm.nih.gov/gene/?term=812594,812594"}`.
The same object shape appeared on toxodb.org. A client that types attribute values as
strings gets a dict where it expected text, on the attributes most worth showing a
researcher.

**`TEXT` is not a plain-text mode.** It swaps display for value and collapses links to urls;
it strips nothing. Markup survives it whenever the markup *is* the stored value. Live on
plasmodb.org under `attributeFormat: "text"`, `organism` does lose its `<i>` wrapper - display
and value differ there - while `orthomcl_link` still comes back as a raw
`<a href="..." target="_blank">OG6_532925</a>`. Reaching for `TEXT` to get parseable output
gets you fewer surprises, not none.

`null` is likewise not absent. The key is present with a JSON null, so a lookup succeeds and
returns nothing, which is a different failure from a missing attribute
([WDK-ANS-002](#wdk-ans-002---a-reportconfig-that-omits-attributes-returns-every-record-with-no-attributes-and-returns-200)).

### WDK-ANS-009 - The `aiExpression` reporter reads a cache by default and generates only when asked, and asking spends the whole deployment's daily budget

- class: CONTRACT
- upstream: https://github.com/VEuPathDB/ApiCommonWebsite/blob/18c54ba811ae1dd12125ab4483a3251b19a1a639/Model/src/main/java/org/apidb/apicommon/model/report/ai/SingleGeneAiExpressionReporter.java#L74-L106
- anchor: src/veupathdb/wdk/ai_expression.py:AiExpressionReportConfig
- status: ENFORCED by tests/unit/wdk/test_ai_expression.py::TestTheRequestCanNeverAskForGeneration::test_a_config_that_asks_for_generation_is_refused

`configure` reads `populateIfNotPresent` with `optBoolean(key, false)`, so an absent key
reads the cache. `true` calls `cache.populateSummary`, which runs Claude over every
experiment of the gene and then over their summaries. The spend is capped per deployment,
not per user:
[`DailyCostMonitor`](https://github.com/VEuPathDB/ApiCommonWebsite/blob/18c54ba811ae1dd12125ab4483a3251b19a1a639/Model/src/main/java/org/apidb/apicommon/model/report/ai/expression/DailyCostMonitor.java#L32-L38)
reads `MAX_DAILY_AI_EXPRESSION_DOLLAR_COST` from the WDK model properties and
`isCostExceeded` compares one accumulated dollar figure, held in a `DirectoryLock`-guarded
file, against it. When that figure is over the cap and the request asked to generate, the
reporter throws `WdkServiceTemporarilyUnavailableException` before it writes a byte, so
the feature answers 503 for everyone on that deployment until the date rolls over. A
client with no reason to generate must never send `true`.

The reporter is registered on the gene record class, not the transcript one
([`geneRecord.xml:158`](https://github.com/VEuPathDB/ApiCommonModel/blob/ef7c5199c0aa6fcf535ffbd2806c39b00d5886b1/Model/lib/wdk/model/records/geneRecord.xml#L158-L160)),
so the path segment is `gene`. Its `scopes` attribute is empty, which by
[WDK-ANS-006](#wdk-ans-006---a-reporters-scopes-control-where-a-client-should-offer-it-not-whether-wdk-will-run-it)
keeps it out of the UI menu and does not stop WDK running it.

`primaryKeys` needs **both** primary key columns. The gene record class declares
`source_id` and a `project_id` that is excluded only on UniDB
([`geneRecord.xml:78-82`](https://github.com/VEuPathDB/ApiCommonModel/blob/ef7c5199c0aa6fcf535ffbd2806c39b00d5886b1/Model/lib/wdk/model/records/geneRecord.xml#L78-L82)),
so every site PathFinder serves needs `"<sourceId>,<projectId>"`. Measured on 2026-09-04:
`"PF3D7_1133400"` alone returns **422** with
`RecordClass 'GeneRecordClasses.GeneRecordClass' PK requires exactly 2 values [ source_id, project_id ]`,
and `"PF3D7_1133400,PlasmoDB"` returns **200**. The same call anonymously returns **401**
`Valid API Key required for this endpoint`; the deployment's service token and a registered
user's token both answer 200, so this is a user-independent read.

A cache miss is a 200, not a 404. The body is one object per record keyed by gene id, and
the entry carries `resultStatus` plus `numExperiments`, `numExperimentsComplete` and an
`experimentStatus` map; `expressionSummary` is present only for `resultStatus: "present"`.
Measured on 2026-09-04 on plasmodb, PF3D7_1133400 answered `"expired"` with 41 of 41
experiments `present`, and PF3D7_0709000 answered `"experiments_incomplete"` with 0 of 41.
A reader must treat every non-`present` status as "no summary to quote" rather than as an
error, because the status also goes stale when upstream changes model or prompt version.

### WDK-SEARCH-001 - A search belongs to exactly one record class, and asking for it under another is a 404

- class: HARD
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/AbstractWdkService.java#L359-L368
- anchor: src/veupathdb/wdk/_searches.py:get_search_details
- status: UNENFORCED
- reason: enforced in the consuming application, at veupathdb-mcp/tests/unit/catalog/test_discovery.py::test_wdk_search_001_the_catalog_binds_a_search_to_one_record_type

`getQuestionOrNotFound(RecordClass, String)` resolves the search by name and then compares
`question.getRecordClassName()` against the record class's **full name**. A mismatch throws
`NotFoundException` with `There is no search "<name>" associated with record type "<rc>"`.
The binding itself is not a service-layer convention:
[`Question`'s class comment](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/question/Question.java#L51-L62)
opens `A class representing a binding between a RecordClass and a Query`, and the field
holding it is a single `RecordClass`, resolved once from a single `recordClassRef`.

Confirmed live on 2026-08-10. `GET /record-types/organism/searches/GenesByMolecularWeight`
returns **404** with exactly
`There is no search "GenesByMolecularWeight" associated with record type "OrganismRecordClass"`
on plasmodb.org and on toxodb.org - the source string, verbatim, on both.

The practical consequence is that `/record-types/{rc}/searches/{name}` has no redundancy in
it. The record type in the path is not decoration and it is not a hint; supply the wrong one
and the search is simply not there. A client that caches "search X exists" without the record
type it exists under has cached half a fact.

Note which name the comparison uses. The check is against the record class **full name**
(`TranscriptRecordClasses.TranscriptRecordClass`) while the path segment is the **url
segment** (`transcript`), the same two-vocabulary split that bites in
[WDK-STEP-006](strategies-and-steps.md).

### WDK-SEARCH-002 - A search is addressed by its url segment only; its full two-part name is a 404, whatever the service's own comment says

- class: HARD
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/AbstractWdkService.java#L344-L349
- anchor: src/veupathdb/wdk/wdk_models.py:WDKSearch
- status: UNENFORCED
- reason: enforced in the consuming application, at veupathdb-mcp/tests/unit/catalog/test_discovery.py::test_wdk_search_002_the_request_path_carries_the_url_segment

A search carries two names and the response gives you both:
[`QuestionFormatter`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/QuestionFormatter.java#L66-L68)
emits `urlSegment` from `getName()` and `fullName` from `getFullName()`. Live on both sites
those are `GenesByMolecularWeight` and `GeneQuestions.GenesByMolecularWeight`.

Only the first one is a path segment. `getQuestionOrNotFound(String)` delegates to
`getQuestionByName`, and on 2026-08-10
`GET /record-types/transcript/searches/GeneQuestions.GenesByMolecularWeight` returned
**404** with `Resource 'search: GeneQuestions.GenesByMolecularWeight' does not exist.` on
plasmodb.org and on toxodb.org - which is `formatNotFound("search: " + questionUrlSegment)`
from the cited lines, so the failure is that lookup and not the record-class check.

**`QuestionService`'s class comment says the opposite.** Its
[first paragraph](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/QuestionService.java#L52-L60)
states that question name path params `can be either the configured question URL segment
... or the question's full, two-part name`. At this sha, against these two deployments,
they cannot. The rule is written from the behavior, not the comment, and the disagreement
is recorded rather than smoothed over because a client that trusted the comment would
build every URL wrong and only find out per-search.

What this does **not** say is that the full name is useless. It is the name a step's
`searchName` carries and the name error messages use
(`not available for question 'GeneQuestions.GenesByMolecularWeight'`, live on toxodb.org).
Two names, two jobs; the mapping between them is data, so keep both.

### WDK-SEARCH-003 - The set of searches is a property of the deployment, computed per request from that site's model

- class: CONTRACT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/QuestionService.java#L96-L105
- anchor: src/veupathdb/wdk/_searches.py:get_searches
- status: UNENFORCED
- reason: enforced in the consuming application, at veupathdb-mcp/tests/unit/catalog/test_discovery.py::test_wdk_search_003_two_sites_do_not_share_a_search_set

`getQuestions()` takes `model.getAllQuestions()` and filters it by the requested record
class's full name, every time. There is no per-site constant anywhere in the service layer:
the list is whatever XML that deployment loaded. So availability is a deployment fact, and
the endpoint is the only thing that knows it.

The measurement that makes this concrete is in [sources.md](../sources.md):
`record-types/transcript/searches` returned **325** searches on plasmodb.org and **234** on
toxodb.org on 2026-08-10, from the same platform build. A list hardcoded from one site is
wrong for the other by roughly a third.

This rule is `CONTRACT` rather than `HARD` because WDK does not punish a client for holding a
stale list - it just 404s on the entries that were never there, one search at a time, at the
moment the researcher runs the thing. Which is the worst time to find out.

The narrower trap: per-site variation is not only presence. `GenesBySpanLogic` accepts
`snp-chip` as an input record class on plasmodb.org and not on toxodb.org, so even a search
that exists on both can differ in what it will take.

### WDK-SEARCH-004 - Parameter groups are presentation; `paramNames` is the parameter list

- class: CONTRACT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/Group.java#L6-L16
- anchor: src/veupathdb/wdk/wdk_models.py:WDKParameterGroup
- status: UNENFORCED
- reason: enforced in the consuming application, at veupathdb-mcp/tests/unit/catalog/test_discovery.py::test_wdk_search_004_the_specs_come_from_the_parameter_list

`Group`'s class comment is unambiguous: a group is `only used to group Params together in
the question page for display/layout purpose`, and a param with no group is assigned to the
default `Empty` group. Its state is a name, four presentation fields - `displayName`,
`description`, `displayType`, `visible` - plus `_descriptions`, the per-project text list
that `excludeResources` collapses into `description`, and `_groupSet`, which only supplies
the prefix in `getFullName`. Nothing on it describes the parameters it holds.

Both keys come from one call.
[`supplementWithBasicParamInfo`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/param/ParamContainerFormatter.java#L104-L126)
writes `groups` from `getParamMapByGroups()` and `paramNames` from `getParamMap()`, and
both run through the same `filterNames`, which drops internal-only params. So the two views
agree on membership by construction - and `paramNames` is the flat one, with no grouping to
undo.

Live on 2026-08-10, `GenesByMolecularWeight` returns one group on both plasmodb.org and
toxodb.org: `{name: "empty", displayType: "empty", isVisible: true}` holding all three of
`organism`, `min_molecular_weight`, `max_molecular_weight`. A single synthetic group holding
everything is the common case, which is exactly why treating groups as structure is
tempting and wrong - it looks like it works until a search that really does group its
params arrives.

Read groups when rendering a form. Read `paramNames` for anything else. In particular
`isVisible: false` is a display instruction and not a statement that the parameter is
optional or defaulted; the parameter still has to be supplied.

# WDK-ANS - the answer, its reporters, and what comes back
