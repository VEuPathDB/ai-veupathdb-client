---
type: Reference
title: What EDA is
description: VEuPathDB's Exploratory Data Analysis platform, its study/entity/variable data model, filter algebra, computes, and analyses, verified live on PlasmoDB.
tags: [eda, veupathdb, data-model, studies, entities, variables, computes]
generated: { by: claude-code/fable-5, at: 2026-08-27T00:00:00Z }
verified: { by: claude-code/fable-5, at: 2026-08-27T00:00:00Z }
status: stable
---

# What EDA is

EDA (Exploratory Data Analysis) is VEuPathDB's second platform, alongside WDK.
Where WDK answers "which records match this search" over fixed record types
(genes, transcripts, organisms), EDA answers "what does this study's data look
like": subset a study's samples or observations by variable filters, compute
statistics over the subset, and visualize the result. It powers ClinEpiDB and
MicrobiomeDB outright, MapVEu on VectorBase, and since roughly 2025 it also
holds the genomics sites' experiment data (RNA-Seq counts, phenotype scores,
antibody arrays, SNP calls, ChIP peaks).

On 2026-08-27, `GET https://plasmodb.org/eda/studies` returned **759 studies**,
and the list spans projects (P. falciparum RNA-Seq next to T. cruzi and
Z. tritici studies): one EDA deployment serves study metadata across the
genomics family, and each site's WDK exposes only the datasets it presents.
There are at least two independent deployments: the genomics one (759 studies)
and the ClinEpiDB/MicrobiomeDB/VectorBase one (984 studies);
`https://clinepidb.org/eda/studies` and `https://microbiomedb.org/eda/studies`
returned byte-identical payloads (md5 `5bebed2e95029b082ee378518c736743`), so a
study id is only meaningful together with its base URL.

## The services

The runtime is `VEuPathDB/service-eda` (Java/Kotlin, JaxRS, RAML-defined),
deployed at `https://{site}/eda` (default branch `master`; raw URLs with
`/main/` 404). It absorbed what used to be separate repos: subsetting, merging
(derived variables), data/apps (visualization data), computes (the archived
`service-eda-compute` now lives under its `compute/` package; the statistical
work is R packages run in a separate `veupathdb/rserve` container), user
analyses, dataset access/permissions, and download. The full compose stack is
`VEuPathDB/stack-eda-services`. Java query access to the EDA database is
`VEuPathDB/lib-eda-subsetting`.

The only API documentation is the generated RAML page
(https://veupathdb.github.io/service-eda/api.html, built from `api.raml` plus
`schema/library.raml` in the repo). There is no prose semantics document; the
semantics below were read from source and confirmed live.

## The data model

A **study** is the unit of loading and permission. Its `id` is opaque and
follows a per-deployment convention: `STUDY_66f9e70b8a` on the genomics sites,
a curated slug such as `PRISM0001-1` or `2020-kamgang-congo` on the ClinEpiDB
family (only 2 of 984 ids there start with `STUDY_`). It pairs with a
**dataset** whose id is `DS_xxx` for curated studies and `EDAUD_xxx` for
user-submitted ones; the dataset id is the currency of WDK dataset presenters
and of the `/eda/permissions` map. Never parse either id and never derive one
from the other (63 of 747 curated PlasmoDB studies have a study-id suffix that
differs from the dataset-id suffix); `GET /eda/permissions` ->
`perDataset[datasetId].studyId` is the mapping. The full field inventory is in
[data-model.md](data-model.md).

A study owns a **tree of entities**. An entity is a table of rows (samples,
participants, observations, genes-with-data) with:

- `variables`: typed columns. Types seen in the wire: `string`, `number`,
  `integer`, `date`, `longitude`, `category` (a grouping node in the variable
  tree, no data). Variables carry `dataShape` (continuous, categorical,
  ordinal, binary), vocabularies for categoricals, ranges for numerics,
  `isMultiValued` (one row may hold several values, which changes what a
  `stringSet` filter matches; see [filters.md](filters.md)), and `displayType`
  UI hints (default, hidden, multifilter, geoaggregator, latitude, longitude).
- `collections`: named groups of variables treated as one axis (e.g. a taxon
  abundance matrix or a WGCNA eigengene set). Collections carry
  `isCompositional`, `isProportion`, `normalizationMethod`, `imputeZero`, plus
  `memberVariableIds`, `member`/`memberPlural` and `type`/`dataShape`.
  `normalizationMethod` is declared required but is absent on 66 of 387 live
  ClinEpiDB collections and is the literal string `"NULL"` on 157 more. A
  collection id is unique only within an entity, so a reference needs
  `{entityId, collectionId}`. The collection-based computes (differential
  abundance, diversity, correlation) take a `collectionVariable`
  ({entityId, collectionId}) as input; the genomics differential-expression
  and PCA computes instead take `identifierVariable` + `valueVariable` over
  tall data and need no collection (see
  [computes-and-jobs.md](computes-and-jobs.md)).
- `children`: sub-entities, one-to-many down the tree. Filters on any entity
  constrain related entities through the tree (subset the samples and the
  observations under them shrink accordingly).

Example, live on PlasmoDB study `STUDY_66f9e70b8a` (3D7 7 stages RNA-Seq):
root entity `ENT_8151325d` (Sample) with vars `label`, `parasite stage`;
child entity `ENT_fd574cd6` (htseq counts) with vars `SEQUENCE_READ_COUNT`
[integer] and `VEUPATHDB_GENE_ID` [string]. The reserved variable id
`VEUPATHDB_GENE_ID` marks the gene column; the [EDA-WDK
bridge](eda-wdk-bridge.md) depends on it.

## Storage

EDA data is installed into the application database as entity-attribute-value
tuning tables under the `eda` schema: `eda.attributegraph_{study}_{entity}`,
`eda.attributevalue_{study}_{entity}`, plus `EDA.ENTITYTYPEGRAPH` and friends
(visible in `VEuPathDB/ApiCommonModel` `.dst` templates and tuning table
lists). `{study}` is the study's `internal_abbrev`, computed by
`GenomicsEDAStudy.setEdaStudyInternalAbbrev()` as `"s" + SHA-1(datasetName)[:10]`,
and the dataset presenter id is `DS_` plus the same 10 hex characters, so
`DS_53f554ec6a` implies `eda.attributevalue_s53f554ec6a_gnPhntyD`.
`eda.study.user_dataset_id` links a VDI upload to its study. WDK record pages
on genomics sites already read these tables directly in SQL; the EDA service is
the only supported API over them. Loading pipelines are `eda-nextflow`,
`study-wrangler` (via `vdi-plugin-wrangler` for user datasets), and
`dataset-installer-isasimple`. The table-by-table layout is in
[data-model.md](data-model.md); the WDK-side relations in
[genomics-and-wdk-relations.md](genomics-and-wdk-relations.md).

## Filters, the subset algebra

A subset is an array of typed filters, each targeting one variable on one
entity (`entityId`, `variableId`, `type`, plus the type's payload):

- `stringSet` (categorical membership), `numberSet`, `dateSet`
- `numberRange`, `dateRange`, `longitudeRange`
- `multiFilter`: union/intersect over sub-filters of one multifilter variable

The io-ts definitions in
`web-monorepo/packages/libs/eda/src/lib/core/types/filter.ts` are the
consumer-side truth for the JSON. The RAML at HEAD declares an eighth type,
`stringPrefixSet`, implemented in `lib-eda-subsetting` but rejected 422 by the
deployed builds. Filters compose by AND across the array; the exact shapes,
composition proofs and error behavior are in [filters.md](filters.md), and the
cross-entity propagation semantics in
[subsetting-and-tabular.md](subsetting-and-tabular.md).

## Computes, apps, and visualizations

An **app** groups visualizations, optionally behind a **compute** (a
server-side R job over the filtered subset). `GET /eda/apps` on PlasmoDB
(2026-08-27) shows which are live per project:

- All genomics projects: `differentialexpression` (volcanoplot),
  `correlation` (the WGCNA eigengene app, bipartitenetwork; absent from
  VectorBase), `dimensionalityreduction` (scatterplot), plus compute-less
  `distributions`, `countsandproportions`, `xyrelationships`. The `pass`
  pass-through app is NOT on the genomics projects; its `projects` array is
  ClinEpiDB, AllClinEpiDB and VectorBase only.
- MicrobiomeDB adds `alphadiv`, `betadiv`, `abundance` (compute
  `rankedabundance`), `differentialabundance`, `selfcorrelation`,
  `correlationassayassay`, `correlationassaymetadata`, `maps`.
- VectorBase adds the `standalone-map*` apps behind MapVEu.

The full catalog with per-project availability is
[visualizations.md](visualizations.md); the per-compute configuration schemas
are [computes-and-jobs.md](computes-and-jobs.md).

Compute jobs are asynchronous: `POST /computes/{name}?autostart=true` with
{studyId, filters, config, derivedVariables} returns a status in
`queued | in-progress | complete | failed | expired | no-such-job`. When
complete, `POST /apps/{app}/visualizations/{viz}` returns server-computed plot
data; a volcanoplot response is `{effectSizeLabel, pValueFloor,
adjustedPValueFloor, statistics: [{pointID, effectSize, pValue,
adjustedPValue}]}`, where a row may omit `pValue` and `adjustedPValue`. The job
is keyed by an MD5 of its inputs (derivable client-side), so identical requests
share a cached result across users.

## Analyses

An **analysis** is the persisted user document, CRUD at
`/eda/users/{userId}/analyses/{projectId}`. Its `descriptor` is the whole
semantic state: `subset.descriptor` (the filter array), `computations` (each
with a typed `descriptor.type`/`configuration` and nested `visualizations`),
`starredVariables`, `derivedVariables`, `dataTableConfig`. The io-ts truth is
`web-monorepo/packages/libs/eda/src/lib/core/types/analysis.ts`, with one
exception: `descriptor.derivedVariables` holds **ids** (`string[]` in the
RAML; an inline spec object is a 422, proved live in
[derived-variables-and-merging.md](derived-variables-and-merging.md)), while
io-ts types the elements as `t.unknown`. Public
analyses can be listed and imported (`/eda/public/analyses/{projectId}`,
`/eda/import-analysis/...`). This same JSON document, unpersisted, is what the
[EDA-WDK bridge](eda-wdk-bridge.md) inlines into a WDK parameter.

## The frontends

`web-monorepo/packages/libs/eda` holds the React implementation: `core`
(types, api clients, hooks, visualizations), `workspace` (the full ClinEpiDB
and MicrobiomeDB analysis workspace), `map` (MapVEu), and `notebook` (the
newer cell-based UI: subset cell, compute cell, visualization cell, text cell,
wdkparam cell, shared-compute-inputs cell, composed into preset notebooks in
`src/lib/notebook/notebooks/`: `differentialExpression`, `wgcnaCorrelation`,
`antibodyArray`, plus `boxplot` (a test preset bound to no WDK question) and
the shared `differentialAnalysisReview` content; only three `edaNotebookType`
values are live on PlasmoDB, so only the first three are reachable from a WDK
question there - see [notebook-presets.md](notebook-presets.md)). Genomics
sites embed the notebook inside WDK question pages rather than shipping a
standalone workspace; the standalone `NotebookRoute` in the library is marked
as possibly dev-only now that the WDK integration exists.
