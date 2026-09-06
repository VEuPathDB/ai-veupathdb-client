---
type: Reference
title: EDA data model
description: The complete study, entity, variable and collection model of the VEuPathDB EDA service, every field on the wire, with real entity trees from three live deployments.
tags: [eda, veupathdb, data-model, studies, entities, variables, collections, raml]
generated: { by: claude-code/opus-5, at: 2026-08-27T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-27T00:00:00Z }
status: stable
---

# EDA data model

The subsetting half of the EDA service exposes four nested concepts: a
**study** owns a tree of **entities**, an entity owns a flat list of
**variables** that themselves form a tree by `parentId`, and an entity may own
**collections** that name a subset of those variables as one axis. Everything
below is either read off the wire on 2026-08-27 or read from source; each claim
says which.

Companion documents: [what-eda-is.md](what-eda-is.md) for the platform,
[subsetting-and-tabular.md](subsetting-and-tabular.md) for the query semantics,
[rest-surface.md](rest-surface.md) for the endpoint list.

## Sources of truth, and their disagreement

| Source | What it is | Authority |
|---|---|---|
| [`schema/library.raml`](https://github.com/VEuPathDB/service-eda/blob/b3bb8bac06de4340b4b2c21d9aa4a94d9b3de61f/schema/library.raml) | generated RAML for every request and response type | declares the surface; over-declares (see below) |
| [`lib-eda-subsetting`](https://github.com/VEuPathDB/lib-eda-subsetting/tree/869c2342990ab14771480c7d0ba70c2676650173/src/main/java/org/veupathdb/service/eda/subset) | Java model + SQL generation | decides behavior |
| [`eda/src/lib/core/types/study.ts`](https://github.com/VEuPathDB/web-monorepo/blob/3e04f4ff37b7a960fcb2edcf3f65dba876d14815/packages/libs/eda/src/lib/core/types/study.ts) | io-ts codecs the official UI validates with | tells you what the UI treats as required |
| live `GET /eda/studies/{id}` | the deployment | final authority for a given site |

The RAML is generated from Java and is a superset of what any deployment
serves. Three concrete disagreements, all verified below: `stringPrefixSet` is
declared and not implemented; `API_VariableScale` is declared and never
populated; `GET /studies/{s}/entities/{e}` omits two fields its own declared
response type marks required.

## Two deployments, two id conventions

`GET /eda/studies` on 2026-08-27:

| Base | Studies | curated | user_submitted |
|---|---|---|---|
| `https://plasmodb.org/eda` | 759 | 747 | 12 |
| `https://clinepidb.org/eda` | 984 | 882 | 102 |
| `https://microbiomedb.org/eda` | 984 | 882 | 102 |

The clinepidb.org and microbiomedb.org responses were byte-identical
(md5 `5bebed2e95029b082ee378518c736743`): one EDA deployment serves the
ClinEpiDB / MicrobiomeDB / VectorBase family, a different one serves the
genomics family. A study id is only meaningful together with the base URL.

Study id shape is a per-family convention, not a protocol rule:

- Genomics family: `STUDY_66f9e70b8a`, paired with `datasetId`
  `DS_66f9e70b8a`.
- ClinEpi family: a curated slug, for example `PRISM0001-1`,
  `2020-kamgang-congo`, `HMPWgs-1`, paired with `datasetId` `DS_0ad509829e`.
  Only 2 of 984 ids on that deployment start with `STUDY_`.
- User-submitted studies on both: id `STUDY_d77d15d7a5` or `e5myTetIliL`,
  `datasetId` `EDAUD_hpI5oZNAwl0AY`, and `sha1hash` is the **empty string**.

So a client must never parse a study id, and must never derive one id from the
other. On the genomics deployment `datasetId == "DS_" + sha1hash[:10]` held for
747/747 curated studies, but `id == "STUDY_" + sha1hash[:10]` held for only
684/747: 63 curated studies carry a study id whose suffix differs from the
dataset id's suffix (for example `STUDY_bf43a6913c` / `DS_dd73524c7e`,
`STUDY_c66bb8d26a` / `DS_2184f85560`). The dataset-to-study mapping is
`GET /eda/permissions` -> `perDataset[datasetId].studyId`, and nothing else.

## Study

### `API_StudyOverview` - one element of `GET /studies`

Declared in library.raml; every field observed live.

| Field | Type | Notes |
|---|---|---|
| `id` | string | study id, see above |
| `datasetId` | string | `DS_*` for curated, `EDAUD_*` for user-submitted |
| `sha1hash` | string | content hash of the loaded study; `""` for user studies |
| `sourceType` | `curated` \| `user_submitted` | `StudySourceType`; picks the DB schema, see Storage |
| `displayName` | string | |
| `shortDisplayName` | string | declared required, **absent on 14 of 759** plasmodb rows |
| `lastModified` | datetime | ISO-8601 with offset, e.g. `2026-05-27T20:00:00-04:00` |
| `description` | string | HTML markup inline; **absent on 2 of 759** plasmodb rows |

Live example (plasmodb.org, 2026-08-27):

```json
{
 "id": "STUDY_ccab256dfb",
 "datasetId": "DS_ccab256dfb",
 "sha1hash": "ccab256dfb7c9562dfa35f36345348ad2f2d5dfa",
 "sourceType": "curated",
 "displayName": "S. cerevisiae transcriptomes in hypoxia and normoxia conditions",
 "shortDisplayName": "Schypoxia",
 "lastModified": "2026-05-27T20:00:00-04:00",
 "description": "<b>General Description:</b>Examination of hypoxia ..."
}
```

Two overview fields are declared required and are sometimes missing, so a
consumer model must make `shortDisplayName` and `description` optional. There
is no `studyVersion` and no `apiVersion` field anywhere in
`API_StudyOverview`, `API_StudyDetail` or the live payloads; `sha1hash` plus
`lastModified` is the whole versioning story, and `sha1hash` is empty for user
studies. Treat `sha1hash` as the cache key for curated studies and
`lastModified` as the only signal for user studies.

### `API_StudyDetail` - `GET /studies/{studyId}`

```
{ "study": { "id", "isUserStudy": boolean, "hasMap": boolean, "rootEntity": API_Entity } }
```

`isUserStudy` and `hasMap` appear only here, not in the overview list. There is
no `datasetId`, no `sha1hash` and no `displayName` in the detail response: the
overview list and the detail call carry disjoint metadata and a client needs
both. Verified live on `STUDY_66f9e70b8a` and `PRISM0001-1`.

### Permissions, and what they gate

`GET /permissions` -> `{ "perDataset": { "<datasetId>": DatasetPermissionEntry } }`.
880 entries on plasmodb.org on 2026-08-27 against 759 studies, so the
permission map is not a study list. Live entry:

```json
"DS_66f9e70b8a": {
 "studyId": "STUDY_66f9e70b8a",
 "sha1Hash": "66f9e70b8a4a9a7efebfe58e0303f2c7f84ec907",
 "isUserStudy": false,
 "displayName": "Transcriptomes of 7 sexual and asexual life stages",
 "shortDisplayName": "3D7 7Stages RNA-Seq",
 "description": "Illumina-based sequencing of <i>P.falciparum</i> 3D7 mRNA ...",
 "type": "end-user",
 "actionAuthorization": {
  "studyMetadata": true, "subsetting": true, "visualizations": true,
  "resultsFirstPage": true, "resultsAll": true
 },
 "isManager": false,
 "accessRequestStatus": "unrequested"
}
```

Note the field is `sha1Hash` here and `sha1hash` in the study overview. The
five `actionAuthorization` flags are the real access axes;
[subsetting-and-tabular.md](subsetting-and-tabular.md) says which endpoint
checks which.

## Entity

An entity is one table of records. The recursive tree type is
`API_Entity = EntityIdGetResponse + children?`, so the entity fields are:

| Field | Type | Notes |
|---|---|---|
| `id` | string | unique within the study; see the id conventions below |
| `idColumnName` | string | the record's primary-key column, `<internal_abbrev>_stable_id` |
| `displayName` | string | |
| `displayNamePlural` | string | |
| `description` | string | literal `"No Entity Description available"` when unset |
| `isManyToOneWithParent` | boolean | |
| `variables` | `API_Variable[]` | flat list, tree by `parentId` |
| `collections` | `API_Collection[]` | `[]` when the entity has none |
| `children` | `API_Entity[]` | absent on leaves; **present only in the study call** |

`idColumnName` is computed, not stored: `Entity.getPKColName()` in
[Entity.java](https://github.com/VEuPathDB/lib-eda-subsetting/blob/869c2342990ab14771480c7d0ba70c2676650173/src/main/java/org/veupathdb/service/eda/subset/model/Entity.java)
returns `getAbbreviation() + "_stable_id"`, where the abbreviation is the
`internal_abbrev` column of `EntityTypeGraph`. This is exactly the column name
that appears in tabular output headers.

**The single-entity GET is lossy.** `GET /studies/{s}/entities/{e}` is declared
to return `EntityIdGetResponse`, which marks `idColumnName` and
`isManyToOneWithParent` required, but the handler copies only six fields.
Verified live on both deployments on 2026-08-27:

```
GET https://clinepidb.org/eda/studies/PRISM0001-1/entities/EUPATH_0000609
GET https://plasmodb.org/eda/studies/STUDY_66f9e70b8a/entities/ENT_fd574cd6
both -> keys ['collections','description','displayName','displayNamePlural','id','variables']
```

The omission is visible in
[`StudiesService.getStudiesEntitiesByStudyIdAndEntityId`](https://github.com/VEuPathDB/service-eda/blob/b3bb8bac06de4340b4b2c21d9aa4a94d9b3de61f/src/main/java/org/veupathdb/service/eda/subset/service/StudiesService.java),
which sets id, description, displayName, displayNamePlural, variables and
collections and nothing else. Consequence: `idColumnName` and
`isManyToOneWithParent` are only reliably available from
`GET /studies/{studyId}`. Fetch the whole tree once, never the per-entity call,
if you need either field.

Entity id conventions, again per family and never parseable:

- Genomics: mostly `ENT_8151325d` (1310 of 1416 entities seen across all 759
  plasmodb studies), plus three other forms verified live - the lowercase
  literal `sample` (`STUDY_bf43a6913c`, idColumnName `sample_stable_id`),
  `GENE_PHENOTYPE_DATA_ENTITY` (`STUDY_dfae3769c3`, idColumnName
  `gnPhntyD_stable_id`), and `RFLP_ISOLATE` (`STUDY_6d31c76b75`, idColumnName
  `RFLPIslt_stable_id`).
- ClinEpi: ontology term ids - `PCO_0000024` (Household), `EUPATH_0000096`
  (Participant), `EUPATH_0000609` (Sample), `OBI_0002623` (Metagenomic
  sequencing assay), `GAZ_00000448` (Collection site).

### Real entity trees

All three fetched 2026-08-27. Format:
`id  "displayName" / "displayNamePlural"  idColumnName manyToOne vars(categories,values) collections`.

**1. Genomics RNA-Seq, `plasmodb.org`, `STUDY_66f9e70b8a`** ("Transcriptomes of
7 sexual and asexual life stages", dataset `DS_66f9e70b8a`). The two-level
sample/assay shape that 649 of 759 plasmodb studies use.

```
ENT_8151325d  "Sample" / "Samples"  sample_stable_id  manyToOne=false  vars=2(0,2)  collections=0
  ENT_fd574cd6  "pfal3D7 htseq counts"  pfl3D7htc_stable_id  manyToOne=true  vars=2(0,2)  collections=0
```

Root variables: `VAR_64c65374` "label" and `VAR_edd8e67c` "parasite stage",
both `string` / `categorical`, 7-value vocabularies. Child variables:
`SEQUENCE_READ_COUNT` (`integer`, `continuous`, rangeMin 0, rangeMax 1684173)
and `VEUPATHDB_GENE_ID` (`string`, `categorical`, 5655-term vocabulary of
`PF3D7_*` ids). The reserved id `VEUPATHDB_GENE_ID` is what the
[EDA-WDK bridge](eda-wdk-bridge.md) keys on.

Entity-count distribution across all 759 plasmodb studies (each study fetched
individually, 3 returned 502): 649 studies have 2 entities, 106 have 1, and
exactly 1 has 5. Maximum tree depth on that deployment is 1.

**2. Genomics with a branch and collections, `plasmodb.org`,
`STUDY_fd06cb37d3`** ("Dual transcriptomes of malaria-infected Gambian children
(RNA-Seq)") - the only 5-entity study on the deployment, and the only one with
collections.

```
ENT_8151325d  "Sample" / "Samples"  sample_stable_id  manyToOne=false  vars=23(0,23)  collections=0
  ENT_12121f8c  "hsapREF Eigengene (wgcna)"   hspREFegng_stable_id  manyToOne=false  vars=24(1,23)  collections=1
  ENT_d282b742  "hsapREF htseq counts"        hspREFhtsc_stable_id  manyToOne=true   vars=3(0,3)    collections=0
  ENT_2caaf3f6  "pfal3D7 Eigengene (wgcna)"   pfl3D7egng_stable_id  manyToOne=false  vars=17(1,16)  collections=1
  ENT_fd574cd6  "pfal3D7 htseq counts"        pfl3D7htsc_stable_id  manyToOne=true   vars=3(0,3)    collections=0
```

Note that `ENT_8151325d` and `ENT_fd574cd6` are the same entity ids as in
`STUDY_66f9e70b8a`: on the genomics deployment entity ids are reused across
studies and are unique only within a study.

**3. ClinEpi cohort, `clinepidb.org`, `PRISM0001-1`** ("PRISM ICEMR Cohort",
dataset `DS_0ad509829e`). Household as root with two sibling subtrees.

```
PCO_0000024      "Household" / "Households"                              Household_stable_id                 manyToOne=true   vars=51(9,42)  collections=0
  EUPATH_0000776 "Household repeated measure" / "... measures"           HouseholdRepeatedMeasure_stable_id  manyToOne=true   vars=25(7,18)  collections=0
  EUPATH_0000096 "Participant" / "Participants"                          Participant_stable_id              manyToOne=true   vars=18(4,14)  collections=0
    EUPATH_0000738 "Participant repeated measure" / "... measures"       ParticipantRepeatedMeasure_stable_id manyToOne=true  vars=54(9,45)  collections=0
      EUPATH_0000609 "Sample" / "Samples"                                Sample_stable_id                   manyToOne=false  vars=18(8,10)  collections=0
```

Unfiltered record counts per entity, from `POST .../count` with `{"filters":[]}`:
Household 331, Household repeated measure 17081, Participant 1421, Participant
repeated measure 48722, Sample 48721.

`isManyToOneWithParent=true` on the root is not a contradiction: the root has no
parent and the flag is simply what the loader wrote.

**4. MicrobiomeDB-style assay entity with collections, `clinepidb.org`,
`HMPWgs-1`** ("HMP phase I (WGS)", dataset `DS_898df5869d`). Reachable
identically on microbiomedb.org.

```
EUPATH_0000096   "Participant" / "Participants"                      Participant_stable_id                     manyToOne=true   vars=6(2,4)        collections=0
  EUPATH_0000609 "Sample" / "Samples"                                Sample_stable_id                          manyToOne=true   vars=7(2,5)        collections=0
    OBI_0002623  "Metagenomic sequencing assay" / "... assays"       WholeMetagenomeSequencingAssay_stable_id   manyToOne=false  vars=4931(19,4912) collections=11
```

**5. VectorBase-style surveillance study with sibling assay entities,
`clinepidb.org`, `2018-tedrow-bloodmeal`** (`hasMap: true`).

```
GAZ_00000448     "Collection site" / "Collection sites"              GeographicLocation_stable_id        manyToOne=true   vars=13(0,13) collections=0
  OBI_0000659    "Collection" / "Collections"                        SampleProtocol_stable_id            manyToOne=true   vars=9(1,8)   collections=0
    EUPATH_0000609 "Sample" / "Samples"                              Sample_stable_id                    manyToOne=true   vars=7(0,7)   collections=0
      OBI_0002732  "Blood meal assay" / "Blood meal assays"          BloodMealAssay_stable_id            manyToOne=true   vars=5(1,4)   collections=0
      OBI_0002728  "Pathogen detection assay" / "... assays"         PathogenDetectionAssay_stable_id    manyToOne=false  vars=8(2,6)   collections=1
      OBI_0001624  "Species identification assay" / "... assays"     SpeciesIdentificationAssay_stable_id manyToOne=false vars=3(1,2)   collections=0
```

Across the first 200 clinepidb studies (2 returned 500:
`PREVIEW_Gates_Namibia_RACD_rfMDA_RAVC_download` and
`PREVIEW_Gates_REACH_LAKANA_rct`), entity counts per study ranged 1 to 8 and
tree depth reached 5, so a client must handle arbitrary depth and branching,
not the two-level genomics shape.

## Variable

Every variable, value-carrying or not, has the `API_Variable` base. Value
variables add `API_VariableWithValues`. `type` is the RAML discriminator.

### Base fields, on every variable

| Field | Type | Live behavior |
|---|---|---|
| `id` | string | unique within the entity |
| `parentId` | string, optional in RAML | present on 59935/59935 variables scanned; see the tree rule below |
| `providerLabel` | string | the loader's source label; JSON-encoded array text such as `"[\"parasite stage\"]"`, or the literal `"No Provider Label available"` |
| `displayName` | string | |
| `definition` | string, optional | present on all scanned; often `""` |
| `displayType` | `API_VariableDisplayType` | see values below |
| `displayOrder` | int64, optional | present on 21462/59935 clinepi and 3827/6729 plasmodb variables |
| `isCategory` | string | declared in RAML, **never present on the wire** |
| `type` | `API_VariableType` | discriminator |
| `hideFrom` | string[] | see values below |

`isCategory` is declared as a required `string` on `API_Variable` in
library.raml and did not appear on any of the 66664 variables scanned across
both deployments. Do not model it. The category test is `type == "category"`.

### Value-variable fields (`API_VariableWithValues`)

| Field | Type | Live behavior |
|---|---|---|
| `dataShape` | `API_VariableDataShape`, optional | present on every value variable scanned |
| `vocabulary` | string[], optional | present on 35737 of 57540 clinepi value variables and on 4159 of 6291 plasmodb value variables. Not restricted to `string`: low-cardinality `integer` variables carry one too, e.g. `EUPATH_0000025` "Sleeping rooms in dwelling count" on `PRISM0001-1` |
| `distinctValuesCount` | int64 | |
| `isTemporal` | boolean | |
| `isFeatured` | boolean | |
| `isMergeKey` | boolean | `true` on the temporal key of a repeated-measure entity, e.g. `EUPATH_0004991` "Observation date" and `EUPATH_0020003` "Collection date" on `PRISM0001-1` |
| `isMultiValued` | boolean | `true` for variables that hold several values per record, e.g. `EUPATH_0000023` "Cooking fuel" on `PRISM0001-1` |
| `imputeZero` | boolean | |
| `hasStudyDependentVocabulary` | boolean, optional | present on every value variable scanned |
| `variableSpecToImputeZeroesFor` | `VariableSpec` | present on 459/57540 clinepi value variables |

Type-specific additions:

- `string` (`API_StringVariable`): nothing.
- `integer` (`API_IntegerVariable`): `distributionDefaults:
  API_IntegerDistributionDefaults`, `units?`.
- `number` (`API_NumberVariable`): `distributionDefaults:
  API_NumberDistributionDefaults`, `units?`, `precision`, `scale?`.
- `date` (`API_DateVariable`): `distributionDefaults:
  API_DateDistributionDefaults`.
- `longitude` (`API_LongitudeVariable`): `precision`.
- `category` (`API_VariablesCategory`): no value fields at all.

`distributionDefaults` shapes:

```
API_NumberDistributionDefaults  { displayRangeMin?, displayRangeMax?, rangeMin?, rangeMax?, binWidth?, binWidthOverride? }          numbers
API_IntegerDistributionDefaults { same six }                                                                                        int64
API_DateDistributionDefaults    { displayRangeMin?, displayRangeMax?, rangeMin?, rangeMax?, binWidth?: integer, binWidthOverride?: integer, binUnits?: BinUnits }
BinUnits = day | week | month | year
```

Live, `distributionDefaults` on `SEQUENCE_READ_COUNT` in `STUDY_66f9e70b8a` was
`{"rangeMin": 0, "rangeMax": 1684173, "binWidth": 54329}` - only three of the
six keys. The io-ts codec in web-monorepo marks `rangeMin`/`rangeMax` required
and carries the comment that `displayRangeMin`/`displayRangeMax` "is supposed to
be required, but the backend isn't populating it", which matches. Model all six
as optional.

### `type` - all six discriminants

`API_VariableType`, from library.raml, all six observed live:

`category`, `string`, `number`, `date`, `longitude`, `integer`

Counts across all 759 plasmodb studies: string 4159, integer 1416, number 680,
category 438, date 27, longitude 9. Across 200 clinepidb studies: number 47590,
string 7953, category 2395, integer 1331, date 505, longitude 161.

The Java enum
[`VariableType`](https://github.com/VEuPathDB/lib-eda-subsetting/blob/869c2342990ab14771480c7d0ba70c2676650173/src/main/java/org/veupathdb/service/eda/subset/model/variable/VariableType.java)
has only five members - STRING, NUMBER, INTEGER, DATE, LONGITUDE - each bound to
one tall-table value column (`string_value`, `number_value`, `number_value`,
`date_value`, `number_value`). `category` is not a value type; it is the
discriminator for a tree node with no data. The io-ts `VariableType` in
web-monorepo likewise omits `category` and codes categories as a separate
`VariableCategory`. There is no `latitude` variable type: latitude is a
`number` variable with `displayType: "latitude"`.

### `dataShape` - all four values

`API_VariableDataShape`: `continuous`, `categorical`, `ordinal`, `binary`.
All four observed live (200 clinepidb studies): continuous 49561, categorical
5220, binary 2281, ordinal 478; plus 2395 variables with no `dataShape` at all,
exactly the 2395 `category` variables. Ordinal carries a meaningful vocabulary
order, e.g. `EUPATH_0000143` "Household wealth index, categorical" on
`PRISM0001-1` with `["Poorest","Middle","Least poor"]`.

`dataShape` selects the distribution algorithm, not the storage: an `integer`
variable can be `categorical` and a `string` variable can be `ordinal`. See
[subsetting-and-tabular.md](subsetting-and-tabular.md), Distribution.

### `displayType` - all six values

`API_VariableDisplayType`: `default`, `hidden`, `multifilter`,
`geoaggregator`, `latitude`, `longitude`. All six observed live across the 200
clinepidb studies: default 58089, geoaggregator 966, multifilter 538, latitude
161, longitude 161, hidden 20. The plasmodb deployment used only default (6657),
geoaggregator (54), latitude (9), longitude (9).

`displayType` is a presentation and filtering axis orthogonal to `type`:
`hasGeographicData()` in
[Variable.java](https://github.com/VEuPathDB/lib-eda-subsetting/blob/869c2342990ab14771480c7d0ba70c2676650173/src/main/java/org/veupathdb/service/eda/subset/model/variable/Variable.java)
is true for LATITUDE, LONGITUDE and GEOAGGREGATOR. The io-ts codec marks
`hidden` "to be deprecated".

`multifilter` is the one value that changes the request shape. A multifilter
variable is a `category` node whose child variables are its sub-filters. Live
on `clinepidb.org/PERCHGAM-1`, entity `EUPATH_0000096`:

```json
{
 "id": "EUPATH_0000321", "parentId": "EUPATH_0000308",
 "providerLabel": "No Provider Label available",
 "displayName": "Diagnosis at discharge",
 "definition": "Based on clinician report. Multiple diagnoses may be selected. Only collected for cases.",
 "displayType": "multifilter", "displayOrder": 4,
 "type": "category", "hideFrom": []
}
```

It has 21 child variables, each a `string` / `categorical` variable with the
one-value vocabulary `["Yes"]`, for example `EUPATH_0015130` "Diarrhea",
`EUPATH_0015135` "Malaria", `EUPATH_0033376` "Pneumonia". The `multiFilter`
filter type targets the parent and names the children; see
[subsetting-and-tabular.md](subsetting-and-tabular.md).

### `hideFrom`

RAML types it `string[]` with no enum. The io-ts codec restricts it to
`download | variableTree | map | everywhere`. Live values observed: `everywhere`
(1350 clinepi, 54 plasmodb) and `variableTree` (56 clinepi, 61 plasmodb).
`download` and `map` were not observed in the scan and are UNVERIFIED as live
values; a scan of every study on both deployments would settle it.
`hideFrom: ["everywhere"]` is live on `EFO_0004950` "Birth date" of
`PRISM0001-1`, entity `EUPATH_0000096` - the variable still exists in the API
payload and can still be filtered on, so `hideFrom` is UI advice, not access
control.

### `scale` - declared, never populated

`API_VariableScale = log | log2 | ln`, an optional field on
`API_NumberVariable`. `scale` appeared on **0** of the 66664 variables scanned
across 759 plasmodb studies and 200 clinepidb studies. The loader column exists
(`DB.Tables.AttributeGraph.Columns.SCALE_COL_NAME = "scale"`), so the path is
real and unused. Do not build on it.

### Impute-zero

Two related fields. `imputeZero` (boolean) says this variable's absent values
should read as zero. `variableSpecToImputeZeroesFor` is a `VariableSpec`
(`{entityId, variableId}`) naming the measure variable that should be
zero-filled for every combination of this variable's vocabulary. Live on
`clinepidb.org/2020-kamgang-congo`, entity `EUPATH_0000609`:

```json
{
 "id": "OBI_0001909", "parentId": "EUPATH_0000609",
 "displayName": "species", "type": "string", "dataShape": "binary",
 "vocabulary": ["Aedes aegypti", "Aedes albopictus"],
 "distinctValuesCount": 2,
 "isFeatured": true, "imputeZero": false,
 "hasStudyDependentVocabulary": true,
 "variableSpecToImputeZeroesFor": { "entityId": "EUPATH_0000609", "variableId": "POPBIO_8000017" }
}
```

Three variables on that entity carry the same spec (`OBI_0001909` species,
`PATO_0000047` biological sex, `UBERON_0000105` life cycle stage): absent
species-by-sex-by-stage combinations mean a specimen count of zero, not missing
data. A client that ignores this field will read absence as missing and
undercount.

### The variable tree

`parentId` builds a tree inside one entity. The roots are the variables whose
`parentId` is not the id of another variable in the same entity, and that
`parentId` value is a synthetic root that **may or may not** equal the entity id:

- `plasmodb.org/STUDY_66f9e70b8a`, entity `ENT_8151325d`: root variables have
  `parentId` `ENT_8151325d`, the entity id.
- `clinepidb.org/HMPWgs-1`, entity `OBI_0002623`: the three root variables
  (`EUPATH_0000815`, `EUPATH_0009246`, `EUPATH_0009250`) have `parentId`
  `OBI_0200000`, which is neither the entity id (`OBI_0002623`) nor any
  variable in the entity.

So the tree-building rule is "a variable whose parentId names no sibling
variable is a root", never "a variable whose parentId equals the entity id".
Depth distribution on `HMPWgs-1`/`OBI_0002623`: 3 roots, 12 at depth 1, 4817 at
depth 2, 99 at depth 3.

`category` variables are the internal nodes. Live example:

```json
{
 "id": "EUPATH_0000815", "parentId": "OBI_0200000",
 "providerLabel": "No Provider Label available",
 "displayName": "CORRAL eukaryote detection and abundance analysis",
 "definition": "A data transformation that uses data from a whole metagenome sequencing assay and CORRAL ... to specify taxa of Eukaryota in a specimen.",
 "displayType": "default", "type": "category", "hideFrom": []
}
```

No `dataShape`, no `vocabulary`, no `distinctValuesCount`. A category cannot be
filtered on and cannot be an output variable; the tabular endpoint answers
`Variable <id> is not a variable with values.` for one.

## Collection

A collection names a set of same-typed variables on one entity as a single
analysis axis - a taxon abundance matrix, a gene expression matrix, a WGCNA
eigengene set. It is what the compute plugins take as input.

`API_Collection`, discriminated on `type`:

| Field | Type | Live behavior |
|---|---|---|
| `id` | string | unique **within the entity only**, see below |
| `displayName` | string | |
| `type` | `API_CollectionType` = `number` \| `date` \| `integer` \| `string` | live: number 375, string 12 across 387 clinepi collections; number 2 on plasmodb |
| `dataShape` | `API_VariableDataShape` | |
| `vocabulary` | string[], optional | present on 76/387, all the string collections |
| `distinctValuesCount` | int64, optional | present on the same 76 |
| `memberVariableIds` | string[] | the member variable ids on this entity |
| `imputeZero` | boolean | `false` on all 387 clinepi and both plasmodb collections scanned |
| `normalizationMethod` | string | see values below; **absent on 66/387** despite being declared required |
| `isCompositional` | boolean | |
| `isProportion` | boolean | |
| `variableSpecToImputeZeroesFor` | `VariableSpec`, optional | not observed on any collection scanned |
| `member` | string | singular noun for one member, e.g. `"taxon"`, `"gene"`, `"pathway"`, `"eigengene"`, `"pathogen"` |
| `memberPlural` | string | e.g. `"taxa"` |

Type-specific: `number` adds `distributionDefaults`, `units`, `precision`;
`integer` adds `distributionDefaults`, `units`; `date` adds
`distributionDefaults`; `string` adds nothing. Live, the number collections all
carried `distributionDefaults`, `units` and `precision` (375/375) and the string
collections carried none of the three.

`normalizationMethod` values observed live across 387 clinepi collections:
`sumToUnity` (161), the literal string `"NULL"` (157), `RPK` (2), `CPM` (1), and
the field absent (66). The literal `"NULL"` is a value, not JSON null; a client
that treats it as a method name will render "NULL" to a user.

### Collection ids are per-entity, not per-study

`plasmodb.org/STUDY_fd06cb37d3` carries the collection id `EUPATH_0005051`
twice, once on `ENT_12121f8c` (23 members) and once on `ENT_2caaf3f6` (16
members). Any reference to a collection therefore needs both ids, which is why
the API's `CollectionSpec` is `{entityId, collectionId}` and the UI's
`VariableCollectionDescriptor` in
[variable.ts](https://github.com/VEuPathDB/web-monorepo/blob/3e04f4ff37b7a960fcb2edcf3f65dba876d14815/packages/libs/eda/src/lib/core/types/variable.ts)
is the same pair.

### A collection is not reliably a variable

On `clinepidb.org/HMPWgs-1`, entity `OBI_0002623`, all 11 collection ids are
**also** present as `category` variables in the same entity, and every member
variable's `parentId` equals its collection id. On
`plasmodb.org/STUDY_fd06cb37d3`, entity `ENT_12121f8c`, the collection is
`EUPATH_0005051` while the category variable that groups its 23 members is
`VAR_6fc75a9f` (same displayName, "Eigengenes"), and `EUPATH_0005051` is not in
`variables` at all. So a client must resolve members through
`memberVariableIds`, and must not assume the collection id names a node in the
variable tree.

### Real collections

**Microbiome relative abundance, `clinepidb.org/HMPWgs-1`, entity
`OBI_0002623`.** Eleven collections; here are their headline fields:

| id | displayName | type | members | member | isCompositional | isProportion | normalizationMethod |
|---|---|---|---|---|---|---|---|
| EUPATH_0009251 | Kingdom | number | 3 | taxon | true | true | sumToUnity |
| EUPATH_0009252 | Phylum | number | 18 | taxon | true | true | sumToUnity |
| EUPATH_0009253 | Class | number | 35 | taxon | true | true | sumToUnity |
| EUPATH_0009254 | Order | number | 55 | taxon | true | true | sumToUnity |
| EUPATH_0009255 | Family | number | 95 | taxon | true | true | sumToUnity |
| EUPATH_0009256 | Genus | number | 224 | taxon | true | true | sumToUnity |
| EUPATH_0009257 | Species | number | 729 | taxon | true | true | sumToUnity |
| EUPATH_0009269 | Normalized number of taxon-specific sequence matches | number | 99 | taxon | false | false | CPM |
| EUPATH_0009247 | 4th level EC metagenome abundance data | number | 2581 | gene | true | false | RPK |
| EUPATH_0009248 | Metagenome enzyme pathway abundance data | number | 487 | pathway | true | false | RPK |
| EUPATH_0009249 | Metagenome enzyme pathway coverage data | number | 487 | pathway | false | false | "NULL" |

The Phylum collection in full:

```json
{
 "id": "EUPATH_0009252",
 "displayName": "Phylum",
 "type": "number",
 "dataShape": "continuous",
 "memberVariableIds": [
  "EUPATH_0009252_Bacteria_Fusobacteria", "EUPATH_0009252_Bacteria_Lentisphaerae",
  "EUPATH_0009252_Eukaryota_Basidiomycota", "EUPATH_0009252_Bacteria_Cyanobacteria",
  "EUPATH_0009252_Bacteria_Verrucomicrobia", "EUPATH_0009252_Bacteria_Actinobacteria",
  "EUPATH_0009252_Bacteria_Chloroflexi", "EUPATH_0009252_Bacteria_Proteobacteria",
  "EUPATH_0009252_Eukaryota_Eukaryota_unclassified", "EUPATH_0009252_Archaea_Euryarchaeota",
  "EUPATH_0009252_Bacteria_Firmicutes", "EUPATH_0009252_Bacteria_Spirochaetes",
  "EUPATH_0009252_Bacteria_Synergistetes", "EUPATH_0009252_Bacteria_Tenericutes",
  "EUPATH_0009252_Eukaryota_Ascomycota", "EUPATH_0009252_Bacteria_Bacteroidetes",
  "EUPATH_0009252_Bacteria_Candidatus_Melainabacteria", "EUPATH_0009252_Bacteria_Chlamydiae"
 ],
 "imputeZero": false,
 "normalizationMethod": "sumToUnity",
 "isCompositional": true,
 "isProportion": true,
 "member": "taxon",
 "memberPlural": "taxa",
 "distributionDefaults": { "rangeMin": 0.000214, "rangeMax": 1.0, "binWidth": 1.0 },
 "units": "",
 "precision": 6
}
```

One member of it:

```json
{
 "id": "EUPATH_0009252_Bacteria_Fusobacteria",
 "parentId": "EUPATH_0009252",
 "providerLabel": "No Provider Label available",
 "displayName": "Fusobacteria",
 "definition": "A data item that is the output of a relative taxonomic abundance analysis for organisms grouped at the level of phylum.",
 "displayType": "default", "displayOrder": 2,
 "type": "number", "hideFrom": [], "dataShape": "continuous",
 "distinctValuesCount": 424,
 "isTemporal": false, "isFeatured": false, "isMergeKey": false,
 "isMultiValued": false, "imputeZero": false, "hasStudyDependentVocabulary": false,
 "distributionDefaults": { "rangeMin": 3e-06, "rangeMax": 0.328339, "binWidth": 0.021889 },
 "units": "", "precision": 6
}
```

The member's `displayName` is the taxon name only; the collection's
`displayName` carries the rank. Rendering a member without its collection loses
the rank.

**Genomics WGCNA eigengenes, `plasmodb.org/STUDY_fd06cb37d3`, entity
`ENT_2caaf3f6`** - the only collection shape on the genomics deployment:

```json
{
 "id": "EUPATH_0005051",
 "displayName": "Eigengenes",
 "type": "number", "dataShape": "continuous",
 "memberVariableIds": ["VAR_e25a2cd5", "VAR_717f7e06", "... 16 total"],
 "imputeZero": false, "isCompositional": false, "isProportion": false,
 "member": "eigengene", "memberPlural": "eigengenes",
 "distributionDefaults": { "rangeMin": -0.3804735, "rangeMax": 0.8449449, "binWidth": 0.101914285714286 },
 "units": "", "precision": 16
}
```

`normalizationMethod` is absent here, one of the 66 such cases.

**A string collection, `clinepidb.org/2018-tedrow-bloodmeal`, entity
`OBI_0002728`** - shows the shape with a vocabulary and no numeric fields:

```json
{
 "id": "POPBIO_8000020",
 "displayName": "malaria pathogen presence/absence",
 "type": "string", "dataShape": "categorical",
 "vocabulary": ["absent", "present"],
 "distinctValuesCount": 2,
 "memberVariableIds": ["POPBIO_8000021", "POPBIO_8000022", "POPBIO_8000023", "POPBIO_8000024"],
 "imputeZero": false, "isCompositional": false, "isProportion": false,
 "member": "pathogen", "memberPlural": "pathogens"
}
```

## Storage

The model is loaded into the application database as per-entity tables named
`<prefix>_<studyAbbrev>_<entityAbbrev>`
([DB.java](https://github.com/VEuPathDB/lib-eda-subsetting/blob/869c2342990ab14771480c7d0ba70c2676650173/src/main/java/org/veupathdb/service/eda/subset/model/db/DB.java)
`applyPrefix`):

| Prefix | Contents |
|---|---|
| `ancestors` | one row per record, one column per ancestor primary key. Drives every cross-entity join. |
| `attributegraph` | the variable metadata - one row per variable, columns `stable_id`, `parent_stable_id`, `provider_label`, `display_name`, `definition`, `vocabulary`, `display_type`, `hidden`, `display_order`, `display_range_min/max`, `range_min/max`, `bin_width_override`, `bin_width_computed`, `is_temporal`, `is_featured`, `is_merge_key`, `impute_zero`, `is_repeated`, `has_values`, `data_type`, `distinct_values_count`, `is_multi_valued`, `data_shape`, `unit`, `precision`, `scale`, `has_study_dependent_vocabulary`, `variable_spec_to_impute_zeroes_for` |
| `attributevalue` | the tall EAV table - `attribute_stable_id`, `string_value`, `date_value`, `number_value` |
| `attributes` | the wide table - one row per record, one column per attribute. Only built for entities with at most 1000 total columns. |
| `collection` | collection metadata, columns mirroring `API_Collection` |
| `collectionattribute` | collection-to-member mapping (`collection_stable_id`, `attribute_stable_id`) |

Plus the study-level tables `study` (`stable_id`, `internal_abbrev`,
`modification_date`) and `EntityTypeGraph` (`stable_id`, `study_stable_id`,
`parent_stable_id`, `internal_abbrev`, `description`, `display_name`,
`display_name_plural`, `has_attribute_collections`,
`is_many_to_one_with_parent`).

The schema is chosen by `sourceType`:
[`StudiesService.resolveSchema`](https://github.com/VEuPathDB/service-eda/blob/b3bb8bac06de4340b4b2c21d9aa4a94d9b3de61f/src/main/java/org/veupathdb/service/eda/subset/service/StudiesService.java)
maps `CURATED` to the app-db schema and `USER_SUBMITTED` to the VDI datasets
schema. That is the whole difference between a curated study and a user
dataset at query time: same model, same endpoints, different schema.

The service also keeps a parallel binary-file store and prefers it when every
requested and filtered variable has a file
(`shouldRunFileBasedSubsetting`); otherwise it falls back to Oracle SQL. Both
paths are declared to produce the same answer, and
`reportConfig.dataSource` (`file` | `database`) asks for one explicitly. See
[subsetting-and-tabular.md](subsetting-and-tabular.md).

## Modeling checklist

For a Pydantic mirror of this model:

1. Discriminate variables on `type` with six members; give `category` no value
   fields.
2. Make optional: `shortDisplayName`, `description` (overview),
   `displayOrder`, `vocabulary`, `scale`, `units`, `precision`,
   `variableSpecToImputeZeroesFor`, `normalizationMethod` (collection), every
   `distributionDefaults` key.
3. Do not model `isCategory`.
4. Model the entity tree as recursive with `children` optional, and take
   `idColumnName` / `isManyToOneWithParent` only from `GET /studies/{id}`.
5. Key any cache on `(baseUrl, studyId, sha1hash)` and fall back to
   `lastModified` when `sha1hash` is empty.
6. Reference a collection as `{entityId, collectionId}`, never by id alone.
7. Treat `normalizationMethod == "NULL"` as absent.
