---
type: Reference
title: Parameters and their wire forms
description: The eleven parameter types, the difference between type and displayType, and the exact string each type takes in searchConfig.parameters - which is where silent corruption happens.
tags: [wdk-alignment, parameters, wire-format, model]
generated: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
status: stable
---

Every permalink below is pinned to the sha recorded in [sources.md](../sources.md).

# Eleven types, and `displayType` is not one of them

A parameter's `type` is emitted by one method.
[`ParamFormatter.getBaseJson`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/param/ParamFormatter.java#L42-L61)
writes `JsonKeys.TYPE` from the abstract `getParamType()`, and
[`ParamFormatterFactory`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/param/ParamFormatterFactory.java#L18-L55)
picks the formatter by Java class. Each `getParamType()` returns one of the
[eleven `*_PARAM_TYPE` constants](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/core/api/JsonKeys.java#L147-L157),
and `wdk-client`'s
[`Parameter` union](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkModel.ts#L224-L234)
is the same eleven.

| `type` | Java class | Decoded shape |
|---|---|---|
| `string` | `StringParam` | a string, possibly numeric |
| `number` | `NumberParam` | a number |
| `number-range` | `NumberRangeParam` | `{min, max}` |
| `date` | `DateParam` | `yyyy-mm-dd` |
| `date-range` | `DateRangeParam` | `{min, max}` |
| `timestamp` | `TimestampParam` | a string |
| `single-pick-vocabulary` | `AbstractEnumParam`, `isMultiPick=false` | one term |
| `multi-pick-vocabulary` | `AbstractEnumParam`, `isMultiPick=true` | a list of terms |
| `filter` | `FilterParamNew` | `{filters: [...]}` |
| `input-dataset` | `DatasetParam` | a dataset id |
| `input-step` | `AnswerParam` | a step id |

Two of those rows are one Java class. `EnumParamFormatter.getParamType` returns
[`isMultiPick() ? MULTI_VOCAB : SINGLE_VOCAB`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/param/EnumParamFormatter.java#L47-L50),
so the split a client sees is a projection of one model flag.

**`displayType` is a different axis and it is presentation.**
[`AbstractEnumParam.DisplayType`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/AbstractEnumParam.java#L85-L117)
has four values - `select`, `checkBox`, `treeBox`, `typeAhead` - and
[defaults to `checkBox` when multi-pick and `select` when single](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/AbstractEnumParam.java#L195-L204).
`wdk-client` exports eight enum interfaces, and they are exactly the cross
product. Four bases carry a `displayType` and two tiny interfaces carry a
`type`,
[declared together](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkModel.ts#L119-L141),
and the eight exported names are
[every pairing of one with the other](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkModel.ts#L143-L167).
Counting those eight as types is where the larger figures in circulation come
from. `displayType` changes what the form draws; it never changes the value
shape ([WDK-PARAM-001](../rules/parameters-and-vocabularies.md)).

Live on 2026-08-10 the two axes are visibly independent. Parameters live in the
per-search document, so the population is the **320 of plasmodb.org's 325
transcript searches whose `GET /record-types/transcript/searches/{name}`
resolves** - five return 500 and are excluded from every parameter figure in
this bundle. Across those 320, `single-pick-vocabulary` appears with `select`,
`checkBox` and `typeAhead`; `multi-pick-vocabulary` appears with all four. `GenesByLocation.organismSinglePick` is
`multi-pick-vocabulary` rendered as a `select` - a name that says single, a type
that says list. toxodb.org shows the same seven combinations.

Only eight of the eleven appear on either site's transcript searches. Widening
to all 23 record types on plasmodb.org adds `date-range` (11 parameters, all on
`metrics` searches, e.g. `Awstats.date`). **I could not find a live `date` or
`timestamp` parameter on either site** - which is not evidence that none exists
elsewhere in VEuPathDB, only that the two sampled deployments do not use them.

# The wire form is a string, always

`searchConfig.parameters` is
[`Record<string, string>`](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkModel.ts#L284-L286)
and WDK calls the string the *stable value*. A structured type does not get a
JSON object in the map; it gets a JSON object **serialized into a string**. That
one indirection is where most of the damage in this document happens, because a
string that parses to the wrong thing is still a valid string.

The table is what to put in the map. `initialDisplayValue` in a live search
document is the same encoding, which makes it the cheapest available oracle -
[the formatter writes it through `getExternalStableValue`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/param/ParamFormatter.java#L54-L59).

| `type` | Wire string | Live example, 2026-08-10 |
|---|---|---|
| `string` | the value itself | `PF3D7_1133400` (`GeneBySingleLocusTag.single_gene_id`) |
| `number` | decimal digits | `100` (`GenesByMultiBlast.NumQueryResults`) |
| `number-range` | `{"min":...,"max":...}`, both required | `{"min":"20","max":"100"}` (`GenesByIntronJunctions.percent_max`) |
| `date` | `yyyy-mm-dd` | not observed live |
| `date-range` | `{"min":"...","max":"..."}`, both required | `{"min":"2025-01-01","max":"2025-12-31"}` (`metrics/Awstats.date`) |
| `timestamp` | the value itself | not observed live |
| `single-pick-vocabulary` | the bare term | `pfal3D7_microarrayAntibody_Crompton_Mali_RSRC` |
| `multi-pick-vocabulary` | a JSON array of terms | `["Plasmodium falciparum 3D7"]` |
| `filter` | `{"filters":[...]}` | `{"filters":[]}` |
| `input-dataset` | the dataset id | `` (empty by default) |
| `input-step` | the step id | `` (empty by default) |

Note the asymmetry in the two vocabulary rows: **the single-pick form is not a
one-element array of the multi-pick form.** It is a bare string. That is
deliberate and
[documented on the method that does it](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/AbstractEnumParam.java#L772-L804):
internally both are JSON arrays, and single-pick is unwrapped on the way out.

Note also that the two range rows carry **strings** inside the JSON on the live
sites, not numbers. Both are accepted - `org.json`'s `getDouble` coerces - and
both were confirmed valid on plasmodb.org and toxodb.org on 2026-08-10. But
`{"min":"20"}` alone is not
([WDK-PARAM-005](../rules/parameters-and-vocabularies.md)).

# What each type does with a value it does not like

Every parameter class implements `validateValue`, and the differences matter
more than the similarities, because three of them 500 rather than reject.

**`string`** parses as a double when `isNumber`, then applies the model's
`_regex`, then a length cap
([`StringParam.validateValue`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/StringParam.java#L171-L203)).
The numeric bounds a researcher actually meets are this type, not `number` -
`min_molecular_weight` is `type: "string"` with `isNumber: true`, live on both
sites - which is why PathFinder had to learn the distinction
(`pathfinder: docs/knowledge/decisions/numeric-default-is-not-an-example.md`).
The trap: `toInternalValue`
[strips commas](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/StringParamHandler.java#L40-L60)
but validation runs first and the site regex rejects them, so `10,000` never
reaches the code that would have handled it.

**`number`** parses, then regex, then integer-ness, then min and max
([`NumberParam.validateValue`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/NumberParam.java#L105-L145)).

**`number-range`** builds a `JSONObject` and calls `getDouble` on both `min` and
`max`
([`NumberRangeParam.validateValue`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/NumberRangeParam.java#L96-L146)).
A missing key throws `JSONException`, which **is** caught, so a one-sided range
is a clean validation error.

**`date-range`** does the same and then parses each string as a `LocalDate`
([`DateRangeParam.validateValue`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/DateRangeParam.java#L154-L207)).
Only `JSONException` is caught. `LocalDate.parse` throws
`DateTimeParseException`, which is not a `JSONException`, so a well-formed
object holding a badly formatted date escapes the handler entirely - a **500**,
live on both sites ([WDK-PARAM-006](../rules/parameters-and-vocabularies.md)).

**The vocabulary types** skip the database entirely below `SEMANTIC` and then
check the selection count before the terms
([`AbstractEnumParam.validateValue`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/AbstractEnumParam.java#L401-L455)).
That ordering is why an unknown term in a `treeBox` parameter is reported as a
count error rather than as an unknown term - see
[dependent params and vocabularies](dependent-params-and-vocabularies.md).

**`input-step`** is a bare step id: its handler
[stringifies `step.getStepId()`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/AnswerParamHandler.java#L25-L32)
and reads it back with `Long.parseLong`. **`input-dataset`** is a bare dataset id
([`DatasetParamHandler.toStableValue`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/DatasetParamHandler.java#L21-L27)),
and the dataset must belong to the requesting user - `toSignature` throws
`Dataset does not belong to current user` otherwise. Neither is a value a client
invents; both are ids WDK handed out.

# Two endpoints will tell you whether a value is good, and one of them lies about what you sent

`POST /record-types/{rc}/searches/{name}` is the revise endpoint. It takes
`{"contextParamValues": {...}}`, validates at `SEMANTIC` with `NO_FILL`, keeps
that validation, and then - if anything was invalid - **rebuilds the spec with
`FILL_PARAM_IF_MISSING_OR_INVALID`** before rendering
([`QuestionService.getQuestionRevise`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/QuestionService.java#L176-L213)).

So the response body has two halves that disagree on purpose. `validation`
describes what you sent. `searchData.parameters[].initialDisplayValue` describes
what WDK would use instead. Live on both sites, sending
`organism: ["Plasmodium falciparum"]` to `GenesByMolecularWeight` returns
`initialDisplayValue: "[]"` for that parameter - not the branch term you sent -
alongside the error that explains why
([WDK-PARAM-008](../rules/parameters-and-vocabularies.md)).

It is still the best probe available: it needs no login, creates nothing, and
returns per-parameter errors keyed by parameter name. Every live result in this
document and the next one was measured through it or through an anonymous guest
session.

Unknown parameter names are refused before any of that.
[`ParamValueSetRequest.checkParam`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/request/ParamValueSetRequest.java#L66-L71)
throws `DataValidationException`, a **422**, naming the container it looked in.
Live on both sites the container it names is the *query* full name
(`GeneId.GenesByGenericPercentile`), not the search - two more names that are
not the one in your URL.
