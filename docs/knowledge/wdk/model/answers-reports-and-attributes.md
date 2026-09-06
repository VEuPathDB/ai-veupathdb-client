---
type: Reference
title: Answers, reports, and attribute values
description: The two report endpoints, what the standard reporter puts in meta and records, the three shapes an attribute value can take, and where a step analysis result actually comes from.
tags: [wdk-alignment, answers, reports, reporters, attributes, enrichment, model]
generated: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
status: stable
---

Every permalink below is pinned to the sha recorded in [sources.md](../sources.md).

# An answer is a search plus values plus a reporter

WDK never returns "the result". It returns the output of a named *reporter* run over an
*answer value*, and the two are configured separately in one request body:

```
{
  searchConfig: { parameters, filters, ... },   // what to compute
  reportConfig: { attributes, tables, pagination, sorting, ... }   // how to render it
}
```

There are two endpoints and they differ in exactly one thing - where the answer spec comes
from.

| Endpoint | Answer spec from | Body |
|---|---|---|
| `POST /record-types/{rc}/searches/{name}/reports/{reporter}` | the request | `searchConfig` **and** `reportConfig`, both [required](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/AnswerService.java#L282-L304) |
| `POST /users/{userId}/steps/{stepId}/reports/{reporter}` | the step | `reportConfig` only, but a body is still [required](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/user/StepService.java#L239-L282) |

The first runs a search that nothing persists - no step, no strategy, no id. The second runs
a step and refuses one that is not in a strategy before it looks at anything else
([WDK-STEP-005](../rules/strategies-and-steps.md)). Both then converge on
`AnswerService.getAnswerResponse`.

Reporter dispatch is a single map lookup:
[`getConfiguredReporter`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/AnswerService.java#L448-L461)
checks `question.getReporterMap().containsKey(formatName)` and nothing else - not scopes, not
`isInReport` ([WDK-ANS-006](../rules/searches-and-answers.md)). The map is
[the record class's reporters with the search's dynamic-attribute reporters layered over
them](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/question/Question.java#L365-L374),
which is why per-attribute tools like `wdk_weight-histogram` are addressable as reporters.

# `standard` is `DefaultJsonReporter`, and `StandardReporter` is something else

This is the naming trap in the reporter layer, and it decides whether your `reportConfig` is
obeyed.

```
AnswerDetailsReporter          <- honors pagination, sorting, attributes, tables
  DefaultJsonReporter          <- RESERVED_NAME = "standard"

StandardReporter               <- forces full result, primary-key order
  AttributesTabularReporter, TableTabularReporter, FullRecordReporter, JSONReporter, ...
```

[`DefaultJsonReporter.RESERVED_NAME`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/report/reporter/DefaultJsonReporter.java#L36-L58)
is the string `standard`, and the class extends `AnswerDetailsReporter`. The class *named*
`StandardReporter` overrides `setAnswerValue` to call
[`standardizeAnswerValue`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/report/reporter/StandardReporter.java#L52-L66),
which sets the page to unbounded under the comment `always return all records; user cannot
select a subset of records` and empties the sorting map. Measured: and recorded in
[WDK-ANS-005](../rules/searches-and-answers.md).

`AnswerService`'s own javadoc marks the fields this affects, annotating `pagination` and
`sorting` with `[only used by WDK standard JSON]`.

# What `reportConfig` actually means

[`AnswerDetailsFactory.createFromJson`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/report/config/AnswerDetailsFactory.java#L91-L140)
is the whole parser, and the defaults are on the
[field declarations](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/report/config/AnswerDetails.java#L13-L32):

| Key | Omitted means | Note |
|---|---|---|
| `attributes` | **none** | Not the defaults. [WDK-ANS-002](../rules/searches-and-answers.md). Accepts `"__ALL_ATTRIBUTES__"` or `"__DEFAULT_ATTRIBUTES__"` as a bare string instead of an array. |
| `tables` | none | Accepts `"__ALL_TABLES__"`. There is no default-tables value; the javadoc says so outright. |
| `pagination` | `offset 0`, `numRecords -1` = everything | All or nothing. Sending `{offset: 0}` alone is rejected on both sites with `object has missing required properties (["numRecords"])`, by the same schema filter that catches a missing `reportConfig`. |
| `sorting` | the search's default sorting | Attribute must be in the search's attribute map or it is a 400. |
| `attributeFormat` | `DISPLAY` | See below. `TEXT` is the other value. |
| `contentDisposition` | `INLINE` | |
| `bufferEntireResponse` | `false` | `true` buys a real 500 instead of a truncated 200, [up to a 50 MB cap](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/report/reporter/AnswerDetailsReporter.java#L26-L78). |

`createDefault` - the branch that *does* use
[the search's summary attributes and default sorting](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/report/config/AnswerDetailsFactory.java#L29-L45) -
runs only when the whole config object is `null`, and neither endpoint lets you get there.
So the search document's `defaultAttributes` is a suggestion the client has to act on.

# The standard response: `records` then `meta`

[`DefaultJsonReporter.writeResponseBody`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/report/reporter/DefaultJsonReporter.java#L60-L108)
streams `records` first and appends `meta` at the end - it cannot do otherwise, because
`responseCount` is not known until the last record is written. A streaming consumer therefore
sees rows before it sees the counts.

`meta` holds eleven keys, live on both sites:

| Key | Meaning |
|---|---|
| `recordClassName` | **url segment**. The same key inside `records[]` is the full name ([WDK-ANS-004](../rules/searches-and-answers.md)). |
| `totalCount` / `displayTotalCount` | The result size ignoring view filters. |
| `viewTotalCount` / `displayViewTotalCount` | The result size with them. Equal when there are none. |
| `responseCount` | Rows in *this* response. |
| `pagination` | Echo of `{offset, numRecords}` as sent. |
| `attributes` / `tables` | Echo of what was included. |
| `sorting` | The sort actually applied. |
| `cachePreviouslyExisted` | Whether WDK had to compute the result. |

The doubling is the interesting part.
[`getMetaData`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/report/reporter/DefaultJsonReporter.java#L123-L143)
builds a second answer value with the view filters stripped out to compute the `total`
pair, then uses the original for the `viewTotal` pair. So `totalCount` is the honest size of
the step and `viewTotalCount` is what this request is showing - which matters because a
view filter is per-request and never stored on the step
([steps-and-search-config](steps-and-search-config.md)).

**The class comment above the reporter describes a different response.** It lists
`meta: { class, totalCount, responseCount, attributes, tables }`. There is no `class` key -
the code writes `recordClassName` - and the comment omits six keys that are there. Live
`meta` on plasmodb.org and toxodb.org on 2026-08-10 has exactly the eleven above. Read the
method, not the comment.

A record is [five keys](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/report/util/RecordFormatter.java#L41-L52):
`displayName`, `id`, `recordClassName`, `attributes`, `tables`, plus `tableErrors`. `id` is an
ordered array of `{name, value}` pairs, one per primary-key column, and it is present
regardless of what `attributes` you asked for - identity is not an attribute.

`tableErrors` deserves a note. Table loading is caught
[per table rather than per request](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/report/util/RecordFormatter.java#L72-L93),
`since most of the data is probably fine`. So a table that failed appears in `tableErrors`
and *not* in `tables`, and the response is still a 200. A client that ignores `tableErrors`
cannot tell a failed table from an empty one.

# An attribute value is a string, an object, or null

[`getAttributeValueJson`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/report/util/RecordFormatter.java#L110-L140)
is a four-way branch on the attribute's Java type and the requested format:

| Attribute kind | `DISPLAY` (default) | `TEXT` |
|---|---|---|
| Link | `{ url, displayText }` object, or `null` when the text is empty | the url, as a bare string |
| Text | `attr.getDisplay()` | `attr.getValue()` |
| Anything else | `attr.getValue()`, or `null` when empty | same |

Confirmed live on 2026-08-10, one record on plasmodb.org carrying all three shapes at once:
`primary_key` a string, `ec_numbers` `null`, and `gene_entrez_link` the object
`{"displayText": "812594,812594", "url": "http://www.ncbi.nlm.nih.gov/gene/?term=812594,812594"}`.
The same object shape on toxodb.org.

`TEXT` is not an HTML-stripping mode, and assuming it is will bite. It returns the attribute's
*value* instead of its *display* and collapses links to a url - nothing more. Live on both
sites, `organism` loses its `<i>` wrapper under `TEXT` because its display and value differ;
on plasmodb.org `orthomcl_link` comes back as a raw `<a href=...>` anchor under `TEXT` as
well as under `DISPLAY`, because the markup is its stored value. Markup can be in either
format. Only link attributes change *shape*.

# A step analysis result is the plugin's JSON, not WDK's

Enrichment does not go through the reporter layer at all. It is a *step analysis*, a
four-call sequence against a step that is already in a strategy:

```
POST   .../steps/{stepId}/analyses                 -> analysisId
POST   .../steps/{stepId}/analyses/{id}/result     -> 202 {"status":"RUNNING"}
GET    .../steps/{stepId}/analyses/{id}/result/status
GET    .../steps/{stepId}/analyses/{id}/result
```

The last call is a pass-through.
[`getStepAnalysisResult`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/user/StepAnalysisInstanceService.java#L272-L284)
takes `result.get().getResultJson()` and adds four keys - `contextHash`, `accessToken`,
`downloadUrl`, `propertiesUrl`. Everything else, `resultData` included, is whatever the
plugin produced. **WDK does not define, validate, or document those column names**, so no
part of the WDK repository can tell you what an enrichment result looks like.

The plugins that can are in `VEuPathDB/ApiCommonWebsite`, under
`Model/src/main/java/org/apidb/apicommon/model/stepanalysis`, pinned as the fourth
repository in [sources.md](../sources.md). The envelope is
[the plugin's own view model](https://github.com/VEuPathDB/ApiCommonWebsite/blob/830bb57fe07fc2e4dd37b6ea2e3baae0eaee5bee/Model/src/main/java/org/apidb/apicommon/model/stepanalysis/WordEnrichmentPlugin.java#L118-L128),
which is where `resultData` sits alongside `headerRow`, `headerDescription`, `downloadPath`
and `pvalueCutoff`.

Which makes the response's own manifest the thing to read. Each enrichment result carries
`headerRow` and `headerDescription`, objects keyed by exactly the `resultData` keys, giving
each column a label and a description. The column names themselves, and the one that is not
what you would guess, are in [WDK-ANS-007](../rules/searches-and-answers.md).

An analysis needs a step in a strategy, so this is the one part of the answer surface that
cannot be exercised statelessly. It does not need an account: a guest session
(`GET /service/users/current`) is enough, and every enrichment figure in this bundle was
measured that way.
