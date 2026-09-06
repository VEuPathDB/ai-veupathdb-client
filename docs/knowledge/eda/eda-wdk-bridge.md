---
type: Reference
title: The EDA-WDK bridge
description: How an EDA analysis becomes a WDK step through the eda_analysis_spec parameter and the WSF gene plugins, proven live on PlasmoDB with real counts, including the measurement that the generic and the per-dataset subset searches count the same genes.
tags: [eda, wdk, bridge, steps, strategies, eda_analysis_spec, wsf]
generated: { by: claude-code/fable-5, at: 2026-08-27T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-30T00:00:00Z }
status: stable
---

# The EDA-WDK bridge

EDA output enters a strategy as an ordinary WDK step. There is no new WDK
concept: the whole bridge is two string parameters on ordinary gene searches,
resolved by a WSF plugin that calls the EDA service and hands WDK a gene list.
A step built this way combines, transforms, nests, and saves exactly like any
other step.

## The parameters

Defined in `ApiCommonModel/Model/lib/wdk/model/questions/params/geneParams.xml`:

- `eda_dataset_id`: a `stringParam` (or, for user datasets, a
  `flatVocabParam` over installed VDI datasets) holding the dataset id
  (`DS_xxx`). Per-dataset generated searches default it to the dataset
  presenter id and hide it.
- `eda_analysis_spec`: a multiline `stringParam` holding the JSON of an EDA
  `NewAnalysis` (see [what-eda-is.md](what-eda-is.md), Analyses). The plugin
  synthesizes an empty descriptor for an empty value, but only the searches
  whose question sets `allowEmpty="true"` accept one; the generic search does
  not (see the count section below).

## The searches

In `ApiCommonModel/Model/lib/wdk/model/questions/queries/geneQueries.xml`:

- `GenesByEdaSubset` -> processQuery
  `org.apidb.apicomplexa.wsfplugin.eda.GeneEdaSubsetPlugin`: genes in the
  filtered subset. `GenesByEdaSubsetGeneric` is a third declared process query
  on the same plugin with `eda_dataset_id` hidden; it is the `queryRef` every
  per-dataset subset template uses, and the genomics-site UI routes the subset
  widget on `queryName === 'GenesByEdaSubsetGeneric'`, so the bare
  `GenesByEdaSubset` gets no EDA widget.
- `GenesByEdaVizWithCompute` -> `GeneEdaVizWithComputePlugin`: genes passing a
  compute-backed volcano visualization's thresholds, with dynamic columns
  `effectSize` and `pValue`. The bridge is volcano-only by construction: the
  plugin's `findVolcanoComputation` accepts a computation only if it carries a
  visualization of `type == "volcanoplot"` whose configuration has both
  `effectSizeThreshold` and `significanceThreshold`, and throws otherwise. So
  only `differentialexpression` and `differentialabundance` can reach a step
  this way (see [notebook-presets.md](notebook-presets.md)).
- Per-dataset searches are stamped out of `.dst` templates (`phenotype.dst`,
  `antibodyArray.dst`, `rnaSeqTemplates.dst`, `cellularLocalization.dst`) as
  `GenesByPhenotypeEdaSubset_{dataset}` and the like. `chipchip.dst` reads the
  same `eda.*` tables but stamps no EDA search: its templates feed a classic
  WDK `filterParam` and its gene query answers from
  `webready.ChIPchipTranscript_p`
  (see [genomics-and-wdk-relations.md](genomics-and-wdk-relations.md)).
- VDI user datasets route through the same plugins:
  `GenesByPhenotypeUserDataset`, `GenesByDESeqUserDataset`.

Live on PlasmoDB (2026-08-27), 68 of the transcript record type's 359 searches
declare `eda_analysis_spec`: 52 `GenesByRNASeq{dataset}DESeq`, 6 per-dataset
phenotype, 5 antibody-array, `GenesByEdaSubset`, `GenesByEdaVizWithCompute`,
`GenesByPhenotypeUserDataset`, `GenesByDESeqUserDataset`, and one
WGCNA-modules search whose SQL never reads the spec. Only 13 of the 68 have
`Eda` in their name, so an EDA-backed search is identified by the parameter,
never by the name.

## What the subset plugin does

`ApiCommonWebService/WSFPlugin/.../eda/AbstractEdaGenesPlugin.java` and
`GeneEdaSubsetPlugin.java`:

1. Parse `eda_analysis_spec`; require `studyId` in the spec to equal
   `eda_dataset_id` when both are present. Both are DATASET ids: the plugin's
   own comment reads `_datasetId = _analysisSpec.getString("studyId"); //
   misnamed; still need to look up study ID`, and its mismatch error ends
   "Note both values should be dataset IDs, not study IDs (old API)."
2. Resolve dataset -> study id via `GET {eda}/permissions`
   (`perDataset[datasetId].studyId`), which also enforces the user's access.
3. Fetch the study's entity tree and locate the entity carrying the variable
   with the reserved id `VEUPATHDB_GENE_ID`. The study must contain exactly
   one such variable, or the request fails.
4. `POST {eda}/studies/{study}/entities/{entity}/tabular` with
   `outputVariableIds: [VEUPATHDB_GENE_ID]` and the spec's
   `descriptor.subset.descriptor` filter array, `Accept:
   text/tab-separated-values`.
5. Stream the gene column into a WDK temporary table, expanding cells that
   hold JSON arrays of gene ids into one row each.
6. Join to `apidbtuning.transcriptattributes` (case-insensitive on
   `apidbtuning.geneid`) and emit transcript rows to WDK.

The plugin authenticates to EDA with the requesting user's bearer token
(`Authorization: Bearer ...`); there is no service account in the path.

## What the compute plugin adds

`GeneEdaVizWithComputePlugin` reads the spec's first computation and its first
visualization. It then:

1. `POST {eda}/computes/{computeName}?autostart=true` with {studyId, filters,
   config, derivedVariables}. Status `complete` proceeds; `queued` or
   `in-progress` throws WDK's `DelayedResultException`; `failed`, `expired`,
   `no-such-job` error out. Measured live (2026-08-27): while the job runs,
   the answer API returns **HTTP 202** with body
   `{"message":"WDK-DELAYED-RESULT","status":"accepted"}` - and the WDK
   request itself starts the compute, because the plugin posts with
   `autostart=true`. Retrying the identical request after completion returns
   the 200 answer. Full sequence: [notebook-presets.md](notebook-presets.md).
2. When complete, `POST {eda}/apps/{computeName}/visualizations/{vizName}`
   and stream the `statistics` array. The plugin uses `computeName` as the
   APP url segment, which works only because the volcano apps share their
   compute's name; apps and computes are distinct namespaces in general
   (`rankedabundance` backs the app named `abundance`).
3. Retain points passing the viz configuration's `effectSizeThreshold`,
   `significanceThreshold`, and `effectDirection` (upOnly, downOnly,
   upAndDown), and deliver genes with `effectSize` and `pValue` as dynamic
   step columns.

So the thresholds a user drags on the volcano plot ARE the search parameters;
they travel inside the analysis JSON.

## The notebook UI is only a param editor

Questions carrying the `edaNotebookType` property (values live today:
`differentialExpressionNotebook`, `wgcnaCorrelationNotebook`,
`antibodyArrayNotebook`) get their
entire question form replaced by
`genomics-site/.../questions/EdaNotebookQuestionForm.tsx` and
`EdaNotebookParameter.tsx`, which mount the EDA notebook and serialize every
notebook change back into `eda_analysis_spec` via `updateParamValue`. WDK
never knows a notebook exists; it sees a string parameter.

## Live proof (2026-08-27, plasmodb.org)

Search `GenesByPhenotypeEdaSubset_PlasmoDB_Rod_Mal_Phenotype_RSRC`
(`eda_dataset_id` default `DS_53f554ec6a`, study `STUDY_53f554ec6a`, one
entity `GENE_PHENOTYPE_DATA_ENTITY` with 13 string variables including
`VEUPATHDB_GENE_ID`), run through the plain answer API
`POST /plasmo/service/record-types/transcript/searches/{search}/reports/standard`:

- empty `eda_analysis_spec` -> `totalCount` **5810**
- one filter `{"entityId": "GENE_PHENOTYPE_DATA_ENTITY", "variableId":
  "VAR_035294d0", "type": "stringSet", "stringSet": ["P. berghei"]}` ->
  `totalCount` **5602**

Same transport PathFinder already speaks; nothing about the EDA bridge needs a
browser.

## The generic and the per-dataset search count the same genes (2026-08-30)

Both searches were run on plasmodb.org on the same day, through the same answer
API, with one spec: the analysis document above with the single filter
`{"entityId": "GENE_PHENOTYPE_DATA_ENTITY", "variableId": "VAR_035294d0",
"type": "stringSet", "stringSet": ["P. berghei"]}` and `eda_dataset_id`
`DS_53f554ec6a`.

| Search | `totalCount` | `displayTotalCount` |
|---|---|---|
| `GenesByPhenotypeEdaSubset_PlasmoDB_Rod_Mal_Phenotype_RSRC` | 5602 | 5556 |
| `GenesByEdaSubset` | **5602** | **5556** |

**They agree exactly. The 46 that once separated them is the transcript/gene
axis, not the search.** `totalCount` counts transcripts and `displayTotalCount`
counts genes, and a strategy's `estimatedSize` tracks `displayTotalCount`
([WDK-FILTER-005](../wdk/rules/filters.md)). So an answer-API reading of 5602
and a strategy reading of 5556 are one result reported twice, and any
comparison between the two searches must read the same one of the two numbers.

The model says the same. `GenesByEdaSubset` and `GenesByEdaSubsetGeneric` are
[the same plugin with the same four `wsColumn`s](https://github.com/VEuPathDB/ApiCommonModel/blob/7aa7d662b2501ff4d18a1f50ac5a2e16abd884c4/Model/lib/wdk/model/questions/queries/geneQueries.xml#L147-L153),
differing only in `visible="false"` on `eda_dataset_id`; there is no project or
organism scoping on either.

**One real difference: the empty spec.** `geneParams.eda_analysis_spec` declares
no `allowEmpty`, so WDK's default of false applies. The per-dataset template
overrides it -
[`phenotype.dst`](https://github.com/VEuPathDB/ApiCommonModel/blob/7aa7d662b2501ff4d18a1f50ac5a2e16abd884c4/Model/lib/dst/phenotype.dst#L47-L54)
stamps `<paramRef ref="geneParams.eda_analysis_spec" allowEmpty="true" .../>`
beside `default="${presenterId}"` on the hidden dataset id - and the bare
`GenesByEdaSubset` question adds no overrides. Measured the same day: the
per-dataset search with an empty spec answered `totalCount` 5810 /
`displayTotalCount` 5764, and the generic search answered
`HTTP 422 {"byKey":{"eda_analysis_spec":["Cannot be empty."]}}`. PathFinder
exports through the generic search, so an analysis with no filters and no
computation has no step to export.
