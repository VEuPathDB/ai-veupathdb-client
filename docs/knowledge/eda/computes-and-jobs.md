---
type: Reference
title: EDA computes and jobs
description: Every EDA compute plugin, its exact computeConfig schema, and the asynchronous job lifecycle, live-verified on PlasmoDB with a real differential expression run.
tags: [eda, computes, jobs, differentialexpression, deseq, correlation, dimensionalityreduction, async]
generated: { by: claude-code/opus-5, at: 2026-08-27T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-27T00:00:00Z }
status: stable
---

# EDA computes and jobs

A compute is a server-side R job over a filtered study subset. It is submitted
by POSTing a configuration; the service hashes that configuration into a job id
and runs the job asynchronously. Visualization endpoints then read the job's
output files. See [what-eda-is.md](what-eda-is.md) for the study/entity/variable
model the configurations reference and
[visualizations.md](visualizations.md) for the read side.

Sources. Upstream is `VEuPathDB/service-eda` at commit
`b3bb8bac06de4340b4b2c21d9aa4a94d9b3de61f`, **default branch `master`, not
`main`**. Schema is `schema/library.raml` plus per-endpoint files under
`schema/url/`. Live calls in this document ran against
`https://plasmodb.org/eda` on 2026-08-27 with a registered WDK token.

## Where the compute code lives

`service-eda-compute` was archived in 2024 and its contents are now inside
`service-eda`:

- Controller: `src/main/java/org/veupathdb/service/eda/compute/controller/ComputeController.java`
- Registry: `.../compute/plugins/PluginRegistry.java`
- One package per plugin under `.../compute/plugins/{name}/`
- Job platform glue in Kotlin: `src/main/kotlin/.../compute/EDACompute.kt`,
  `.../compute/util/JobIDs.kt`, `.../compute/service/JobsController.kt`,
  `.../compute/RServe.kt`

The R runs in a separate `veupathdb/rserve` container reached over RServe;
`VEuPathDB/stack-eda-services` `docker-compose.yml` runs exactly one
`veupathdb/service-eda` image plus `veupathdb/rserve`, a RabbitMQ
`compute-queue` and a Postgres `compute-queue-db`. The statistical work is R
packages (`veupathUtils::differentialExpression` and friends), not Java.

`GET /eda/computes` returns the registered plugins. Live on PlasmoDB there are
**9**: `alphadiv`, `betadiv`, `rankedabundance`, `differentialabundance`,
`differentialexpression`, `dimensionalityreduction`, `correlation`,
`selfcorrelation`, `example`. Registration is deployment-wide; whether a compute
is reachable from a project's UI is decided by the app list in
[visualizations.md](visualizations.md), not by this list.

## The request envelope

Every compute POST body is `ComputeRequestBase` plus a plugin-specific `config`
(`schema/url/common/compute.raml`):

| Field | Type | Required | Notes |
|---|---|---|---|
| `studyId` | string | yes | **`STUDY_xxx`, not `DS_xxx`** |
| `filters` | `API_Filter[]` | no | the subset filter array; null is normalized to `[]` |
| `derivedVariables` | `DerivedVariableSpec[]` | yes in schema, tolerated absent | null is normalized to `[]` |
| `config` | per plugin | yes | rejected with 400 if null |

Live-verified: passing the dataset id where the study id belongs is refused.

```
POST /eda/computes/differentialexpression?autostart=false
{"studyId":"DS_e973eadd57", ...}
-> 403 {"status":"forbidden","message":"HTTP 403 Forbidden"}
```

The permission check is `allowVisualizations` on the study
(`ComputeController.requirePermissions`), so an id that is not a study id fails
as forbidden rather than as not-found. `STUDY_e973eadd57` with the same config
returns 200.

Two shared building blocks (`schema/url/common/shared-types.raml`):

- `VariableSpec` = `{entityId, variableId}`, no other properties allowed.
- `CollectionSpec` = `{entityId, collectionId}`, no other properties allowed.
- `LabeledRange` extends `Range` = `{min, max, label}`, all strings.

**`LabeledRange.min` and `.max` are declared required by RAML but are optional
in practice.** `PluginUtil.getRBinListAsString` emits `binStart`/`binEnd` only
when `min` is non-null, and a categorical comparator group of `{"label":
"normal"}` alone was accepted live. Label-only bins name vocabulary values;
labelled bins with `min`/`max` cut a continuous variable.

## The compute catalog

### differentialexpression

Live on all genomics projects plus VectorBase and UniDB. Schema:
`schema/url/compute/computes/differentialExpression.raml`.

```json
{
  "identifierVariable":            { "entityId": "...", "variableId": "..." },
  "valueVariable":                 { "entityId": "...", "variableId": "..." },
  "comparator": {
    "variable":                    { "entityId": "...", "variableId": "..." },
    "groupA": [ { "label": "..." } ],
    "groupB": [ { "label": "..." } ]
  },
  "differentialExpressionMethod":  "DESeq" | "limma",
  "pValueFloor":                   "1e-200"
}
```

| Field | Type | Required | Allowed values |
|---|---|---|---|
| `identifierVariable` | `VariableSpec` | yes | the gene column; upstream UIs restrict it to `VEUPATHDB_GENE_ID` |
| `valueVariable` | `VariableSpec` | yes | the measurement column; upstream UIs restrict it to the five ids in [notebook-presets.md](notebook-presets.md) |
| `comparator.variable` | `VariableSpec` | yes | a sample-level metadata variable |
| `comparator.groupA` | `LabeledRange[]` | yes | the reference group |
| `comparator.groupB` | `LabeledRange[]` | yes | the comparison group |
| `differentialExpressionMethod` | enum | yes | exactly `DESeq` or `limma` |
| `pValueFloor` | string | no | default `1e-200` |

There is **no `collectionVariable` and no `dataFormat`** on this compute. It
reads tall (long, entity-attribute-value) data: one row per gene per sample,
with the gene id in `identifierVariable` and the count in `valueVariable`. The
plugin pivots it to a wide count matrix in R with `data.table::dcast`. A genomics
RNA-Seq study therefore needs no collection at all, and the study used below has
none. (A `collectionVariable` shape does exist, but on
`differentialabundance`, which is the MicrobiomeDB sibling. Comment blocks inside
the WDK bridge plugin still show the older collection-based form; the schema
above is what the service accepts today.)

Semantics read from
`.../compute/plugins/differentialexpression/DifferentialExpressionPlugin.java`:

- `identifierVariable` and `valueVariable` **must be on the same entity**, or
  the plugin throws `IllegalArgumentException`.
- The comparator variable is read from an ancestor entity of that entity and
  deduplicated to one row per sample.
- `DESeq` builds a `veupathUtils::CountDataCollection` with `imputeZero=TRUE`,
  fills missing cells with `NA_integer_`, and aggregates duplicate gene columns
  as `as.integer(round(mean(x)))`. Wire value `DESeq` means DESeq2 (Love et al.,
  2014); the frontend method table maps the key `DESeq` to the display name
  `DESeq2`. `DESeq2` is **not** a valid wire value.
- `limma` builds an `ArrayDataCollection` with `imputeZero=FALSE`, fills with
  `NA_real_`, and aggregates as plain `mean(x)`. This is the antibody-array path.
- `pValueFloor` is passed to R as a number; the default `1e-200` is set in the
  plugin and matches the frontend default.
- The only output file is the statistics result.

### differentialabundance

MicrobiomeDB only. Schema:
`schema/url/compute/computes/differentialAbundance.raml`.

```json
{
  "collectionVariable":           { "entityId": "...", "collectionId": "..." },
  "comparator": { "variable": {...}, "groupA": [...], "groupB": [...] },
  "differentialAbundanceMethod":  "DESeq" | "ANCOMBC" | "Maaslin",
  "pValueFloor":                  "1e-200"
}
```

Collection-based rather than identifier plus value, and it carries a third
method, `ANCOMBC`, plus `Maaslin`. `pValueFloor` is optional.

### dimensionalityreduction

Live on all genomics projects, VectorBase, UniDB and MicrobiomeDB. Schema:
`schema/url/compute/computes/dimensionalityReduction.raml`.

```json
{
  "identifierVariable": { "entityId": "...", "variableId": "..." },
  "valueVariable":      { "entityId": "...", "variableId": "..." },
  "nPCs":               2,
  "dataFormat":         "rawCounts" | "normalizedValues"
}
```

All four fields are required. `dataFormat` is the enum that `differentialexpression`
does not have. Only PCA is implemented; a commented-out
`DimensionalityReductionMethod` enum (`pca`, `pcoa`, `mapper`) marks the intent.

This compute **generates variables**: its `meta` output declares computed
variables `PC1`, `PC2`, ... on the sample entity, which a visualization can then
reference as ordinary `VariableSpec` values. Live on
`STUDY_e973eadd57`:

```
POST /eda/computes/dimensionalityreduction/meta
-> {"variables":[
     {"variableClass":"computed",
      "variableSpec":{"variableId":"PC1","entityId":"ENT_8151325d"},
      "plotReference":"xAxis",
      "displayName":"PC 1 (54.35% variance)",
      "displayRangeMin":"-61.4351512946123",
      "displayRangeMax":"63.5443711576177",
      "dataType":"number","dataShape":"continuous", ...},
     {... "variableId":"PC2", "plotReference":"yAxis",
      "displayName":"PC 2 (12.79% variance)" ...}]}
```

### correlation

Live on all genomics projects except VectorBase, and on MicrobiomeDB. Schema:
`schema/url/compute/computes/correlation.raml`.

```json
{
  "correlationMethod":   "spearman" | "pearson",
  "data1":               { "dataType": "collection", "collectionSpec": {...} },
  "data2":               { "dataType": "metadata" },
  "prefilterThresholds": { "proportionNonZero": 0.5, "variance": 0, "standardDeviation": 0 }
}
```

`data1` and `data2` are each `{dataType, collectionSpec?}` with `dataType` in
`metadata | collection`; `collectionSpec` is present only for `collection`.
`prefilterThresholds` is optional and every member inside it is optional
(`proportionNonZero` between 0 and 1, `variance` and `standardDeviation` at least
0). Three apps drive this one compute with narrowed shapes:
`correlationassayassay` (collection against collection),
`correlationassaymetadata` (collection against metadata), and `correlation`,
the genomics WGCNA app (eigengene collection against metadata or another
collection).

### selfcorrelation

MicrobiomeDB only.

```json
{ "correlationMethod": "spearman" | "pearson" | "sparcc",
  "data1": { "entityId": "...", "collectionId": "..." },
  "prefilterThresholds": {...} }
```

`data1` here is a bare `CollectionSpec`, not a `CorrelationInputData`, and the
method enum gains `sparcc`.

### alphadiv, betadiv, rankedabundance

MicrobiomeDB only, one collection plus one method enum each:

| Compute | Config |
|---|---|
| `alphadiv` | `{collectionVariable: CollectionSpec, alphaDivMethod: 'shannon' \| 'simpson' \| 'evenness'}` |
| `betadiv` | `{collectionVariable: CollectionSpec, betaDivDissimilarityMethod: 'bray' \| 'jaccard' \| 'jsd'}` |
| `rankedabundance` | `{collectionVariable: CollectionSpec, rankingMethod: 'median' \| 'q3' \| 'variance' \| 'max'}` |

### example

A test plugin, registered but on no project.

## Job identity is a hash of the request

`compute/util/JobIDs.kt` is explicit. The job id is the MD5 of the JSON array
`[pluginUrlSegment, keySortedJson(requestBody)]`, rendered as 32 lowercase hex
characters. Null `filters` and `derivedVariables` are replaced with `[]` before
hashing, and object keys are sorted, so property order and omitted empty arrays
do not change the id.

Consequences that matter for a caller:

- The id is **deterministic and derivable client-side**. The same configuration
  always addresses the same job, so a caller never needs to store a job id.
- No user identity enters the hash, so **results are shared across users**. Two
  users with the same subset and configuration get one job.
- Any change to `studyId`, a filter, or one field of `config` is a different
  job.
- Live-verified: deleting a job and re-posting the same body returns the same id
  with status `no-such-job`.

## The lifecycle, live-verified

Study `STUDY_e973eadd57` (dataset `DS_e973eadd57`, "Heat shock response in
sensitive mutants (LRR5, DHC)") on PlasmoDB: sample entity `ENT_8151325d` with
12 samples and a `temperature_condition` variable `VAR_081ab087` with vocabulary
`['febrile', 'normal']` (6 samples each); child entity `ENT_fd574cd6`
("pfal3D7 htseq counts") with `VEUPATHDB_GENE_ID` (5720 distinct),
`SEQUENCE_READ_COUNT_SENSE` and `SEQUENCE_READ_COUNT_ANTISENSE`. No collections.

Request body used throughout (call it `de_body.json`):

```json
{
  "studyId": "STUDY_e973eadd57",
  "filters": [],
  "derivedVariables": [],
  "config": {
    "identifierVariable": { "entityId": "ENT_fd574cd6", "variableId": "VEUPATHDB_GENE_ID" },
    "valueVariable": { "entityId": "ENT_fd574cd6", "variableId": "SEQUENCE_READ_COUNT_SENSE" },
    "comparator": {
      "variable": { "entityId": "ENT_8151325d", "variableId": "VAR_081ab087" },
      "groupA": [ { "label": "normal" } ],
      "groupB": [ { "label": "febrile" } ]
    },
    "differentialExpressionMethod": "DESeq",
    "pValueFloor": "1e-200"
  }
}
```

Observed transitions:

| Time (UTC) | Call | Response |
|---|---|---|
| 08:26 | `POST /computes/differentialexpression?autostart=false` | `{"jobID":"db04204e5386396e1ca2cb78469ab6fb","status":"no-such-job"}` |
| 08:26:58 | `POST /computes/differentialexpression?autostart=true` | `{"jobID":"db04204e5386396e1ca2cb78469ab6fb","status":"queued"}` |
| 08:26:59 | same POST again | `{"jobID":"db04204e5386396e1ca2cb78469ab6fb","status":"in-progress"}` |
| 08:27:33 | `GET /jobs/db04204e5386396e1ca2cb78469ab6fb` | `{"jobID":"db04204e5386396e1ca2cb78469ab6fb","status":"complete"}` |

The whole run took under 35 seconds for 12 samples and 5720 genes. A
`dimensionalityreduction` job on the same data went from `queued` to `complete`
in under 10 seconds; a `correlation` job on
`STUDY_fd06cb37d3` did the same.

Notes on the shape:

- `autostart` defaults to `true` in the RAML. With `autostart=false` the endpoint
  is a pure lookup: it computes the id and reports `no-such-job` if nothing
  exists. This is the safe way to ask "has this been computed" without starting
  work.
- `queued` may carry `queuePosition` (an int32). None of the live responses
  above did, because the job started immediately.
- An `expired` job is resubmitted by a POST with `autostart=true`; with
  `autostart=false` its `expired` status is returned unchanged
  (`EDACompute.getOrSubmitComputeJob`).
- Polling has no push alternative. There is no callback, no SSE and no ETag.

## Job control endpoints

`GET /eda/jobs/{jobId}` where `{jobId}` matches `^[0-9A-Fa-f]{32}$`.

```
GET /eda/jobs/db04204e5386396e1ca2cb78469ab6fb
-> 200 {"jobID":"db04204e5386396e1ca2cb78469ab6fb","status":"complete"}
GET /eda/jobs/00000000000000000000000000000000
-> 404 {"status":"not-found","message":"HTTP 404 Not Found"}
GET /eda/jobs/notahash
-> 404 {"status":"not-found","message":"HTTP 404 Not Found"}
```

A malformed id is a 404, not a 400: `JobsController.toHashID` converts the parse
failure into `NotFoundException`. `JobsController` is annotated
`@Authenticated(allowGuests = false)`, so unlike the compute submission endpoints
the jobs endpoints never accept a guest.

`GET /eda/jobs/{jobId}/files` lists output file names. Live:

| Compute | Files after `complete` |
|---|---|
| `differentialexpression` | `["output-stats"]` |
| `correlation` | `["output-stats"]` |
| `dimensionalityreduction` | `["output-data","output-meta"]` |
| a failed job | `[]` |

Reserved names are fixed in `compute/jobs/ReservedFiles.kt`: inputs
`input-meta`, `input-config`, `input-request`; outputs `output-stats`,
`output-meta`, `output-data`, `error.log`, `exception.log`. A job that has not
finished returns 403 for `files` per the RAML, though a running
`differentialexpression` job already listed `["output-stats"]` live at 08:26:59,
so the file entry can exist before the content is final.

`GET /eda/jobs/{jobId}/files/{fileName}` streams one file as `text/plain` with
`Content-Disposition: attachment; filename={fileName}`. For the completed run
above, `output-stats` was 712323 bytes and byte-identical to both the
`/statistics` endpoint and the volcanoplot response.

`DELETE /eda/jobs/{jobId}` returns 204. It requires the job to be **owned by
this deployment and finished**, otherwise 403 (`JobsController.deleteJobsByJobId`).
Live: deleting a finished failed job returned 204, a subsequent GET returned 404,
and re-posting the identical body returned the same id with `no-such-job`.

Expiration is an **admin operation**, not a caller-visible TTL.
`GET /eda/expire-compute-jobs` (annotated `@AdminRequired`) takes optional
`job-id`, or `study-id` and/or `plugin-name`, expires every matching owned job,
and returns `{numJobsExpired}`. With no argument it expires everything. There is
no documented age-based expiry in the service code; `expired` is a status a
caller must handle but cannot predict.

## Reading compute output

Two families of endpoint, and **the split is per plugin**, not uniform:

| Endpoint | Plugins |
|---|---|
| `POST /computes/{name}/statistics` (JSON) | `differentialexpression`, `differentialabundance`, `correlation`, `selfcorrelation` |
| `POST /computes/{name}/{file}` (text, `file` in `meta` \| `tabular` \| `statistics`) | `example`, `alphadiv`, `betadiv`, `rankedabundance`, `dimensionalityreduction` |

Both take the **same body as the submission**, because that body is how the job
is addressed. Live-verified:

```
POST /eda/computes/differentialexpression/statistics   (body = de_body.json)
-> 200, 712323 bytes:
{"effectSizeLabel": "log2(Fold Change)","pValueFloor": "1e-200",
 "adjustedPValueFloor": null,
 "statistics": [
   {"effectSize":"-0.218035922112735","pValue":"0.350285751849808",
    "adjustedPValue":"0.46960449943855","pointID":"PF3D7_0100100"},
   ...]}

POST /eda/computes/differentialexpression/meta         (body = de_body.json)
-> 404 {"status":"not-found","message":"HTTP 404 Not Found"}
```

The `/{file}` route does not exist for `differentialexpression`, and
`/statistics` does not exist for `dimensionalityreduction` (404 live). The
`meta` and `tabular` names map to `output-meta` and `output-data`;
`ComputeController.getResultFileStreamer` 404s on any other name.

`dimensionalityreduction` tabular output, live, is a TSV keyed by the sample
entity's id column:

```
POST /eda/computes/dimensionalityreduction/tabular
-> ENT_8151325d.sample_stable_id	PC1	PC2
   PB31_37C_Rep1	-61.4351512946123	43.0792816268799
   PB31_37C_Rep2	-50.227058404734	10.9447707441747
   ...
```

`correlation` statistics, live on `STUDY_fd06cb37d3` with the
`ENT_2caaf3f6` / `EUPATH_0005051` eigengene collection against metadata:

```json
{"data1Metadata": "assay","data2Metadata": "sampleMetadata",
 "statistics": [
   {"data1":"ENT_2caaf3f6.VAR_e25a2cd5","data2":"ENT_8151325d.VAR_03116aa2",
    "correlationCoef":"-0.121152248776127","pValue":"0.516192742649685"}, ...]}
```

`adjustedPValue` is optional in `CorrelationPoint` and was absent from every
live row.

One transient: the first `POST /computes/correlation/statistics` immediately
after the status flipped to `complete` returned an nginx `502 Bad Gateway`. Two
retries seconds later returned 200 with 40942 bytes, as did the raw
`/jobs/{id}/files/output-stats`. Treat a read failure right after completion as
retryable rather than as a failed job.

## What the service validates, and what it does not

Validation at submit time is schema shape plus study permission. Semantic
errors are accepted and surface later as a `failed` job. Live-verified:

| Body | Result |
|---|---|
| `differentialExpressionMethod: "DESeq2"` | `422 {"status":"invalid-input","errors":{"general":[],"byKey":{"config":["Cannot deserialize value of type ... DifferentialExpressionMethod from String \"DESeq2\": not one of the values accepted for Enum class: [limma, DESeq]\n"]}}}` |
| `studyId` set to `DS_e973eadd57` | `403 {"status":"forbidden","message":"HTTP 403 Forbidden"}` |
| `valueVariable` on a different entity than `identifierVariable` | `200 {"jobID":"113dec29c65e6ad1b0c1707fa1549593","status":"no-such-job"}`, and once started the job reached `status: failed` within 10 seconds with `files: []` |
| `groupA: [{"label":"NOT_A_VALUE"}]` (not in vocabulary) | `200 ... "status":"no-such-job"`, accepted at submit |

So a caller cannot rely on submission to catch a bad entity pairing or an
out-of-vocabulary group label. Both must be checked against the study metadata
before submitting; the `422` shape (`errors.byKey.config`) is the only
machine-readable rejection.

## Authentication

Identical to the rest of the service, see
[rest-surface.md](rest-surface.md). Live on 2026-08-27 against
`GET /eda/apps`: `Cookie: Authorization={token}` returned 200,
`Authorization: Bearer {token}` returned 200 (this is the form the WDK bridge
plugins send), and no credential returned 401. Both forms work; the bearer form
is confirmed, so the note in [rest-surface.md](rest-surface.md) is settled.

## What this means for PathFinder

The compute model maps cleanly onto the existing durable-task architecture, and
nothing here needs a browser:

- A compute job is addressable by a **client-derivable** MD5. A tool can compute
  the id, ask with `autostart=false`, and skip the job entirely on a cache hit.
- `queued | in-progress | complete | failed | expired | no-such-job` is a
  six-state machine with polling only, which is what `@durable_tool` plus
  `TaskProgressEmitter` already expresses.
- Submission validates almost nothing semantic. Entity pairing, vocabulary
  membership and group non-emptiness are the caller's job, exactly the trust
  posture already applied to WDK parameters.
- The output-file split per plugin (`/statistics` against `/{file}`) means a
  typed client needs a per-compute reader, not one generic one.
