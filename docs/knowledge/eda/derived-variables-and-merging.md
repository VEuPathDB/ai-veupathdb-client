---
type: Reference
title: EDA derived variables and merging
description: The twelve EDA derived-variable plugins with their exact config shapes, how the merging service traverses the entity tree, and how derived variables are persisted and referenced, proved live on ClinEpiDB.
tags: [eda, veupathdb, derived-variables, merging, reductions, transforms]
generated: { by: claude-code/opus-5, at: 2026-08-27T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-27T00:00:00Z }
status: stable
---

# EDA derived variables and merging

A derived variable is a column the EDA service computes on the fly, per
request, from other variables in the same study. The merging service owns them.
It is also the only service that returns rows from more than one entity in one
answer, which is why the two subjects are one document: a derived variable
that reaches across entities and a merged output that reaches across entities
are the same tree traversal.

The io-ts type is not a source of truth here. In
[`web-monorepo` `analysis.ts`](https://github.com/VEuPathDB/web-monorepo/blob/3e04f4ff37b7a960fcb2edcf3f65dba876d14815/packages/libs/eda/src/lib/core/types/analysis.ts)
line 40 the whole definition is `export const DerivedVariable = t.unknown;`.
The truth is the RAML plus the Java plugins:

- [`service-eda` `schema/library.raml`](https://github.com/VEuPathDB/service-eda/blob/b3bb8bac06de4340b4b2c21d9aa4a94d9b3de61f/schema/library.raml)
  and [`api.raml`](https://github.com/VEuPathDB/service-eda/blob/b3bb8bac06de4340b4b2c21d9aa4a94d9b3de61f/api.raml).
- [`src/main/java/org/veupathdb/service/eda/merge/`](https://github.com/VEuPathDB/service-eda/tree/b3bb8bac06de4340b4b2c21d9aa4a94d9b3de61f/src/main/java/org/veupathdb/service/eda/merge)
  - `core/derivedvars/` (the machinery), `plugins/Reductions.java` and
  `plugins/Transforms.java` (the registries), `plugins/reductions/` and
  `plugins/transforms/` (the implementations).

Live proofs ran on 2026-08-27 against `https://clinepidb.org/eda` with a
registered WDK token as `Cookie: Authorization={token}`. Filter JSON shapes are
in [filters.md](filters.md); the data model is in
[what-eda-is.md](what-eda-is.md).

## The spec every derived variable takes

**schema**, `DerivedVariableSpec` extends `VariableSpec`:

```json
{
  "entityId": "GAZ_00000448",
  "variableId": "DV_meanMortality",
  "functionName": "mean",
  "displayName": "Mean mortality rate",
  "config": { }
}
```

`entityId` is the entity the new column lands ON, which is not necessarily the
entity its inputs come from. `variableId` is an id the caller invents;
`config` is `object` in the RAML and its real shape is per `functionName`.

Rules, all from
[`DerivedVariableFactory`](https://github.com/VEuPathDB/service-eda/blob/b3bb8bac06de4340b4b2c21d9aa4a94d9b3de61f/src/main/java/org/veupathdb/service/eda/merge/core/derivedvars/DerivedVariableFactory.java)
and confirmed live:

- An unknown `functionName` is 400:
  `{"status":"bad-request","message":"Unrecognized derived variable function
  name: notAThing"}`.
- A `variableId` that collides with a native variable on the same entity is
  400: `{"status":"bad-request","message":"Tried to add element
  {\"entityId\":\"GAZ_00000448\",\"variableId\":\"OBI_0001627\"} to entity def
  with name that already exists."}`.
- Two specs with the same `entityId` + `variableId` do NOT error. **live:**
  a `mean` spec and a `sum` spec both named `DV_dup` returned HTTP 200 and the
  `mean` values (71.725, 70.006, 79.618, 84.34, 80.977, 94.40599999999999,
  95.598). The factory skips a spec whose variable is already present, so the
  first wins silently and the second is discarded. The uniqueness check that
  raises `"Derived variable names are not unique."` compares list sizes after
  that de-duplication, so it can never fire for an exact duplicate. Do not
  rely on last-write-wins.
- Specs are topologically ordered and circular dependencies are rejected.
- Plugins may declare their own internal helper specs, which are added to the
  same graph (this is how one plugin is currently broken - see
  `relativeObservationMinTimeInterval` below).

## Reductions and transforms

**schema**, `DerivationType` is `transform | reduction`, and the two
registries in
[`Reductions.java`](https://github.com/VEuPathDB/service-eda/blob/b3bb8bac06de4340b4b2c21d9aa4a94d9b3de61f/src/main/java/org/veupathdb/service/eda/merge/plugins/Reductions.java)
and
[`Transforms.java`](https://github.com/VEuPathDB/service-eda/blob/b3bb8bac06de4340b4b2c21d9aa4a94d9b3de61f/src/main/java/org/veupathdb/service/eda/merge/plugins/Transforms.java)
are described in their own javadoc as "the definitive list".

A **transform** reads one row and writes one value on the same entity.
`Transform.getValue(Map<String,String> row)`.

A **reduction** collects rows from a DESCENDANT entity and reduces them to one
value on the target entity. `Reduction.createReducer()` returns a fresh
`Reducer` per output row; `addRow` is called for each descendant row and
`getResultingValue` once, possibly with zero `addRow` calls.
[`Reduction.validateDependedVariableLocations`](https://github.com/VEuPathDB/service-eda/blob/b3bb8bac06de4340b4b2c21d9aa4a94d9b3de61f/src/main/java/org/veupathdb/service/eda/merge/core/derivedvars/Reduction.java)
requires the input variables' lowest common entity to be the target entity or
a descendant of it, and requires all input variables to sit in one branch of
the tree. **live**, a `mean` whose input is an ancestor variable:
`{"status":"bad-request","message":"Input vars configured for reduction derived
var mean are not on the target or a descendant entity."}`.

There is no aggregation in the other direction, and none is needed: pulling an
ancestor variable onto descendant rows is plain broadcast and the merging
service does it for any variable without a plugin.

## The twelve plugins

Reductions (4) and transforms (8). Function names are the `getFunctionName()`
return values; config type names are the RAML types listed in
`DerivedVariableDocumentationRequest`, whose only purpose is to make those
types appear in the generated API page.

| `functionName` | kind | config type | config fields |
| --- | --- | --- | --- |
| `sum` | reduction | `SingleNumericVarReductionConfig` | `inputVariable: VariableSpec`, `imputeZero?: boolean` |
| `mean` | reduction | `SingleNumericVarReductionConfig` | same |
| `subsetMembership` | reduction | `SubsetMembershipConfig` | `subsetFilters: API_Filter[]` |
| `relativeObservationAggregator` | reduction | `RelativeObservationAggregatorConfig` (a Java record, not in the RAML) | `varDescription: string`, `variable: VariableSpec`, `timestampVariable: VariableSpec`, `trueValues: string[]`, `filtersOverride: API_Filter[]` |
| `concatenation` | transform | `ConcatenationConfig` | `inputVariables: VariableSpec[]`, `prefix?`, `delimiter?`, `suffix?` |
| `bodyMassIndex` | transform | `BodyMassIndexConfig` | `heightVariable: VariableSpec`, `weightVariable: VariableSpec` |
| `categoricalRecoding` | transform | `CategoricalRecodingConfig` | `inputVariable: VariableSpec`, `rules: [{inputValues: string[], outputValue: string}]`, `unmappedValue?: string` |
| `continuousToOrdinal` | transform | `ContinuousNumericRecodingConfig` | `inputVariable: VariableSpec`, `rules: [{minInclusive?: number, maxExclusive?: number, outputValue: string}]`, `unmappedValue?: string` |
| `advancedSubset` | transform | `AdvancedSubsetConfig` | `rootStepKey: string`, `steps: Step[]` |
| `ecmaScriptExpressionEval` | transform | `EcmaScriptExpressionEvalConfig` | `ecmaScriptExpression: string`, `nullResultOnAnyMissingInput: boolean`, `inputVariables: [{name: string, variable: VariableSpec}]`, `expectedType: API_VariableType`, `expectedShape: API_VariableDataShape` |
| `relativeObservationMinTimeInterval` | transform | `RelatedObservationMinTimeIntervalConfig` | `relatedObservationsSubset: API_Filter[]`, `anchorVariable`, `anchorVariableTrueValues: string[]`, `anchorTimestampVariable`, `targetVariable`, `targetVariableTrueValues: string[]`, `targetTimestampVariable`, `minimumTimeIntervalDays: integer` |
| `unitConversion` | transform | `UnitConversionConfig` | `inputVariable: VariableSpec`, `outputUnits: string` |

`Step`, used by `advancedSubset`: `{key: string, operation: SetOperation,
leftStepKey?, leftVariable?: VariableSpec, leftVariableTrueValues?: string[],
rightStepKey?, rightVariable?, rightVariableTrueValues?}`, where
`SetOperation` is `intersect | union | minus`. A step names either another
step (`leftStepKey`) or a variable plus its true values on each side, and
`rootStepKey` selects the step whose result becomes the column.

Naming caveat, all **schema**: the function name is
`relativeObservationMinTimeInterval` ("Relative") while its config type is
`RelatedObservationMinTimeIntervalConfig` ("Related") and one of its fields is
`relatedObservationsSubset`. The RAML documentation key matches the function
name. Do not normalise the spelling.

### Ten of twelve, proved live

All on ClinEpiDB, `POST /eda/merging/query`, HTTP 200 with a TSV body unless
noted. `2020-kamgang-congo` is the mosquito insecticide-resistance study whose
tree is `GAZ_00000448` (7 sites) -> `OBI_0000659` (7 collections) ->
`EUPATH_0000609` (17 samples) -> `OBI_0002695` (42 resistance assays).

**`mean`** - mortality rate from the assay entity reduced onto site rows:

```json
{"studyId":"2020-kamgang-congo","filters":[],"entityId":"GAZ_00000448",
 "derivedVariables":[{"entityId":"GAZ_00000448","variableId":"DV_meanMortality",
   "functionName":"mean","displayName":"Mean mortality rate",
   "config":{"inputVariable":{"entityId":"OBI_0002695","variableId":"APOLLO_SV_00000445"}}}],
 "outputVariables":[{"entityId":"GAZ_00000448","variableId":"OBI_0001627"},
                    {"entityId":"GAZ_00000448","variableId":"DV_meanMortality"}]}
```

```
GAZ_00000448.GeographicLocation_stable_id  GAZ_00000448.OBI_0001627          GAZ_00000448.DV_meanMortality
2020-kamgang-congo_1                       Republic of the Congo             71.725
2020-kamgang-congo_2                       Republic of the Congo             70.006
2020-kamgang-congo_3                       Democratic Republic of the Congo  79.618
2020-kamgang-congo_4                       Republic of the Congo             84.34
2020-kamgang-congo_5                       Republic of the Congo             80.977
2020-kamgang-congo_6                       Republic of the Congo             94.40599999999999
2020-kamgang-congo_7                       Republic of the Congo             95.598
```

**`sum`** - same shape over `POPBIO_8000018` ("number of input specimens"):
347.0, 442.0, 436.0, 459.0, 932.0, 458.0, 518.0.

**`subsetMembership`** - a binary column that is 1 when the row has at least
one descendant row matching its own filter array.
`config: {"subsetFilters":[{"entityId":"OBI_0002695","variableId":"CHEBI_24852","type":"stringSet","stringSet":["DDT"]}]}`
returned 1 for all 7 sites. **schema:** vocabulary is `["1","0"]`,
`variableType: integer`, `dataShape: binary`, and the reducer returns 1 if
`addRow` was called even once. Its `subsetFilters` are a filters OVERRIDE, not
an addition: `Reduction.getFiltersOverride()` replaces the request's filters
for that plugin's input stream.

**`categoricalRecoding`** on the assay entity:
`rules: [{inputValues:["DDT"],outputValue:"organochlorine"},
{inputValues:["deltamethrin","permethrin"],outputValue:"pyrethroid"}]`,
`unmappedValue: "other"`. `DDT -> organochlorine`,
`deltamethrin -> pyrethroid`, `permethrin -> pyrethroid`,
`fenitrothion -> other`, `propoxur -> other`.

**`continuousToOrdinal`** on `APOLLO_SV_00000445` with rules
`[{maxExclusive:90,outputValue:"resistant"},
{minInclusive:90,maxExclusive:98,outputValue:"possible resistance"},
{minInclusive:98,outputValue:"susceptible"}]`:
38.35 -> `resistant`, 94.43 -> `possible resistance`,
100.0 -> `susceptible`, 54.12 -> `resistant`.

**`concatenation`** with `prefix:"["`, `delimiter:" | "`, `suffix:"]"` over
`[CHEBI_24852, OBI_0000272]`:
`[DDT | WHO paper kit diagnostic assay]`,
`[deltamethrin | WHO paper kit diagnostic assay]`.

**`ecmaScriptExpressionEval`** with
`ecmaScriptExpression: "m / 100"`,
`inputVariables: [{"name":"m","variable":{"entityId":"OBI_0002695","variableId":"APOLLO_SV_00000445"}}]`,
`expectedType: "number"`, `expectedShape: "continuous"`:
38.35 -> 0.3835, 94.43 -> 0.9443, 100.0 -> 1.0,
97.73 -> 0.9773000000000001. The expression is compiled into a JS function
whose parameters are the `name` fields, so the names, not the variable ids,
are the identifiers in the expression.

**`advancedSubset`** on the sample entity, one `intersect` step
(`leftVariable` species with `leftVariableTrueValues: ["Aedes aegypti"]`,
`rightVariable` biological sex with `rightVariableTrueValues: ["female"]`,
`rootStepKey: "s1"`). Result over all 17 samples: 1 for exactly
`brazzaville_aegypti` and `ngo_aegypti` (both `Aedes aegypti` + `female`), 0
for every other row including `brazzaville_aegypti_larvae`
(`Aedes aegypti` + `mixed sex`).

**`unitConversion`** and **`bodyMassIndex`** on ClinEpiDB `INDIA0002-1`,
entity `EUPATH_0000738` ("Participant repeated measure"), which carries
`EUPATH_0010075` Height in `cm` and `IAO_0000414` Weight in `kg`.
`{"inputVariable": Height, "outputUnits":"m"}`:
159.0 -> 1.59, 165.0 -> 1.6500000000000001, 147.0 -> 1.47, 110.0 -> 1.1.
`bodyMassIndex` with those two variables: (159.0, 89.8) -> 35.52074680590166,
(165.0, 72.2) -> 26.51974288337924, (110.0, 17.6) -> 14.545454545454545.

`unitConversion` has three distinct failures, all **live** 400:

- unknown output unit ->
  `"Output unit 'centimeter' is not a valid unit"`. The valid strings are the
  `values` arrays from `GET /merging/derived-variables/metadata/units`, NOT
  the `displayName` fields. `"centimeter"` is a display name; `"cm"` is the
  value.
- incompatible dimensions ->
  `"Output unit KILOGRAM is not compatible with input variable's unit
  CENTIMETER"`.
- the input variable's own `units` string is not a recognised value ->
  `"Variable 'OBI_0002695.EUPATH_0043064' has a unit 'minute' that is not
  convertible to other units."` The units table's `time small` type lists a
  `minute` unit whose accepted values are `["min","minutes"]`, so a study that
  loaded the string `minute` cannot be converted. Study curation, not caller
  error - and unfixable from the request.

`GET /merging/derived-variables/metadata/units` returned, **live**:

```
length: mm, cm, feet, m, km
mass: ug, mg, g, kg
volume: mL/ml, L
temperature: C, F
time large: months, years/Years
time small: ms, sec, min/minutes, hours, days, weeks
mass proportion: ug/g, mg/g
mass by volume: (no units)
biological effect by volume: (no units)
```

### The two that cannot be reached

`relativeObservationMinTimeInterval` is registered in `Transforms` but is
**broken upstream**. Its
[`getDependedDerivedVarSpecs()`](https://github.com/VEuPathDB/service-eda/blob/b3bb8bac06de4340b4b2c21d9aa4a94d9b3de61f/src/main/java/org/veupathdb/service/eda/merge/plugins/transforms/RelativeObservationMinTimeInterval.java)
declares an internal helper with
`functionName = RelativeObservationCalculator.FUNCTION_NAME`, which is
`"relativeObservationCalculator"` - and `RelativeObservationCalculator.class`
is NOT in the `Transforms.getPlugins()` list. **live**, a well-formed request
on `INDIA0002-1` (anchor `EUPATH_0000417` "Ill now" = Yes, target
`EUPATH_0021090` "Fever in last 48 hours" = Yes, timestamps
`EUPATH_0004991` "Observation date", `minimumTimeIntervalDays: 1`):

```
{"status":"bad-request","message":"Unrecognized derived variable function name: relativeObservationCalculator"}  HTTP 400
```

The chain the plugin's own javadoc describes (A: a reduction pulling
[value, timestamp, id] from the child entity, B: a transform aggregating and
assigning the minimum, C: a transform inheriting B) cannot execute, because B
is unregistered. `relativeObservationAggregator` (the A step) IS registered,
so the only unreachable plugin is the calculator, and the only unusable
public function name is `relativeObservationMinTimeInterval`.
`relativeObservationAggregator` is reachable but its config type is a Java
record absent from the RAML, so it is undocumented rather than broken;
**UNVERIFIED:** no live proof of calling it directly was attempted.

## Merging semantics

`POST /merging/query`. **schema**, `MergedEntityTabularPostRequest` extends
`DerivedVariableBulkMetadataRequest`, so the full body is:

```json
{
  "studyId": "2020-kamgang-congo",
  "derivedVariables": [ /* DerivedVariableSpec[] */ ],
  "filters": [ /* API_Filter[] */ ],
  "entityId": "OBI_0002695",
  "outputVariables": [ /* VariableSpec[] */ ],
  "computeSpec": { "computeName": "...", "computeConfig": { } }
}
```

The response is `text/tab-separated-values`. There is no paging or sorting
config on this endpoint, unlike `POST /studies/{s}/entities/{e}/tabular`.
`/merging-internal/query` is the same operation with the same body, for
service-to-service calls.

### Column naming

**live.** Every column header is `{entityId}.{columnName}`. The service
prepends the target entity's primary key and every ancestor primary key, in
child-to-root order, before the requested variables:

```
OBI_0002695.InsecticideResistanceAssay_stable_id  EUPATH_0000609.Sample_stable_id  OBI_0000659.ParentOfSample_stable_id  GAZ_00000448.GeographicLocation_stable_id  GAZ_00000448.OBI_0001627  ...
```

The primary key column names come from each entity's `idColumnName` in
`GET /studies/{id}`. A caller cannot suppress them.

### Ancestor variables broadcast onto descendant rows

**live**, `entityId: "OBI_0002695"` with output variables drawn from three
levels of the tree:

```json
{"studyId":"2020-kamgang-congo","filters":[],"derivedVariables":[],
 "entityId":"OBI_0002695",
 "outputVariables":[{"entityId":"GAZ_00000448","variableId":"OBI_0001627"},
                    {"entityId":"GAZ_00000448","variableId":"OBI_0001621"},
                    {"entityId":"EUPATH_0000609","variableId":"OBI_0001909"},
                    {"entityId":"OBI_0002695","variableId":"CHEBI_24852"},
                    {"entityId":"OBI_0002695","variableId":"APOLLO_SV_00000445"}]}
```

```
...OBI_0002695...stable_id                          GAZ_00000448.OBI_0001627  GAZ_00000448.OBI_0001621  EUPATH_0000609.OBI_0001909  OBI_0002695.CHEBI_24852  OBI_0002695.APOLLO_SV_00000445
lefini_albopictus.DT.IR_WHO.DDT                     Republic of the Congo     15.6322                   Aedes albopictus            DDT                      38.35
lefini_albopictus.DT.IR_WHO.deltamethrin            Republic of the Congo     15.6322                   Aedes albopictus            deltamethrin             94.43
lefini_albopictus.DT.IR_WHO.fenitrothion            Republic of the Congo     15.6322                   Aedes albopictus            fenitrothion             100.0
lefini_albopictus.DT.IR_WHO.permethrin              Republic of the Congo     15.6322                   Aedes albopictus            permethrin               54.12
owando_albopictus.DT.IR_WHO.DDT                     Republic of the Congo     15.9114                   Aedes albopictus            DDT                      21.92
```

One row per target-entity row. The site's country and longitude repeat on every
assay under that site - a many-to-one traversal resolved by repetition, with
no aggregation and no plugin required.

### Descendant variables do NOT come onto ancestor rows

**live**, `entityId: "GAZ_00000448"` asking for an assay variable:

```
{"status":"bad-request","message":"{\"keyedErrors\":{\"incoming\":[\"Variable '{\\\"entityId\\\":\\\"OBI_0002695\\\",\\\"variableId\\\":\\\"APOLLO_SV_00000445\\\"}' must be available on entity 'GAZ_00000448'.\"]},\"validationLevel\":\"RUNNABLE\",\"validationStatus\":\"FAILED\",\"errors\":[]}"}   HTTP 400
```

The direction is asymmetric by design: seven site rows cannot hold 42 assay
values, so the caller must say HOW to collapse them, and a reduction derived
variable is that statement. This is the single most important shape fact for a
model authoring merge requests: choose the output entity first, then decide
whether each wanted variable is at or above that entity (name it directly) or
below it (wrap it in a reduction).

The error envelope on `/merging/query` differs from the subsetting service's:
the `message` is a JSON string containing `keyedErrors`, `validationLevel`,
`validationStatus` and `errors`. Parse it as nested JSON, not as prose.

## Derived variables and filters

Two facts, both **live**, and they pull in opposite directions.

**Filters restrict a reduction's inputs.** The same `mean` request as above,
with `filters: [{"entityId":"OBI_0002695","variableId":"CHEBI_24852",
"type":"stringSet","stringSet":["deltamethrin"]}]`, returned per-site means of
94.43, 97.73, 97.61, 100.0, 97.63499999999999, 97.77, 100.0 - the
deltamethrin rows only, against 71.725 / 70.006 / 79.618 / 84.34 / 80.977 /
94.406 / 95.598 unfiltered. Site 5's 97.635 is a mean of two surviving rows.
A reduction is computed over the filtered subset, so the same spec under two
filter arrays is two different numbers. A stored derived variable is not a
stored value.

**A filter cannot name a derived variable.** The filter array is executed by
the subsetting service, which has no knowledge of the merge request's
`derivedVariables`. **live** on `/merging/query`, filtering on `DV_hasDDT`
while declaring it in the same body:

```
{"status":"bad-request","message":"Variable 'DV_hasDDT' is not found"}   HTTP 400
```

The same attempt through a data plugin,
`POST /eda/apps/distributions/visualizations/histogram` with the same
`filters` and `derivedVariables`, fails differently and worse:

```
{"status":"server-error","message":"Unable to fetch all required data","requestId":"4jTC6JEW1qNwKRaXJq7oz2"}   HTTP 500
```

So: to subset BY a derived condition, inline the condition as a real filter
array instead - which is exactly what `subsetMembership` and
`advancedSubset` exist to express as a column, and what an ordinary filter
array expresses as a subset.

A derived variable IS usable as a plot input. **live**, the same histogram
endpoint with `DV_frac` (an `ecmaScriptExpressionEval` column) as
`config.xAxisVariable` and no filter on it returned bins from
`[0.2192, 0.2972)` to `[0.9992, 1.077]` with counts summing to 39. Note the
response reported that column as `"variableClass":"native"`, not `"derived"`
(**schema**: `VariableClass` is `native | derived | computed`), so the
response metadata cannot be used to tell a derived column from a real one.

Where `derivedVariables` is accepted, all **schema**:

- `MergedEntityTabularPostRequest.derivedVariables: DerivedVariableSpec[]`
  (inherited, required).
- `ComputeRequestBase.derivedVariables: DerivedVariableSpec[]` - the body of
  `POST /computes/{name}`, alongside `studyId`, optional `filters` and
  `config`.
- `DataPluginRequestBase.derivedVariables: DerivedVariableSpec[]` (optional) -
  the body of every `POST /apps/{app}/visualizations/{viz}`.
- `DerivedVariableBulkMetadataRequest` - `{studyId, derivedVariables}` for the
  metadata endpoint below.

`POST /studies/{s}/entities/{e}/count` and `.../tabular` do NOT take
`derivedVariables` at all. Subsetting is derived-variable-blind end to end.

## The metadata endpoints

**live.** `POST /merging/derived-variables/metadata/variables` with
`{studyId, derivedVariables}` returns one `DerivedVariableMetadata` per spec,
which is how a client learns a derived column's type before requesting data:

```json
[{"derivationType":"reduction","variableType":"number","vocabulary":null,
  "variableId":"DV_meanMortality","dataShape":"continuous","dataRange":null,
  "units":null,"entityId":"GAZ_00000448"},
 {"derivationType":"reduction","variableType":"integer","vocabulary":["1","0"],
  "variableId":"DV_hasDDT","dataShape":"binary","dataRange":null,
  "units":null,"entityId":"GAZ_00000448"}]
```

`GET /merging/derived-variables/metadata/units` returns the unit table quoted
above.

`POST /merging/derived-variables/input-specs` is documentation scaffolding, not
an API. **schema**, `api.raml` labels it "This endpoint is used only to produce
documentation of derived variable configuration types" and declares a `204`
response. **live**, POSTing with no body returns HTTP 204 with an empty body;
`GET` on it returns HTTP 405 `{"status":"method-not-allowed","message":"HTTP
405 Method Not Allowed"}`. Its value is entirely in the RAML: its request type
`DerivedVariableDocumentationRequest` is the enumeration of the eleven
documented config types, and reading that RAML type is the only way to get the
list without reading the Java.

## The persisted side

Two separate stores, and they are referenced differently.

### Persisted derived variables

**schema**, `api.raml` `/users/{user-id}/derived-variables/{project-id}`:

- `GET` -> `DerivedVariableGetResponse[]`, which is a `DerivedVariableSpec`
  plus `datasetId`, optional `description` (max 4000 chars) and optional
  `provenance: {copyDate, copiedFrom}`.
- `POST` -> `DerivedVariablePostRequest`
  `{datasetId, entityId, displayName (1..256), functionName, config,
  description? (max 4000)}` -> `DerivedVariablePostResponse`, which is just a
  `VariableSpec` `{entityId, variableId}` - the id the server assigns.
- `GET|PATCH /{derived-variable-id}`; `PATCH` takes
  `{displayName?, description?}` and returns 204. There is no `DELETE`.

Note the POST is keyed by `datasetId` (`DS_xxx`), not `studyId`
(`STUDY_xxx`) - the dataset is the permission currency, and the two ids
differ (see [what-eda-is.md](what-eda-is.md)).

**live: this endpoint is not functional on either deployment tested on
2026-08-27.** `GET
https://clinepidb.org/eda/users/1216062453/derived-variables/ClinEpiDB` and
`GET https://plasmodb.org/eda/users/1216062453/derived-variables/PlasmoDB`
both returned HTTP 500 `{"status":"server-error","message":"Unable to
complete requested operation","requestId":"..."}`, and a well-formed `POST`
returned the same 500. A wrong project id gives 404 instead of 500, so the
route resolves and the failure is behind it. **UNVERIFIED:** the cause. A
missing user-database table is the obvious candidate but was not confirmed.
Consequence for PathFinder: only the inline `DerivedVariableSpec[]` path in
merge, compute and data-plugin bodies is usable today, and the inline path
needs no persistence.

### How an analysis references a derived variable

This is where the io-ts and the RAML disagree most sharply, and the RAML wins.

**schema.** `AnalysisDescriptor.derivedVariables` is `string[]` in
`library.raml`. In `analysis.ts` it is `t.array(DerivedVariable)` where
`DerivedVariable = t.unknown`, which types nothing and hides the fact that the
elements are ids.

**live**, on ClinEpiDB `POST /eda/users/1216062453/analyses/ClinEpiDB`. A
descriptor whose `derivedVariables` holds a string was accepted:

```json
{"displayName":"pf probe A","description":"probe","studyId":"2020-kamgang-congo",
 "studyVersion":"f9388574b5bf8bffe13ea3672cfc4239c96b251e","apiVersion":"1.0.0",
 "isPublic":false,
 "descriptor":{"subset":{"descriptor":[{"entityId":"OBI_0002695","variableId":"CHEBI_24852","type":"stringSet","stringSet":["DDT"]}]},
   "computations":[],"starredVariables":[],"dataTableConfig":{},
   "derivedVariables":["dv-abc-123"]}}
-> {"analysisId":"t4fszEJ"}   HTTP 200
```

The same body with a `DerivedVariableSpec` object in that array was rejected:

```
{"status":"invalid-input","errors":{"general":[],"byKey":{"descriptor":[
 "Cannot deserialize value of type `java.lang.String` from Object value
  (token `JsonToken.START_OBJECT`)\n"]}}}   HTTP 422
```

`GET` on the created analysis returned `"derivedVariables":["dv-abc-123"]`
verbatim, with `numFilters: 1` computed from the subset. The id
`dv-abc-123` does not exist; the service does not check referential
integrity at write time. (The probe analysis was deleted:
`DELETE .../analyses/ClinEpiDB/t4fszEJ` -> HTTP 202, and the list returned
`[]`.)

So the persisted model is:

- An analysis descriptor holds POINTERS: `derivedVariables: string[]`, the ids
  from `/users/{uid}/derived-variables/{project}`.
- Every request that computes anything holds DEFINITIONS: inline
  `DerivedVariableSpec[]`.
- Nothing in the service resolves pointers into definitions. A client that
  loads an analysis must fetch each id from the derived-variables store and
  inline the spec into its merge, compute and visualization bodies itself.

For PathFinder this means an EDA integration that never persists an analysis
never needs the derived-variables store at all: it composes
`DerivedVariableSpec[]` per request. See the integration concept
(`pathfinder: docs/knowledge/eda/pathfinder-integration-concept.md`).

## Access control cuts between subsetting and merging

**live.** `GET /eda/permissions` returns
`perDataset[DS_xxx].actionAuthorization` with `studyMetadata`, `subsetting`,
`visualizations`, `resultsFirstPage`, `resultsAll`. On ClinEpiDB for the
account tested:

- `DS_f9388574b5` (`2020-kamgang-congo`): `resultsAll: true`.
  `/merging/query` works, as every proof above shows.
- `DS_59bedf2966` (`PERCHGAM-1`): `subsetting: true`,
  `visualizations: true`, `resultsFirstPage: true`, `resultsAll: false`.
  `POST /merging/query` on it returned `{"status":"forbidden","message":"HTTP
  403 Forbidden"}` for every request tried, while
  `POST /studies/PERCHGAM-1/entities/EUPATH_0000096/count` returned counts
  normally.

A study can be fully subsettable and countable while row-level merge output is
refused. Check `resultsAll` before planning a merge, and expect 403 rather
than an empty result. 806 of the 984 ClinEpiDB datasets reported
`resultsAll: true` for this account on 2026-08-27.

## Authoring checklist

1. Choose the output `entityId` first. Every other decision follows from it.
2. Variables at or above that entity go straight into `outputVariables`; the
   service broadcasts them.
3. Variables below it need a reduction (`mean`, `sum`, `subsetMembership`,
   `relativeObservationAggregator`) whose target `entityId` is the output
   entity and whose input variables sit in one branch below it.
4. Same-row arithmetic and recoding are transforms; they must live on the
   entity that holds their inputs.
5. Invent `variableId` values that cannot collide with native ids on that
   entity, and never submit the same id twice.
6. Remember filters restrict reduction inputs, and no filter can name a
   derived variable.
7. Confirm `resultsAll` in `GET /permissions` before expecting rows.
8. Do not use `relativeObservationMinTimeInterval` until
   `RelativeObservationCalculator` is registered upstream.
