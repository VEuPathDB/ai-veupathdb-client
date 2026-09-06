---
type: Reference
title: Searches and record classes
description: What a search is bound to, the two names it answers to, why parameter groups are only layout, and why the set of searches is a fact about a deployment rather than about WDK.
tags: [wdk-alignment, searches, record-classes, questions, parameters, model]
generated: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
status: stable
---

Every permalink below is pinned to the sha recorded in [sources.md](../sources.md).

# A search is a record class bound to a query

WDK's own word is *question*. The REST surface calls the same object a *search*, and the two
are the same class: `Question`, whose class comment opens
[`A class representing a binding between a RecordClass and a Query`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/question/Question.java#L51-L62)
and adds that `on the website, a question is displayed in categories, and are called
searches`.

The binding is singular and it is resolved once, at model load:
[`resolveReferences`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/question/Question.java#L549-L562)
assigns `_recordClass` from a single `recordClassRef` before anything else, because the rest
of the question is defined in terms of it. There is no list. A search produces one kind of
thing, forever, and that is why the record type is part of its URL rather than a query
parameter ([WDK-SEARCH-001](../rules/searches-and-answers.md)).

What a search may do is *extend* its record class rather than change it. The same comment
records the two allowed overrides: `dynamicAttributes` introduces attributes that exist only
for this search, and `summaryView` adds or replaces views. So
[`getAttributeFieldMap`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/question/Question.java#L528-L546)
is the record class's attributes with the search's dynamic ones layered on top, primary key
first. That layering is why an attribute name has to be validated against a *search* and not
against a record type: `matched_result` and `wdk_weight` are real attributes of
`GenesByMolecularWeight` and belong to no record class at all, confirmed live on
plasmodb.org and toxodb.org on 2026-08-10.

# Two names, and only one of them is a URL

[`QuestionFormatter`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/QuestionFormatter.java#L64-L96)
emits both:

| Field | Source | Live example |
|---|---|---|
| `urlSegment` | `q.getName()` | `GenesByMolecularWeight` |
| `fullName` | `q.getFullName()` | `GeneQuestions.GenesByMolecularWeight` |
| `outputRecordClassName` | `q.getRecordClass().getUrlSegment()` | `transcript` |
| `queryName` | `q.getQuery().getName()` | the id query behind it |

The full name is question-set plus short name. The url segment defaults to the short name and
can be overridden in the XML, so the two are related by convention rather than by rule, and
neither can be computed from the other.

Only `urlSegment` works as a path segment - `GeneQuestions.GenesByMolecularWeight` is a 404 on
both sites, against `QuestionService`'s own class comment, which is the whole of
[WDK-SEARCH-002](../rules/searches-and-answers.md). The full name is what a step's
`searchName` carries and what WDK's error messages quote, so both names have to be kept.

Note the third row. `outputRecordClassName` is a **url segment**, so it can be pasted
straight into `/record-types/{rc}/`, while the record class *full name* is what
`AbstractWdkService` compares against internally and what a record instance reports
([WDK-ANS-004](../rules/searches-and-answers.md)). Three fields, two vocabularies, and the
JSON does not label which is which.

# Transform inputs are the only other record class a search names

A search with an answer parameter declares what it will accept, and
`getAllowedRecordClasses` maps those to
[url segments, or omits the property entirely when there is no such parameter](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/QuestionFormatter.java#L98-L108).
The absence of `allowedPrimaryInputRecordClassNames` is therefore how you tell a leaf search
from a transform, and the counting rule behind it is in
[steps-and-search-config](steps-and-search-config.md).

The consequence worth repeating here: a transform's input record class and its output record
class are independent. `TranscriptsFromGenes` accepts `gene` and outputs `transcript`. So
"the record class of a search" is two questions, and `outputRecordClassName` answers only
one of them.

# Parameter groups are layout

A search's parameters arrive twice in one document, and
[`supplementWithBasicParamInfo`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/param/ParamContainerFormatter.java#L104-L126)
writes both from the same source in the same call - `groups` from `getParamMapByGroups()`,
`paramNames` from `getParamMap()`, both filtered through one `filterNames` that drops
internal-only parameters. They cannot disagree about membership.

`Group` has nothing else in it.
[Its class comment](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/Group.java#L6-L16)
says a group is `only used to group Params together in the question page for display/layout
purpose`, and that an ungrouped parameter falls into the default `Empty` group - which is
[a singleton with display type `empty` and `visible = true`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/Group.java#L41-L63),
alongside a `Hidden` singleton for parameters with no group and visibility off.

That default is what you usually see. `GenesByMolecularWeight` returns exactly one group on
plasmodb.org and on toxodb.org, named `empty`, holding all three parameters - a group that
exists because the parameters had none. Reading structure into it is reading structure into
a placeholder ([WDK-SEARCH-004](../rules/searches-and-answers.md)).

`isVisible: false` is a rendering instruction and nothing more. It does not make a parameter
optional, defaulted, or safe to omit.

# The set of searches belongs to the deployment

[`getQuestions`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/QuestionService.java#L96-L105)
filters `model.getAllQuestions()` by record class full name on every request. Nothing is
cached in the service and nothing is enumerated anywhere in the platform; the model is
whatever XML that site loaded.

The same is true one level up. `GET /record-types` returns
[a bare array of url segments](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/RecordService.java#L62-L75)
unless you ask for `format=expanded`. Live on 2026-08-10 both plasmodb.org and toxodb.org
return 23 record types - and they are not the same 23. plasmodb.org has `snp-chip`;
toxodb.org has `rflp-isolate`; the other 22 match. Equal counts, different sets, which is a
good reason not to compare lengths.

Below that, `transcript` carries **325** searches on plasmodb.org and **234** on toxodb.org.
So "does this site have this search" is a question only the site can answer, and
[WDK-SEARCH-003](../rules/searches-and-answers.md) is the rule that says to ask it.

# The record class document, and the size of it

`GET /record-types/{rc}` **defaults to the expanded form** - the format parameter's default
is `true` here and `false` on the collection endpoint, which is easy to get backwards:

```java
isExpandedFormat(format, true)   // GET /record-types/{rc}
isExpandedFormat(format, false)  // GET /record-types
```

Expanded means [the record class plus its `searches`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/RecordService.java#L82-L99),
and the record class itself is
[always emitted with attributes and tables expanded](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/RecordClassFormatter.java#L59-L86).
There is no lightweight form of this document. Live on plasmodb.org, `transcript` returns
**3,070** attribute objects and 325 search objects in one response. Fetch it once per site
and keep it; do not fetch it per search.

The fields that carry meaning rather than presentation:

| Field | Note |
|---|---|
| `urlSegment` | The path segment. `transcript`. |
| `fullName` | `TranscriptRecordClasses.TranscriptRecordClass`. The form a record instance reports. |
| `primaryKeyColumnRefs` | Ordered. Live for `transcript`: `gene_source_id`, `source_id`, `project_id`. This is the order `records[].id` comes back in. |
| `recordIdAttributeName` | Live: `primary_key`. The attribute holding the display id. |
| `attributes` | Every attribute the record class defines. Not every attribute a *search* has. |
| `tables` | Multi-row data. Often empty - `transcript` has **0** on both sites, `pathway` has 4. |
| `formats` | The reporters. See [WDK-ANS-006](../rules/searches-and-answers.md) for what `scopes` does and does not mean. |

# An attribute is one value per record; a table is many rows

[`AttributeField`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/record/attribute/AttributeField.java#L27-L41)
`defines a single value property to a RecordClass`.
[`TableField`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/record/TableField.java#L36-L45)
`defines a table of data associated with a recordClass` and holds attribute fields of its
own. That is the entire distinction, and it is why they are separate keys in a report
request and separate keys in a record.

Both are `ScopedField`, so both carry
[`internal` and `inReportMaker`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/record/ScopedField.java#L9-L19),
surfaced as `isDisplayable` and `isInReport` by
[`AttributeFieldFormatter`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/AttributeFieldFormatter.java#L42-L58)
and its table equivalent. Those are advice to a client about what to offer, not a statement
about what a request will accept.

One asymmetry does bite. A table backed by a process query rather than SQL
[is single-record only](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/record/TableField.java#L116-L118),
and the two paths disagree about whether to show it. The record class document asks for
[`getTableFieldMap(true)`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/record/RecordClass.java#L576-L585),
which includes them, while a search asks for
[`getTableFieldMap(false)`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/question/Question.java#L1137-L1139),
which does not. So the record type can list a table that a report of that record type will
refuse, with `is not available for question`. Neither verification site has such a table on
`transcript` or `pathway`, so this is stated from source and is **not** live-confirmed.

# The pinned sha is not the deployed build

The consequence of this section, and the list of rules it puts in doubt, is in
[sources.md](../sources.md). What follows is the evidence behind it.

Worth knowing before you trust a key's presence.
[`TableFieldFormatter.getTableJson`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/TableFieldFormatter.java#L43-L58)
ends with `.put(JsonKeys.SINGLE_RECORD_ONLY, table.isForSingleRecordOnly())`, whose wire name
is [`supportsSingleRecordOnly`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/core/api/JsonKeys.java#L94)
- not `isSingleRecordOnly`, which is the name you would guess. The value is a primitive
boolean, so it cannot be dropped the way a null `type` or `help` is dropped.

Neither plasmodb.org nor toxodb.org emits it. On 2026-08-10 every table object on
`record-types/pathway` on both sites had exactly `attributes`, `clientSortSpec`,
`description`, `displayName`, `isDisplayable`, `isInReport`, `name`, `properties` - eight
keys, and `supportsSingleRecordOnly` was not among them.

The pin is a fixed point to reason from, not a description of what is running. Read the sha
for what a field *means*; read the deployment for what is *there*. A client that requires
`supportsSingleRecordOnly` because the pinned formatter writes it will fail against every
site in [sources.md](../sources.md).
