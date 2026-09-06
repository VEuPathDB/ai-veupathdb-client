---
type: Reference
title: EDA filter algebra
description: The complete EDA subset filter algebra - every filter type's JSON shape, AND composition across entities, multiFilter, date and longitude wire semantics, and the service's error responses, proved live on PlasmoDB and ClinEpiDB.
tags: [eda, veupathdb, filters, subsetting, multifilter, error-handling]
generated: { by: claude-code/opus-5, at: 2026-08-27T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-27T00:00:00Z }
status: stable
---

# EDA filter algebra

A subset is a flat JSON array of typed filters. Every entry names one variable
on one entity and carries that type's payload. There is no nesting except
inside `multiFilter`, and there is no OR at the array level. This document is
the authoring contract: an agent that composes filter arrays must obey it or
the service answers 400, 422 or 500.

Two upstreams define the JSON, and they disagree. Both are cited per claim:

- io-ts (consumer side):
  [`web-monorepo` `packages/libs/eda/src/lib/core/types/filter.ts`](https://github.com/VEuPathDB/web-monorepo/blob/3e04f4ff37b7a960fcb2edcf3f65dba876d14815/packages/libs/eda/src/lib/core/types/filter.ts)
  (93 lines, whole file read).
- RAML (service side):
  [`service-eda` `schema/library.raml`](https://github.com/VEuPathDB/service-eda/blob/b3bb8bac06de4340b4b2c21d9aa4a94d9b3de61f/schema/library.raml)
  types `API_Filter`, `API_FilterType` and the seven-plus subtypes, generated
  from `schema/url/common/filter.raml`.
- SQL semantics:
  [`lib-eda-subsetting` `src/main/java/org/veupathdb/service/eda/subset/model/filter/`](https://github.com/VEuPathDB/lib-eda-subsetting/tree/869c2342990ab14771480c7d0ba70c2676650173/src/main/java/org/veupathdb/service/eda/subset/model/filter)
  and `.../model/db/FilteredResultFactory.java`.

Live proofs below ran on 2026-08-27 against `https://plasmodb.org/eda` and
`https://clinepidb.org/eda` with a registered WDK token as
`Cookie: Authorization={token}` (see [REST surface](rest-surface.md) for auth).
Claims are labelled **live** or **schema**.

## The base shape

Every filter carries `entityId`, `variableId`, `type`. The `type` is the
Jackson discriminator on the service side and the io-ts union tag on the
client side.

```json
{ "entityId": "GAZ_00000448", "variableId": "OBI_0001627", "type": "stringSet", "stringSet": ["Republic of the Congo"] }
```

**schema:** the RAML puts only `entityId` and `type` on `API_Filter` and
re-declares `variableId` in each subtype; io-ts puts `entityId` and
`variableId` on `_FilterBase`. The wire result is identical - all subtypes
require all three - but a generated RAML client will show `variableId` as a
per-subtype field.

**live:** unknown extra properties on a filter object are ignored. Adding
`"extraJunk": 1` to a working `stringSet` filter returned the same count
(4011) as without it.

## The seven types

| `type` | payload | applies to variable type |
| --- | --- | --- |
| `stringSet` | `stringSet: string[]` | `string` |
| `numberSet` | `numberSet: number[]` | `number`, `integer` |
| `dateSet` | `dateSet: string[]` | `date` |
| `numberRange` | `min: number, max: number` | `number`, `integer` |
| `dateRange` | `min: string, max: string` | `date` |
| `longitudeRange` | `left: number, right: number` | `longitude` |
| `multiFilter` | `operation, subFilters[]` | a `category` variable whose `displayType` is `multifilter` |

The type must match the variable's declared type. Mismatches are 400, quoted
under [Error behavior](#error-behavior).

### stringSet

Set membership. **live** on PlasmoDB `STUDY_53f554ec6a`
(`GENE_PHENOTYPE_DATA_ENTITY`, 4279 rows):
`VAR_a8ad31c0` ("Success of Genetic Modification", vocabulary `["no","yes"]`)
filtered to `["yes"]` gives 2719, to `["no"]` gives 1560, and 2719 + 1560 =
4279 - the variable is single-valued and the sets partition the entity.

Values are NOT validated against the variable's vocabulary. **live:**
`stringSet: ["maybe"]` on that same variable returns `{"count":0}` with HTTP
200, not an error. The vocabulary check exists in `StringSetFilter` but is
commented out in
[`StringSetFilter.java`](https://github.com/VEuPathDB/lib-eda-subsetting/blob/869c2342990ab14771480c7d0ba70c2676650173/src/main/java/org/veupathdb/service/eda/subset/model/filter/StringSetFilter.java)
with a `FIXME` about validating the database data first. An agent authoring a
filter therefore gets silence, not a correction, when it invents a category
value; the vocabulary in `GET /studies/{id}` is the only guard.

An empty set IS rejected: `{"status":"bad-request","message":"String set
filter: >0 strings must be specified"}`, HTTP 400.

### Multi-valued variables change what stringSet means

`GET /studies/{id}` reports `isMultiValued` on every variable with values
(**schema**: `API_VariableWithValues.isMultiValued: boolean` in the RAML;
**absent from the io-ts** variable type read at the same commit). When it is
true, one entity row holds several values for that variable, and a `stringSet`
filter matches a row if ANY of its values is in the set.

**live**, same study, `VAR_035294d0` ("Species", `isMultiValued: true`,
vocabulary `["P. berghei","P. falciparum","P. yoelii"]`):

```
POST /eda/studies/STUDY_53f554ec6a/entities/GENE_PHENOTYPE_DATA_ENTITY/variables/VAR_035294d0/distribution
{"filters":[],"valueSpec":"count"}
-> histogram P. berghei 4011, P. falciparum 4130, P. yoelii 268
   statistics {"subsetSize":4279,"numVarValues":8409,"numDistinctValues":3,
               "numDistinctEntityRecords":4279,"numMissingCases":0}
```

4011 + 4130 + 268 = 8409 values over 4279 rows. Reading the per-value counts
as a partition of the entity is wrong here, and an agent that sums them to
sanity-check a subset will be off by nearly a factor of two.

### numberSet and numberRange

**live** on ClinEpiDB `2020-kamgang-congo`, entity `OBI_0002695`
("Insecticide resistance assay", 42 rows, 39 with a mortality-rate value):

- Both range bounds are inclusive. `numberRange {min: 100, max: 100}` on
  `APOLLO_SV_00000445` returns 11 - the eleven rows whose value is exactly
  100.0. `{min: 21.92, max: 21.92}` returns 1. `{min: 0, max: 100}` returns
  39, matching `numMissingCases: 3` from the distribution endpoint.
- `numberSet [100.0, 21.92]` returns 12 = 11 + 1.
- `min > max` is not an error: `{min: 100, max: 0}` returns
  `{"count":0}`, HTTP 200.
- On an `integer` variable a fractional `numberSet` member is rejected:
  `{"status":"bad-request","message":"Passed value '60.5' must be an integer
  but is not."}`, HTTP 400.
- On an `integer` variable fractional range bounds ARE accepted and snapped
  inward. `{min: 59.5, max: 60.5}` on `EUPATH_0043064` returned 39, the same
  as `{min: 60, max: 60}` and `numberSet [60]`. **schema:** `NumberRangeFilter`
  calls `getValidatedSubtypeForInclusiveRangeBoundary(min, MIN)` and
  `(max, MAX)`, which round the boundary toward the interior.

### dateSet and dateRange - the wire format is not a date

**live.** The wire format is `YYYY-MM-DDTHH:mm:ss`. A bare `YYYY-MM-DD` is a
server error, not a 400:

```
POST /eda/studies/2020-kamgang-congo/entities/OBI_0000659/count
{"filters":[{"entityId":"OBI_0000659","variableId":"EUPATH_0043256",
             "type":"dateRange","min":"2017-05-05","max":"2017-05-08"}]}
-> HTTP 500 {"status":"server-error","message":"Can't parse date/time string: 2017-05-05",
             "requestId":"4HQSoRw9nQo3rwwigaAFzW"}
```

The same request with `"2017-05-05T00:00:00"` / `"2017-05-08T00:00:00"`
returns `{"count":3}`. A trailing `Z` and a `.000Z` millisecond field are both
accepted and give the same 3. `dateSet` behaves identically: bare dates 500,
`["2017-05-05T00:00:00","2017-05-11T00:00:00"]` returns 2.

This is a trap for a model, because the study metadata for the same variable
prints bare dates. `EUPATH_0043256` reports
`distributionDefaults: {"rangeMin":"2017-05-05","rangeMax":"2017-05-11",
"binWidth":1,"binUnits":"day"}` and a vocabulary of `["2017-05-05",
"2017-05-08", ...]`. Copying a bound straight out of the metadata into a
filter produces a 500. Append `T00:00:00`.

Bounds are inclusive: `{min:"2017-05-05T00:00:00", max:"2017-05-05T00:00:00"}`
returns 1, and the full window `2017-05-05` to `2017-05-11` returns all 7
collection rows. `min > max` returns `{"count":0}`, HTTP 200. An unparseable
string is 500 regardless of shape (`"05/05/2017"` -> the same
`Can't parse date/time string` body).

**schema:** `DateRangeFilter` builds
`TO_DATE('{ISO_DATE_TIME}', 'YYYY-MM-DD"T"HH24:MI:SS')` and compares with
`>=` / `<=`, which is where the format requirement comes from.

### longitudeRange wraps at the antimeridian

`left` and `right`, not `min`/`max`, and the order is meaningful.
**schema**, from
[`LongitudeRangeFilter.java`](https://github.com/VEuPathDB/lib-eda-subsetting/blob/869c2342990ab14771480c7d0ba70c2676650173/src/main/java/org/veupathdb/service/eda/subset/model/filter/LongitudeRangeFilter.java):

- `abs(left - right) < 1e-8` emits `AND 1 = 1` - a no-op filter that keeps
  every row.
- `left < right` emits `value >= left AND value <= right`.
- `left > right` emits `value >= left OR value <= right` - the wrap-around
  window that crosses 180/-180.

**live** on `2020-kamgang-congo` entity `GAZ_00000448` (7 sites). The full
longitude column, read with
`POST /entities/GAZ_00000448/tabular {"filters":[],"outputVariableIds":["OBI_0001621","OBI_0001620","OBI_0001627"]}`:

```
2020-kamgang-congo_1  15.6322
2020-kamgang-congo_2  15.9114
2020-kamgang-congo_3  19.6258
2020-kamgang-congo_4  16.0494
2020-kamgang-congo_5  15.2897
2020-kamgang-congo_6  15.8736
2020-kamgang-congo_7  15.75
```

| filter | count | why |
| --- | --- | --- |
| `left: 15, right: 16` | 5 | the five values inside [15, 16] |
| `left: 16, right: 15` | 2 | `>= 16 OR <= 15` - only 16.0494 and 19.6258 |
| `left: 170, right: -170` | 0 | a real antimeridian window, no data there |
| `left: -170, right: 170` | 7 | the whole world the normal way |
| `left: 0, right: 0` | 7 | equal bounds, no-op |
| `left: 15.5, right: 15.5` | 7 | equal bounds, no-op even mid-data |

The equal-bounds no-op is the surprise: a degenerate longitude window does not
select the rows at that longitude and does not error. It silently selects
everything.

A `longitudeRange` on a plain `number` latitude variable is refused:
`{"status":"bad-request","message":"Variable OBI_0001620 of entity
GAZ_00000448 is not a longitude variable."}`. A `numberRange` on the
`longitude` variable is refused symmetrically:
`"... is not a number or integer variable."` Longitude is its own type on both
axes.

### multiFilter

The one nested type. It targets a `category` variable - a grouping node in the
variable tree with no data of its own - whose `displayType` is `multifilter`,
and its `subFilters` name that category's child variables. Each sub-filter is
a bare `{variableId, stringSet}` with no `entityId` and no `type`: the parent
filter's `entityId` applies and the sub-filter is always a string set.

```json
{
  "entityId": "EUPATH_0000096",
  "variableId": "EUPATH_0000321",
  "type": "multiFilter",
  "operation": "union",
  "subFilters": [
    { "variableId": "EUPATH_0015135", "stringSet": ["Yes"] },
    { "variableId": "EUPATH_0033376", "stringSet": ["Yes"] }
  ]
}
```

`operation` is `union` or `intersect` (**schema**: `API_BooleanOperationType`;
io-ts `t.keyof({union, intersect})`; `MultiFilter.MultiFilterOperation` maps
them to the SQL keywords `UNION` and `INTERSECT` over the sub-filter selects).

Finding one: walk the entity's `variables`, keep those with
`displayType == "multifilter"`, and their children are the variables whose
`parentId` equals the category id. **live** on ClinEpiDB `PERCHGAM-1`
(4 entities, 121 multifilter variables). `EUPATH_0000321` ("Diagnosis at
discharge", `type: "category"`, `displayType: "multifilter"`) has 21 children,
each a `string`/`categorical` variable with vocabulary `["Yes"]` - the shape
that makes union and intersect meaningful.

**live** proof of the operations on entity `EUPATH_0000096` ("Participant",
1292 rows), children `EUPATH_0015135` ("Malaria") and `EUPATH_0033376`
("Pneumonia"):

| request | count |
| --- | --- |
| no filters | 1292 |
| `stringSet` Malaria = Yes | 9 |
| `stringSet` Pneumonia = Yes | 612 |
| `multiFilter` `union` of both | 618 |
| `multiFilter` `intersect` of both | 3 |
| two separate `stringSet` filters (array AND) | 3 |

618 = 9 + 612 - 3, and `intersect` reproduces exactly what two array entries
already do. `multiFilter` therefore earns its existence only for `union`: it
is the sole way to express OR anywhere in the algebra.

Validation is strict on the multifilter target, unlike `stringSet` values:

- a `variableId` that is not a multifilter category ->
  `{"status":"bad-request","message":"Multifilter variable does not have
  display type 'multifilter': EUPATH_0015135"}`, and the same for a
  `geoaggregator` variable.
- a sub-filter naming an unknown variable ->
  `"Multifilter includes subfilter with invalid variable: VAR_bogus"`.
- `subFilters: []` -> `"Multifilter may not have an empty list of
  subFilters"`.
- `operation: "xor"` -> HTTP 422 with a Jackson enum message.

### stringPrefixSet exists upstream and is not deployed

**schema:** `API_FilterType` in `library.raml` at HEAD lists eight values
including `stringPrefixSet`, and `API_StringPrefixSetFilter` is
`{variableId, prefixSet: string[]}`.
[`StringPrefixSetFilter.java`](https://github.com/VEuPathDB/lib-eda-subsetting/blob/869c2342990ab14771480c7d0ba70c2676650173/src/main/java/org/veupathdb/service/eda/subset/model/filter/StringPrefixSetFilter.java)
implements it as OR over `value LIKE 'prefix%' ESCAPE '\'`, motivated by
mixed-precision geohash shapes; empty sets and empty prefixes throw.
`service-eda` `ApiConversionUtil.unpackStringPrefixSetFilter` wires it up.

**It is absent from the io-ts union**, and **live** on PlasmoDB it is
rejected by the deployed build:

```
{"status":"invalid-input","errors":{"general":[],"byKey":{"filters":[
 "Could not resolve type id 'stringPrefixSet' as a subtype of
  `org.veupathdb.service.eda.generated.model.APIFilter`: known type ids = []
  (for POJO property 'filters')\n"]}}}   HTTP 422
```

So the algebra PathFinder can use today is seven types. Treat
`stringPrefixSet` as forward-looking: schema-present, source-present,
wire-absent.

## Composition: the array is AND, per entity and across entities

**schema.**
[`FilteredResultFactory.generateFilterWithClause`](https://github.com/VEuPathDB/lib-eda-subsetting/blob/869c2342990ab14771480c7d0ba70c2676650173/src/main/java/org/veupathdb/service/eda/subset/model/db/FilteredResultFactory.java)
groups the array by `entityId`, joins each group's per-filter selects with SQL
`INTERSECT`, and emits one `WITH` clause per entity. `pruneTree` then keeps
only entities that carry a filter, are the output entity, or are the pivot
needed to join two active subtrees, and the surviving tree is joined on
ancestor primary keys. There is no code path that ORs two array entries.

**live**, single entity, PlasmoDB `STUDY_53f554ec6a`
(`GENE_PHENOTYPE_DATA_ENTITY`):

| filters | count |
| --- | --- |
| none | 4279 |
| A: `VAR_035294d0` in `["P. berghei"]` | 4011 |
| B: `VAR_a8ad31c0` in `["yes"]` | 2719 |
| A and B in one array | 2501 |

2501 <= min(4011, 2719), and 2501 is strictly below both, so the array
narrowed rather than replaced.

**live**, cross entity, ClinEpiDB `2020-kamgang-congo`. Unfiltered row counts
are 7 sites (`GAZ_00000448`), 7 collections (`OBI_0000659`), 17 samples
(`EUPATH_0000609`), 42 resistance assays (`OBI_0002695`).

| filter array | counted on | count |
| --- | --- | --- |
| `OBI_0002695.CHEBI_24852` in `["DDT"]` | `OBI_0002695` | 8 |
| `OBI_0002695.CHEBI_24852` in `["DDT"]` | `GAZ_00000448` | 7 |
| `GAZ_00000448.OBI_0001627` in `["Republic of the Congo"]` | `GAZ_00000448` | 6 |
| `GAZ_00000448.OBI_0001627` in `["Republic of the Congo"]` | `OBI_0002695` | 37 |
| both of the above | `OBI_0002695` | 7 |

A filter propagates both ways through the tree: a descendant filter restricts
the ancestor entity to ancestors that have a surviving descendant (all 7 sites
have a DDT assay), and an ancestor filter restricts the descendant entity to
descendants under a surviving ancestor (37 of 42 assays). The count endpoint's
entity is what is being counted; the filters' entities are independent of it.

### Two filters on the same variable

They AND, exactly like filters on different variables, and the outcome depends
on `isMultiValued`.

**live**, single-valued `VAR_a8ad31c0` (vocabulary `["no","yes"]`):
`["yes"]` AND `["no"]` in one array returns `{"count":0}`. A single row cannot
hold two values, so disjoint sets on a single-valued variable are a
guaranteed empty subset - no error, just zero. This is the most likely way for
an agent to silently produce nothing.

**live**, multi-valued `VAR_035294d0`:

| filters | count |
| --- | --- |
| `["P. berghei"]` | 4011 |
| `["P. falciparum"]` | 4130 |
| `["P. berghei"]` AND `["P. falciparum"]` | 3883 |
| `["P. berghei","P. falciparum"]` AND `["P. falciparum","P. yoelii"]` | 4130 |

3883 rows carry both species. The rule is per filter: a row survives if it has
any value in set 1 AND any value in set 2. To express "berghei or falciparum"
use one filter with both members, never two filters.

## Where the array lives

- Subsetting: the request body of
  `POST /studies/{s}/entities/{e}/count`, `.../tabular`,
  `.../variables/{v}/distribution`, `.../variables/{v}/root-vocab`
  (**schema**: `EntityTabularPostRequest.filters: API_Filter[]`,
  `VariableDistributionPostRequest.filters`).
- Merging: `MergedEntityTabularPostRequest.filters` - see
  [derived variables and merging](derived-variables-and-merging.md).
- Computes and visualization data: `ComputeRequestBase.filters` (optional) and
  `DataPluginRequestBase.filters` (optional).
- Derived variables: `SubsetMembershipConfig.subsetFilters` and
  `RelatedObservationMinTimeIntervalConfig.relatedObservationsSubset` embed a
  filter array as a plugin's own filter override.
- Persisted analyses: `descriptor.subset.descriptor`
  (**schema**: `object[]` in the RAML, `t.array(Filter)` in io-ts). The
  [EDA-WDK bridge](eda-wdk-bridge.md) carries this same array into a WDK
  parameter.

The filter array cannot reference a derived variable. Proof and consequences
are in [derived variables and merging](derived-variables-and-merging.md).

## Error behavior

All **live** on 2026-08-27, from
`POST /eda/studies/{study}/entities/{entity}/count`. An agent that authors
filters will hit these, and the three status classes mean different things.

| what was wrong | status | body |
| --- | --- | --- |
| unknown `variableId` | 400 | `{"status":"bad-request","message":"Variable 'VAR_deadbeef' is not found"}` |
| real variable, wrong `entityId` for it | 400 | `{"status":"bad-request","message":"Variable 'CHEBI_24852' is not found"}` |
| unknown `entityId` | 400 | `{"status":"bad-request","message":"A filter references an unfound entity ID: ENT_nope"}` |
| `numberRange` on a `string` variable | 400 | `{"status":"bad-request","message":"Variable VAR_a8ad31c0 of entity GENE_PHENOTYPE_DATA_ENTITY is not a number or integer variable."}` |
| `stringSet` on a `number` variable | 400 | `... is not a string variable.` |
| `dateRange` on a `string` variable | 400 | `... is not a date variable.` |
| `stringSet` on a `category` variable | 400 | `... is not a string variable.` |
| `stringSet: []` (or the key omitted) | 400 | `{"status":"bad-request","message":"String set filter: >0 strings must be specified"}` |
| unknown `type` value | 422 | see the two 422 bodies quoted in full below the table |
| bad `multiFilter.operation` | 422 | see the two 422 bodies quoted in full below the table |
| bare `YYYY-MM-DD` date bound | 500 | `{"status":"server-error","message":"Can't parse date/time string: 2017-05-05","requestId":"..."}` |
| out-of-vocabulary `stringSet` value | 200 | `{"count":0}` |
| `min > max` on a range | 200 | `{"count":0}` |
| degenerate `longitudeRange` (`left == right`) | 200 | full unfiltered count |
| unknown extra property on a filter | 200 | ignored |

The two 422 bodies in full, as returned:

```
type: "stringBag"
{"status":"invalid-input","errors":{"general":[],"byKey":{"filters":[
 "Could not resolve type id 'stringBag' as a subtype of
  `org.veupathdb.service.eda.generated.model.APIFilter`: known type ids = []
  (for POJO property 'filters')\n"]}}}

operation: "xor"
{"status":"invalid-input","errors":{"general":[],"byKey":{"filters":[
 "Cannot deserialize value of type
  `org.veupathdb.service.eda.generated.model.APIBooleanOperationType`
  from String \"xor\": not one of the values accepted for Enum class:
  [intersect, union]\n"]}}}
```

Reading the classes:

- **422** means the JSON did not deserialize into `APIFilter`. The whole
  request was rejected before any variable was resolved. This is the only
  class where the message names a Java type, and the `known type ids = []`
  fragment is an artifact of the discriminator registry, not a hint that no
  types exist.
- **400** means the JSON was well formed and a name or a type did not check
  out. The message is specific enough to repair: it names the offending id or
  the expected variable type.
- **500** means only one thing so far - an unparseable date string. Treat it
  as an author error, not an outage.
- **200 with an unexpected count** is the dangerous class. Out-of-vocabulary
  values, inverted ranges, disjoint filters on one single-valued variable, and
  degenerate longitude windows all produce a plausible-looking answer. There
  is no server-side guard; the vocabulary and range metadata from
  `GET /studies/{id}` is the only pre-flight check available.

## Authoring checklist

1. Resolve `entityId` and `variableId` together from `GET /studies/{id}`. A
   variable id is only valid on the entity that declares it.
2. Pick `type` from the variable's `type`, not from what the value looks like.
   `longitude` is not `number`; `category` has no values at all.
3. For `date`, append `T00:00:00` to every bound and set member.
4. For `stringSet`, check each value against the variable's `vocabulary`
   yourself; the service will not.
5. Check `isMultiValued` before reasoning about counts or about two filters on
   one variable.
6. Express OR with one `stringSet` holding several members, or with
   `multiFilter` `operation: "union"` when the alternatives are different
   variables under one multifilter category. Never with two array entries.
7. Never place a range's `min` above its `max`, and never set
   `longitudeRange.left == right`, expecting either to mean "nothing" or
   "exactly here".
