---
type: Reference
title: EDA subsetting and tabular semantics
description: How EDA filters propagate across the entity tree, and the exact request and response shapes of count, tabular, distribution, root-vocab and filter-aware-metadata, proven with live calls on PlasmoDB and ClinEpiDB.
tags: [eda, subsetting, filters, tabular, distribution, count, semantics]
generated: { by: claude-code/opus-5, at: 2026-08-27T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-27T00:00:00Z }
status: stable
---

# EDA subsetting and tabular semantics

A subset is a flat array of filters. Each filter names one entity and one
variable on that entity. The service turns the array into a SQL join over the
study's entity tree, which is why a filter on one entity changes the record
count of every other entity in the study. This document proves the propagation
rule with live numbers, then gives the exact wire shape of each subsetting
endpoint.

Prerequisite: [data-model.md](data-model.md) for study, entity, variable and
collection. Endpoint inventory: [rest-surface.md](rest-surface.md).

All live calls below ran on 2026-08-27 with a registered VEuPathDB login sent
as `Cookie: Authorization={wdkToken}`. Every call in this document is
reproducible as written.

## The filter union

`API_Filter` is discriminated on `type`, with `entityId` on the base. The
library.raml `API_FilterType` enum lists **eight** values; the deployed service
accepts **seven**.

| `type` | Payload | Verified live |
|---|---|---|
| `stringSet` | `variableId`, `stringSet: string[]` | yes |
| `numberSet` | `variableId`, `numberSet: number[]` | yes |
| `dateSet` | `variableId`, `dateSet: string[]` | yes |
| `numberRange` | `variableId`, `min: number`, `max: number` | yes |
| `dateRange` | `variableId`, `min: string`, `max: string` | yes |
| `longitudeRange` | `variableId`, `left: number`, `right: number` | yes, in [filters.md](filters.md) |
| `multiFilter` | `variableId`, `operation`, `subFilters[]` | yes |
| `stringPrefixSet` | `variableId`, `prefixSet: string[]` | **rejected by both deployments** |

`stringPrefixSet` is declared in
[library.raml](https://github.com/VEuPathDB/service-eda/blob/b3bb8bac06de4340b4b2c21d9aa4a94d9b3de61f/schema/library.raml)
as `API_StringPrefixSetFilter` and is not in the deployed Jackson subtype
registry. Both deployments answered the same way:

```
POST https://plasmodb.org/eda/studies/STUDY_66f9e70b8a/entities/ENT_fd574cd6/count
{"filters":[{"entityId":"ENT_fd574cd6","variableId":"VEUPATHDB_GENE_ID","type":"stringPrefixSet","prefixSet":["PF3D7_01"]}]}
-> {"status":"invalid-input","errors":{"general":[],"byKey":{"filters":[
     "Could not resolve type id 'stringPrefixSet' as a subtype of
      `org.veupathdb.service.eda.generated.model.APIFilter`: known type ids = []
      (for POJO property 'filters')\n"]}}}
```

An unknown `type` produces the identical error, so this is a hard 400 with no
fallback. `longitudeRange` is proven live, including its antimeridian
wrap-around and equal-bounds no-op, in [filters.md](filters.md), which is the
full authoring contract for every filter type; this document only proves the
types it needs for the propagation experiments below.

Range filters are inclusive at both ends and validated against the variable's
declared type. A filter whose `entityId` does not own the named variable is a
400:

```
POST https://clinepidb.org/eda/studies/PRISM0001-1/entities/EUPATH_0000738/count
{"filters":[{"entityId":"EUPATH_0000609","variableId":"EUPATH_0004991","type":"dateSet","dateSet":["2012-01-25T00:00:00"]}]}
-> {"status":"bad-request","message":"Variable 'EUPATH_0004991' is not found"}
```

Live examples of each accepted scalar type, all on 2026-08-27:

```
plasmodb STUDY_66f9e70b8a / ENT_fd574cd6 (39585 rows unfiltered)
  numberSet  SEQUENCE_READ_COUNT in {0,1,2}                  -> count 3826
  numberRange SEQUENCE_READ_COUNT 1000..2000                  -> count 2661

clinepidb PRISM0001-1 / EUPATH_0000738 (48722 rows unfiltered)
  dateRange  EUPATH_0004991 2012-01-01T00:00:00 .. 2012-12-31T00:00:00 -> count 8902
  dateSet    EUPATH_0004991 in {2012-01-25T00:00:00}                   -> count 12
```

### `multiFilter`

`multiFilter` targets a `category` variable whose `displayType` is
`multifilter`, and its `subFilters` name that category's child variables
(see [data-model.md](data-model.md), displayType). Shape:

```json
{
  "entityId": "<entity>",
  "variableId": "<the multifilter category variable>",
  "type": "multiFilter",
  "operation": "union" | "intersect",
  "subFilters": [ { "variableId": "<child>", "stringSet": ["..."] } ]
}
```

`API_MultiFilterSubFilter` has exactly two fields, `variableId` and
`stringSet`; sub-filters cannot be ranges and cannot nest.

The live proof of the operations (union 618, intersect 3, matching two plain
`stringSet` filters, on `clinepidb.org/PERCHGAM-1`) is in
[filters.md](filters.md): `union` is a set OR over the sub-filters, and
`intersect` is exactly equivalent to listing the children as separate
top-level filters, which confirms the next rule.

### Filters compose by AND

The array is ANDed. Live, plasmodb `STUDY_66f9e70b8a`, entity `ENT_fd574cd6`:

```
parasite stage = ring                                          -> 5655
SEQUENCE_READ_COUNT 1000..2000                                 -> 2661
both filters in one array                                      ->  388
```

There is no OR across the array and no negation. The only disjunction in the
filter language is `multiFilter` with `operation: "union"`.

## Cross-entity propagation

**A filter constrains every entity in the study, in both directions along the
tree, and across sibling subtrees through their common ancestor.** There is no
"direction" to configure and no way to opt out.

### The mechanism

[`FilteredResultFactory`](https://github.com/VEuPathDB/lib-eda-subsetting/blob/869c2342990ab14771480c7d0ba70c2676650173/src/main/java/org/veupathdb/service/eda/subset/model/db/FilteredResultFactory.java)
builds the subset in three steps:

1. `pruneTree(tree, filters, outputEntity)` keeps a node if it carries a filter,
   or is the output entity, or is a "pivot" - an otherwise inactive node with
   more than one active child subtree. Everything else is collapsed away. The
   method's own comment states the purpose: a pivot is forced active "so that we
   can join the lower A entities".
2. `generateFilterWithClause` emits, per surviving entity, either
   `SELECT <ancestor pks>, <own pk> FROM ancestors_<study>_<entity>` when that
   entity has no filters, or the INTERSECT of that entity's filter SQL when it
   does.
3. `generateJoiningJoinsClause` inner-joins every surviving parent to every
   surviving child on the parent's primary key, then
   `generateEntityCountSql` selects `count(distinct <outputEntity pk>)`.

Because step 3 is an inner join over ancestor tables, the surviving set of any
entity is the set of its records that have at least one surviving relative on
every filtered branch. Downward and upward fall out of the same join.

### Proof 1 - two entities, both directions

`plasmodb.org`, `STUDY_66f9e70b8a`. Parent `ENT_8151325d` (Sample, 7 records),
child `ENT_fd574cd6` (htseq counts, 39585 records).

```bash
TOK=<wdk token>
S=STUDY_66f9e70b8a
cnt() { curl -s -X POST "https://plasmodb.org/eda/studies/$S/entities/$1/count" \
  -H "Cookie: Authorization=$TOK" -H "Content-Type: application/json" -d "$2"; }
```

| Filters | Sample count | htseq count |
|---|---|---|
| `[]` | 7 | 39585 |
| parent: `parasite stage` = `ring` | 1 | **5655** |
| child: `SEQUENCE_READ_COUNT` 1000..2000 | 7 | 2661 |
| child: `SEQUENCE_READ_COUNT` 1000000..2000000 | **1** | 1 |
| child: `SEQUENCE_READ_COUNT` -5..-1 | **0** | 0 |
| both parent and child filters | 1 | 388 |

Exact bodies:

```json
parent filter: {"filters":[{"entityId":"ENT_8151325d","variableId":"VAR_edd8e67c","type":"stringSet","stringSet":["ring"]}]}
child filter:  {"filters":[{"entityId":"ENT_fd574cd6","variableId":"SEQUENCE_READ_COUNT","type":"numberRange","min":1000000,"max":2000000}]}
```

Downward is obvious: the parent filter takes Samples 7 -> 1 and htseq rows
39585 -> 5655. Upward needs a filter that actually eliminates parents: the
1000..2000 range leaves all 7 Samples because every Sample has at least one gene
in that range, but the 1000000..2000000 range survives in only one Sample and
the Sample count drops to 1, and an unsatisfiable child filter drops the parent
count to 0. Upward propagation is real; a filter that happens to leave every
parent standing is not evidence against it.

### Proof 2 - five entities, sibling subtrees

`clinepidb.org`, `PRISM0001-1`. Tree (see [data-model.md](data-model.md)):
`PCO_0000024` Household -> {`EUPATH_0000776` Household repeated measure,
`EUPATH_0000096` Participant -> `EUPATH_0000738` Participant repeated measure ->
`EUPATH_0000609` Sample}.

```bash
cnt() { curl -s -X POST \
  "https://clinepidb.org/eda/studies/PRISM0001-1/entities/$1/count" \
  -H "Cookie: Authorization=$TOK" -H "Content-Type: application/json" \
  -d "{\"filters\":$2}"; }
```

| Filter | Household | Household rep. measure | Participant | Participant rep. measure | Sample |
|---|---|---|---|---|---|
| none | 331 | 17081 | 1421 | 48722 | 48721 |
| root Household `EUPATH_0000054` = `Nagongera` | 107 | 6369 | 489 | 23044 | 23043 |
| sibling `EUPATH_0000776`.`EUPATH_0000135` 100..500 | 96 | 318 | 470 | 22157 | 22156 |
| leaf `EUPATH_0000609`.`EUPATH_0000048` = `Positive` | 308 | 16469 | 1063 | 9141 | 9141 |

Exact bodies:

```json
root:    [{"entityId":"PCO_0000024","variableId":"EUPATH_0000054","type":"stringSet","stringSet":["Nagongera"]}]
sibling: [{"entityId":"EUPATH_0000776","variableId":"EUPATH_0000135","type":"numberRange","min":100,"max":500}]
leaf:    [{"entityId":"EUPATH_0000609","variableId":"EUPATH_0000048","type":"stringSet","stringSet":["Positive"]}]
```

Read the third row: a filter on mosquito counts, an entity in the *other*
subtree from Sample, cut Samples from 48721 to 22156. The filter went up to the
Household pivot (331 -> 96 households had a qualifying mosquito collection) and
back down the Participant branch. Read the fourth row: a filter on the deepest
entity cut Households 331 -> 308 and the sibling Household-repeated-measure
entity 17081 -> 16469.

### What this means for a caller

- A count is meaningless without the entity it was taken on. "1292 records"
  says nothing; "1292 Participants" says something.
- Adding a filter anywhere can shrink any displayed count. A UI or an agent
  that caches a count per entity must invalidate all of them when the filter
  array changes.
- Entity-level counts are not additive and not comparable across entities.
  48721 Samples over 331 Households is not 147 Samples per Household in any
  useful sense; the Sample count is the count of Sample records in the joined
  subset.
- The join is over ancestor primary keys only. There is no path between two
  entities that do not share an ancestor, because within one study everything
  shares the root.

## `POST /studies/{studyId}/entities/{entityId}/count`

Request `EntityCountPostRequest`, response `EntityCountPostResponse`, both
`additionalProperties: false`:

```
request:  { "filters": API_Filter[] }
response: { "count": <int64> }
```

`filters` is required; `{"filters":[]}` is the unfiltered count. Permission
check: `StudyAccess::allowSubsetting`, i.e. `actionAuthorization.subsetting` in
`GET /permissions`.

## `POST /studies/{studyId}/entities/{entityId}/tabular`

```
request: {
  "filters": API_Filter[],
  "outputVariableIds": string[],
  "reportConfig": API_TabularReportConfig | absent
}
```

Also accepts `application/x-www-form-urlencoded` with the same JSON in a `data`
parameter; that variant additionally sets
`Content-Disposition: attachment; filename="<studyId>_<entityDisplayName>_subsettedData.txt"`,
which the JSON variant does not. Verified live:

```
curl -X POST https://clinepidb.org/eda/studies/PRISM0001-1/entities/EUPATH_0000609/tabular \
  -H "Cookie: Authorization=$TOK" \
  --data-urlencode 'data={"filters":[],"outputVariableIds":["EUPATH_0000047"],"reportConfig":{"paging":{"numRows":2,"offset":0}}}'
-> Content-Type: text/tab-separated-values
-> Content-Disposition: attachment; filename="PRISM0001-1_Sample_subsettedData.txt"
```

### Ancestor primary keys are prepended

The output columns are, in order: the target entity's primary key, then one
column per ancestor **nearest first up to the root**, then the requested
variables in the order given. That order is
`getColumns(outputEntity, outputVariables, ...)` in `FilteredResultFactory`:
output entity pk, then `outputEntity.getAncestorEntities()`, then the
variables.

Live on `PRISM0001-1` entity `EUPATH_0000609` (Sample), which has three
ancestors:

```
POST https://clinepidb.org/eda/studies/PRISM0001-1/entities/EUPATH_0000609/tabular
{"filters":[],"outputVariableIds":["EUPATH_0000048","EUPATH_0000047"],
 "reportConfig":{"paging":{"numRows":2,"offset":0}}}

Sample_stable_id	ParticipantRepeatedMeasure_stable_id	Participant_stable_id	Household_stable_id	EUPATH_0000048	EUPATH_0000047
s_100619085	o_100619085	1006	h_217001002
s_100619128	o_100619128	1006	h_217001002	Negative	14.2
```

Note that the first data row has empty trailing cells: a subset record with no
value for a requested variable still appears, because the value join is a LEFT
join ("so we always get at least one row per subset record"). Absence is an
empty string, not a marker.

`outputVariableIds: []` is legal and returns the primary-key columns only:

```
Sample_stable_id	ParticipantRepeatedMeasure_stable_id	Participant_stable_id	Household_stable_id
s_300118858	o_300118858	3001	h_101009801
```

A `category` variable or an unknown id is a 400:
`{"status":"bad-request","message":"Variable 'NOPE' is not found for entity with ID: 'EUPATH_0000609'"}`.

### `API_TabularReportConfig` - every option

```
{
  "sorting":              [ { "key": "<variableId>", "direction": "asc" | "desc" } ],
  "paging":               { "numRows": <int64>, "offset": <int64> },
  "headerFormat":         "standard" | "display",
  "trimTimeFromDateVars": boolean,
  "dataSource":           "database" | "file"
}
```

Defaults, from
[`TabularReportConfig`](https://github.com/VEuPathDB/lib-eda-subsetting/blob/869c2342990ab14771480c7d0ba70c2676650173/src/main/java/org/veupathdb/service/eda/subset/model/tabular/TabularReportConfig.java):
empty sorting, `numRows` absent (all rows), `offset` 0, `headerFormat`
`standard`, `trimTimeFromDateVars` false, `dataSource` unspecified (the service
chooses). Validation in
[`RequestBundle`](https://github.com/VEuPathDB/service-eda/blob/b3bb8bac06de4340b4b2c21d9aa4a94d9b3de61f/src/main/java/org/veupathdb/service/eda/subset/service/RequestBundle.java):
`numRows` must be a positive integer, `offset` must be non-negative, and every
`sorting[].key` must be a variable of the target entity.

**`paging.offset` without `paging.numRows` is a 500.** `RequestBundle` logs
`apiConfig.getPaging().getNumRows().getClass()` before the null check.
Verified live:

```
{"filters":[...],"outputVariableIds":[...],"reportConfig":{"paging":{"offset":0}}}
-> {"status":"server-error","message":"Cannot invoke \"Object.getClass()\" because the
     return value of \"org.veupathdb.service.eda.generated.model.APIPagingConfig.getNumRows()\"
     is null","requestId":"51m8M9HTbB91vtZYw4QIgG"}
```

Always send both keys of `paging`, or neither.

**`headerFormat`.** `standard` emits machine names: the entity primary-key
column names and the raw variable ids. `display` emits human labels:
`Entity.getDownloadPkColHeader()` is `displayName` with spaces replaced by
underscores plus `_ID`, and `NumberVariable.getDownloadColHeader()` is
`displayName [ (units)] [variableId]`. Same request as above with
`"headerFormat":"display"`:

```
Sample_ID	Participant_repeated_measure_ID	Participant_ID	Household_ID	Plasmodium asexual stages, by microscopy [EUPATH_0000048]	Hemoglobin (g/dL) [EUPATH_0000047]
s_100619085	o_100619085	1006	h_217001002
s_100619128	o_100619128	1006	h_217001002	Negative	14.2
```

The display header contains spaces, commas, parentheses and brackets, so it is
for humans downloading a file, never for a parser.

**`trimTimeFromDateVars`.** Date values carry a zero time by default. Live on
`PRISM0001-1` entity `EUPATH_0000738`, variable `EUPATH_0004991`:

```
default                       o_100819019	1008	h_216001607	2012-01-25T00:00:00
trimTimeFromDateVars: true    o_100819019	1008	h_216001607	2012-01-25
```

**`sorting`.** Sorting forces the "wide table" SQL path. Without sorting the
rows come back ordered by the tabular ORDER BY, which is root ancestor key
first and the entity's own key last. With sorting, Oracle ordering applies and
nulls sort first on `desc`. Live, sorting `EUPATH_0000047` (Hemoglobin):

```
direction asc  -> first values 3, 3.4000001, 3.5
direction desc -> first three rows have an empty Hemoglobin cell
```

If you need "largest first, values only", filter the variable to a range as
well as sorting.

**The >1000-column guard.** Paging or sorting requires the per-entity wide
table, which is not built for entities with more than 1000 total columns
(entity pk + ancestor pks + variables). Live on `clinepidb.org/HMPWgs-1` entity
`OBI_0002623`, which has 4931 variables:

```
reportConfig {"paging":{"numRows":2,"offset":0}}
-> {"status":"bad-request","message":"Tabular requests with paging/sorting are not
     supported on entities with >1000 total columns"}
reportConfig {"headerFormat":"display"}   -> 200, full stream
no reportConfig                            -> 200, full stream
```

The deployed guard fires on paging alone. The HEAD source of
`requiresWideTables()` returns true only for non-empty sorting, so the deployed
build differs from HEAD here; the observable rule is "paging or sorting on a
wide entity is a 400". Practical consequence: you cannot page a
collection-bearing assay entity. Filter it down instead.

**`dataSource`.** `file` and `database` both returned byte-identical output on
`PRISM0001-1` entity `EUPATH_0000609`, which is the contract: the binary-file
subsetting path and the Oracle path are two implementations of one answer. Send
neither unless you are diagnosing a disagreement.

### TSV or JSON

Content negotiation is a single exact string comparison, not real Accept
parsing.
[`TabularResponses.Type.fromAcceptHeader`](https://github.com/VEuPathDB/lib-eda-subsetting/blob/869c2342990ab14771480c7d0ba70c2676650173/src/main/java/org/veupathdb/service/eda/subset/model/tabular/TabularResponses.java)
reads the first `Accept` header value and returns JSON only when it equals
`application/json` exactly; every other value, including a missing header,
returns TSV. There is no `format` query parameter. Verified live:

| `Accept` | Result |
|---|---|
| absent | TSV |
| `application/json` | JSON |
| `application/json, */*` | **TSV** |

So a client whose HTTP library appends `*/*` silently gets TSV. Send the header
literally.

**The JSON body is not the declared shape.** library.raml declares
`EntityTabularPostResponse` as `{ "tabular": string[][] }` for both media
types. What the JSON formatter writes is a bare array of arrays, header row
first:

```
POST .../EUPATH_0000609/tabular   Accept: application/json
{"filters":[],"outputVariableIds":["EUPATH_0000048"],"reportConfig":{"paging":{"numRows":3,"offset":0}}}

[["Sample_stable_id","ParticipantRepeatedMeasure_stable_id","Participant_stable_id","Household_stable_id","EUPATH_0000048"],
 ["s_100619085","o_100619085","1006","h_217001002",""],
 ["s_100619128","o_100619128","1006","h_217001002","Negative"],
 ["s_100619146","o_100619146","1006","h_217001002",""]]
```

Both formats stream and both put the header in the first row. A model built
from the RAML alone will fail to parse the JSON response.

### Permission depends on the paging config

`getTabularAccessPredicate` in `StudiesService`: a request with `offset == 0`
and `numRows` present and `numRows <= 20` needs only
`actionAuthorization.resultsFirstPage`; anything else needs
`actionAuthorization.resultsAll`. The constant is
`MAX_ROWS_FOR_SINGLE_PAGE_ACCESS = 20`. A preview of at most 20 rows is
therefore available on studies whose full download is not.

### `tabular/temporary-result`

library.raml declares `POST .../tabular/temporary-result` returning
`{ "id": ... }` and `GET /temporary-tabular-result/{id}` returning the TSV. Both
returned `404 {"status":"not-found","message":"HTTP 404 Not Found"}` on
`clinepidb.org` on 2026-08-27. Declared, not deployed there; UNVERIFIED
elsewhere, and a POST against another site's `/eda` would settle it.

## `POST .../variables/{variableId}/distribution`

```
request: {
  "filters":  API_Filter[],
  "valueSpec": "count" | "proportion",
  "binSpec":  { "displayRangeMin": any, "displayRangeMax": any, "binWidth": number, "binUnits"?: "day"|"week"|"month"|"year" }
}
response: {
  "histogram":  [ { "value": number, "binStart": string, "binEnd": string, "binLabel": string } ],
  "statistics": { "subsetSize", "subsetMin"?, "subsetMax"?, "subsetMean"?, "numVarValues",
                  "numDistinctValues", "numDistinctEntityRecords", "numMissingCases" }
}
```

`binSpec` is required for `dataShape: continuous` and forbidden otherwise.
`DistributionFactory` throws
`Bin spec is allowed/required only for continuous variables.` for a binSpec on
a non-continuous variable, and a continuous variable with no binSpec returned a
bare `500` live. Both verified:

```
categorical var + binSpec -> {"status":"bad-request","message":"Bin spec is allowed/required only for continuous variables."}
continuous var, no binSpec -> {"status":"server-error","requestId":"3ZW922biluja6aIgpP1U9W"}
```

`valueSpec` defaults to `count` when omitted (the handler patches it, with the
comment "need this until we turn on schema-level checking to enforce
requiredness").

Categorical, live on `PRISM0001-1` / `EUPATH_0000609` / `EUPATH_0000487`
("Plasmodium, by LAMP"), `{"filters":[],"valueSpec":"count"}`:

```json
{
 "histogram": [
  {"value": 25293, "binStart": "Na",        "binEnd": "Na",        "binLabel": "Na"},
  {"value": 17859, "binStart": "Negative",  "binEnd": "Negative",  "binLabel": "Negative"},
  {"value": 10,    "binStart": "No result", "binEnd": "No result", "binLabel": "No result"},
  {"value": 4562,  "binStart": "Positive",  "binEnd": "Positive",  "binLabel": "Positive"}
 ],
 "statistics": {
  "subsetSize": 48721, "numVarValues": 47724, "numDistinctValues": 4,
  "numDistinctEntityRecords": 47724, "numMissingCases": 997
 }
}
```

For a categorical variable `binStart == binEnd == binLabel == the value`, and
`subsetMin`/`subsetMax`/`subsetMean` are absent. Read the statistics carefully:
`subsetSize` 48721 is the subset's record count on this entity,
`numVarValues` 47724 is how many of them have a value, and `numMissingCases`
997 is the difference. A percentage computed against `subsetSize` and one
computed against `numVarValues` differ.

Continuous, same entity, `EUPATH_0000047` ("Hemoglobin"), with
`"binSpec":{"displayRangeMin":0,"displayRangeMax":20,"binWidth":5}`:

```json
{
 "histogram": [
  {"value": 13,    "binStart": "0.0",  "binEnd": "5.0",  "binLabel": "[0.0,5.0)"},
  {"value": 3254,  "binStart": "5.0",  "binEnd": "10.0", "binLabel": "[5.0,10.0)"},
  {"value": 31990, "binStart": "10.0", "binEnd": "15.0", "binLabel": "[10.0,15.0)"},
  {"value": 1313,  "binStart": "15.0", "binEnd": "20.0", "binLabel": "[15.0,20.0)"},
  {"value": 0,     "binStart": "20.0", "binEnd": "25.0", "binLabel": "[20.0,25.0)"}
 ],
 "statistics": {
  "subsetSize": 48721, "subsetMin": 3.0, "subsetMax": 18.9,
  "subsetMean": 12.032154770825814, "numVarValues": 36570,
  "numDistinctValues": 174, "numDistinctEntityRecords": 36570, "numMissingCases": 12151
 }
}
```

Two things to note. `binStart` and `binEnd` are strings even for numeric
variables. And `displayRangeMax: 20` did not bound the histogram: a
`[20.0,25.0)` bin came back with value 0, so the range is a display hint and a
consumer must not assume the last bin ends at `displayRangeMax`.

**`valueSpec: "proportion"` had no observable effect** on either variable. The
`proportion` responses were byte-identical to the `count` responses, integer
counts and all, on both the categorical and the continuous call above. The
enum is honored all the way into `AbstractDistribution.ValueSpec.PROPORTION` in
`DistributionFactory`, so the divergence is below that point and was not traced
(the class lives in `org.gusdb.fgputil`, outside the EDA repos). Treat
proportions as the caller's job: divide by `numVarValues` or `subsetSize` and
say which.

The distribution is subset-sensitive in the normal way: `filters` on any entity
of the study change both the bins and the statistics, per the propagation rule
above.

## `POST .../variables/{variableId}/root-vocab`

```
request:  { "filters": API_Filter[] }          (VocabByRootEntityPostRequest)
response: TSV, no header row, two columns: <root entity primary key>, <value>
```

Purpose, from the RAML description: group this variable's values by the root
entity record that owns the row, so a "megastudy" (a study whose root entity is
itself a study or a site) can present only the vocabulary that applies to each
root record.

Preconditions, from `getVariableForRootVocab`: the variable must have values,
must be `type: "string"`, and must have a non-null `vocabulary`. Otherwise a
500 with a readable message:

```
POST .../variables/EUPATH_0000047/root-vocab   (a number variable)
-> {"status":"server-error","message":"Specified variable must be a string with a vocabulary.","requestId":"48g5m1XGW7YvN5ysq29dfG"}
```

**TSV only.** `Accept: application/json` produced a 500 with a Jersey
`AbstractMethodSelectingRouter` stack trace, because the RAML declares only
`text/tab-separated-values` for this method. Do not send an Accept header.

Live on `clinepidb.org/2020-kamgang-congo`, entity `EUPATH_0000609`, variable
`OBI_0001909` ("species", `hasStudyDependentVocabulary: true`), root entity
`GAZ_00000448`:

```
2020-kamgang-congo_1	Aedes albopictus
2020-kamgang-congo_2	Aedes albopictus
2020-kamgang-congo_3	Aedes albopictus
2020-kamgang-congo_4	Aedes albopictus
2020-kamgang-congo_5	Aedes aegypti
2020-kamgang-congo_5	Aedes albopictus
2020-kamgang-congo_6	Aedes albopictus
2020-kamgang-congo_7	Aedes aegypti
```

One row per (root record, distinct value) pair. Root record 5 has both species,
root records 1 to 4 only have one.

**root-vocab does NOT follow the subset.** It keeps only the filters that
target the same variable as the vocabulary variable and discards the rest.
`RootVocabHandler.queryStudyVocab` says so:

```java
// Limit to filters that explicitly apply to vocabulary variable. This vocabulary should be
// "filter-sensitive" as opposed to the usual "subset-sensitivity". Vocab values that are
// incidentally filtered out by filters that apply to other variables will not be taken into account.
List<Filter> vocabFilters = filters.stream()
  .filter(filter -> filter.filtersOnVariable(vocabularyVariable))
  .collect(Collectors.toList());
```

Verified live on `PRISM0001-1` / `EUPATH_0000609` / `EUPATH_0000487`, which has
331 root records and 4 distinct values:

| Filters | Rows |
|---|---|
| `[]` | 961 |
| a Household filter (`PCO_0000024`.`EUPATH_0000054` = `Nagongera`) | **961, unchanged** |
| a Sample filter on a *different* variable (`EUPATH_0000048` = `Positive`) | **961, unchanged** |
| a filter on `EUPATH_0000487` itself, `["Positive","Negative"]` | **622**, 327 roots, 2 values |

This is the one endpoint in the subsetting group that is not subset-sensitive.
Do not use it to answer "which values remain in my subset" - use
`/distribution` for that.

## `POST /filter-aware-metadata/continuous-variable`

Not under `/studies`. The body is a `DataPluginRequestBase` plus a config:

```
request: {
  "studyId": "<studyId>",
  "filters": API_Filter[],            (optional)
  "derivedVariables": DerivedVariableSpec[],   (optional)
  "config": {
    "variable": { "entityId": "...", "variableId": "..." },
    "metadata": [ "binRanges" | "median" ]
  }
}
response: {
  "binRanges"?: { "equalInterval": LabeledRange[], "quantile": LabeledRange[], "standardDeviation": LabeledRange[] },
  "median"?: number
}
```

library.raml declares `LabeledRange = Range + { label: string }` and
`Range = { min: string, max: string }`. What comes back on the wire is
`{ "binStart": string, "binEnd": string, "binLabel": string }`. This is the
third place library.raml disagrees with the deployment; model the live shape.

Live on `clinepidb.org`, `PRISM0001-1` / `EUPATH_0000609` / `EUPATH_0000047`
with `"metadata":["binRanges","median"]` and no filters:

```json
{
 "median": 12,
 "binRanges": {
  "equalInterval": [
   {"binStart":"3","binEnd":"4.59","binLabel":"[3, 4.59]"},
   {"binStart":"4.59","binEnd":"6.18","binLabel":"(4.59, 6.18]"},
   ... 10 bins to {"binStart":"17.31","binEnd":"18.9","binLabel":"(17.31, 18.9]"}
  ],
  "quantile": [
   {"binStart":"3","binEnd":"10","binLabel":"[3, 10]"},
   {"binStart":"10","binEnd":"10.8","binLabel":"(10, 10.8]"},
   ...
  ],
  "standardDeviation": [
   {"binStart":"8.76196414451514","binEnd":"10.3809820722576","binLabel":"[8.76196414451514, 10.38]"},
   ...
  ]
 }
}
```

Bin counts on that call: `equalInterval` 10, `quantile` 10,
`standardDeviation` 4. Three binning strategies for the same variable over the
same subset, with `binStart`/`binEnd` as strings and half-open interval labels
(the first bin is closed on the left; `binLabel` rounds while `binStart` and
`binEnd` do not). This is what the official UI calls to offer "equal interval /
quantile / standard deviation" binning; it is the companion to
`/distribution`, which takes a fixed `binWidth`.

Unlike `/root-vocab`, this endpoint is genuinely subset-aware. Adding the
Household filter `PCO_0000024`.`EUPATH_0000054` = `Nagongera` to the same
request moved `median` from 12 to 11.9 and the first standard-deviation bin
from `[8.76196414451514, 10.3809820722576]` to
`[8.77999422500708, 10.3399971125035]`.

## The `ss-internal` mirror

library.raml declares one extra route:

```
/ss-internal/studies/{study-id}/entities/{entity-id}/tabular
```

with exactly the `EntityTabularPostRequest` body and
`EntityTabularPostResponse` responses of the public tabular endpoint. Its
handler is
[`InternalClientsService`](https://github.com/VEuPathDB/service-eda/blob/b3bb8bac06de4340b4b2c21d9aa4a94d9b3de61f/src/main/java/org/veupathdb/service/eda/subset/service/InternalClientsService.java),
whose class comment is the whole story:

```java
/**
 * Provides some of the same endpoints as regular StudiesService but without user authorization checking
 */
@Authenticated(allowGuests = true)
public class InternalClientsService implements SsInternalStudiesStudyIdEntitiesEntityId {
```

It calls `StudiesService.handleTabularRequest(..., checkUserPermissions=false, ...)`,
which is the same method the public endpoint calls with `true`. The only
difference between the two routes is the `checkPerms` call.

It exists because the EDA merge and compute services are separate processes
that call subsetting over HTTP on behalf of a request whose permissions the
front service already checked; re-checking inside the cluster would need the
end user's credential to be forwarded, which the internal calls do not do.

Verified live on `clinepidb.org`, 2026-08-27:

```
POST /eda/ss-internal/studies/PRISM0001-1/entities/EUPATH_0000609/tabular   (no credential)
-> 401 {"status":"unauthorized","message":"HTTP 401 Unauthorized"}
POST same, with Cookie: Authorization={wdkToken}
-> 200, identical output to the public endpoint
```

So the route is reachable from outside the cluster and still requires *some*
authenticated identity, but it does not consult
`actionAuthorization.subsetting`, `resultsFirstPage` or `resultsAll` for the
study.

**External clients must use `/studies/{s}/entities/{e}/tabular` and never
`/ss-internal/...`.** Three reasons, in order:

1. It is not an access-control decision a client is allowed to make. The
   public route enforces the study's `actionAuthorization`; the internal route
   is a mirror wired for callers whose authorization was already established
   upstream. Using it means asserting an authorization you did not obtain.
2. It has no compatibility contract. It is not part of the documented client
   surface, it has no permission model to be stable about, and it can move or
   disappear between deployments without notice.
3. It is missing everything else. Only `tabular` is mirrored - no `count`, no
   `distribution`, no `root-vocab` - so nothing can be built on it anyway.

There is a matching internal split elsewhere in the service
(`compute/controller/InternalJobsController.java`, `merge/ServiceInternal.kt`,
`schema/url/compute/internal.raml`); the same rule applies to those.

## Practical rules

1. Always send `filters`, even empty, on `/count` and `/tabular`.
2. Send `paging` with both `numRows` and `offset` or omit `paging` entirely.
3. Send `Accept: application/json` exactly, or accept TSV.
4. Parse the JSON tabular response as `string[][]`, not as
   `{tabular: string[][]}`.
5. Skip the first row of every tabular response; it is the header in both
   formats.
6. Treat an empty cell as "no value for this record", not as an error.
7. Do not page or sort a tabular request on an entity with more than 1000
   columns.
8. Get a variable's remaining values from `/distribution`, never from
   `/root-vocab`.
9. Compute proportions yourself and say what the denominator is.
10. Re-run every count after any filter change, on every entity you display.
