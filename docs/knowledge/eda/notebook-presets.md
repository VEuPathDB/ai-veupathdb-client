---
type: Reference
title: EDA notebook presets and the compute bridge boundary
description: Every upstream notebook preset cell by cell, the WDK questions they bind to, and the measured answer to whether the compute bridge supports anything other than a volcano plot.
tags: [eda, notebook, presets, wdk, wgcna, differentialexpression, antibodyarray, bridge]
generated: { by: claude-code/opus-5, at: 2026-08-27T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-27T00:00:00Z }
status: stable
---

# EDA notebook presets and the compute bridge boundary

An EDA notebook is a list of typed cells. On the genomics sites the notebook is
not a standalone workspace: it replaces the form of a WDK question and
serializes its state into that question's `eda_analysis_spec` parameter, as
[eda-wdk-bridge.md](eda-wdk-bridge.md) describes. This document is the cell-level
inventory, plus the measured answer to what the compute bridge actually supports.

Sources. `VEuPathDB/web-monorepo` at commit
`3e04f4ff37b7a960fcb2edcf3f65dba876d14815`, under
`packages/libs/eda/src/lib/notebook/`. `VEuPathDB/ApiCommonModel` at commit
`b4acd83696ac7706699078db7759f1b07a589a32`. `VEuPathDB/ApiCommonWebService` at
commit `069d7257e22e9a53c4ec61c7828393a7ae5c588a`. Live calls ran against
`plasmodb.org` on 2026-08-27.

## The cell vocabulary

`notebook/Types.ts` defines six descriptor types. Every one carries
`{id, type, title, cells?, numberedHeader?, helperText?, initialPanelState?}`.

| `type` | Adds | Renderer |
|---|---|---|
| `subset` | nothing | `cells/SubsettingNotebookCell.tsx` |
| `compute` | `computationName`, `computationId`, `configOverrides?`, `sharedInputNames?`, `sharedInputsCellId?`, `readonlyInputNames?`, `hidden?`, `getAdditionalCollectionPredicate?` | `cells/ComputeNotebookCell.tsx` |
| `visualization` | `visualizationName`, `visualizationId`, `getVizPluginOptions?` | `cells/VisualizationNotebookCell.tsx` |
| `text` | `text` (node or function of context), `panelStateResolver?` | `cells/TextNotebookCell.tsx` |
| `wdkparam` | `paramNames[]`, `requiredParamNames?` | `cells/WdkParamNotebookCell.tsx` |
| `sharedcomputeinputs` | `computationIds[]`, `inputNames[]`, `inputs[]`, `constraints?`, `dataElementDependencyOrder?` | `cells/SharedComputeInputsNotebookCell.tsx` |

A `PresetNotebook` is `{name, displayName, projects[], cells[], header?,
isReady?}`. Cells nest: a `compute` cell's `cells` array holds the
visualizations that read that compute.

The `sharedcomputeinputs` cell is the interesting one. It owns named config
properties across **several** computations at once: `computationIds` lists the
computations it writes into and `inputNames` lists the properties it owns. Those
computations render the shared properties read-only. `notebooks/utils.ts`
`withResolvedSharedInputNames` back-fills each compute cell's `sharedInputNames`
from the referenced shared-inputs cell, so a preset states the relationship once.

## The two variable-id constants

Resolved from `core/components/computations/Utils.ts`:

```ts
GENE_EXPRESSION_STABLE_IDS = {
  IDENTIFIER:       'VEUPATHDB_GENE_ID',
  COUNT:            'SEQUENCE_READ_COUNT',
  COUNT_SENSE:      'SEQUENCE_READ_COUNT_SENSE',
  COUNT_ANTISENSE:  'SEQUENCE_READ_COUNT_ANTISENSE',
  NORMALIZED:       'NORMALIZED_EXPRESSION',
  NORMALIZED_ARRAY: 'NORMALIZED_INTENSITY',
}

GENE_EXPRESSION_VALUE_IDS = [
  'SEQUENCE_READ_COUNT', 'SEQUENCE_READ_COUNT_SENSE', 'SEQUENCE_READ_COUNT_ANTISENSE',
  'NORMALIZED_EXPRESSION', 'NORMALIZED_INTENSITY',
]
```

These are **reserved variable ids**, in the same class as `VEUPATHDB_GENE_ID`
itself: they are stable strings across studies, not per-study `VAR_xxx` ids. A
study is usable for differential expression exactly when its gene entity carries
`VEUPATHDB_GENE_ID` and at least one of the five value ids. Live confirmation on
two PlasmoDB studies: `STUDY_66f9e70b8a` carries `SEQUENCE_READ_COUNT`,
`STUDY_e973eadd57` carries `SEQUENCE_READ_COUNT_SENSE` and
`SEQUENCE_READ_COUNT_ANTISENSE`.

Neither is used as a compute-service constraint. The service accepts any
`VariableSpec`; the restriction to these ids lives only in the frontend
`allowedVariableIds` constraints. See
[computes-and-jobs.md](computes-and-jobs.md).

## The presets

`notebooks/index.ts` registers four:

```ts
presetNotebooks = { antibodyArrayNotebook, differentialExpressionNotebook,
                    wgcnaCorrelationNotebook, boxplotNotebook }
```

### differentialExpressionNotebook

`name: 'differentialexpression'`, projects: all of `GENOMICS_PROJECTS`.
Cells, in order:

1. `de_subset` (`subset`), "Select Samples (optional)", `initialPanelState:
   'closed'`. Optional outlier removal.
2. `de_shared_inputs` (`sharedcomputeinputs`), "Select Expression Data".
   `computationIds: ['pca_1','de_1']`,
   `inputNames: ['identifierVariable','valueVariable']`. Constraints: both
   required, exactly one variable each; `identifierVariable` limited to
   `allowedVariableIds: ['VEUPATHDB_GENE_ID']`, `valueVariable` limited to the
   five `GENE_EXPRESSION_VALUE_IDS`. `dataElementDependencyOrder:
   [['identifierVariable','valueVariable']]`. This is why the two computes below
   always agree on their input columns.
3. `de_pca_compute` (`compute`), `computationName: 'dimensionalityreduction'`,
   `computationId: 'pca_1'`, `configOverrides: {dataFormat: 'rawCounts'}`,
   `readonlyInputNames: ['dataFormat']`, `sharedInputsCellId:
   'de_shared_inputs'`.
   - `de_pca_plot` (`visualization`), `scatterplot`, id `pca_1`, with
     `getVizPluginOptions` returning `{hideCoverageData: true, autoSelectFeatured:
     true, autoSelectWhenPossible: true}`.
4. `de_deseq2_compute` (`compute`), `computationName:
   'differentialexpression'`, `computationId: 'de_1'`, `sharedInputsCellId:
   'de_shared_inputs'`. No `configOverrides`, so the method comes from the
   plugin default.
   - `de_volcano` (`visualization`), `volcanoplot`, id `volcano_1`.
   - `de_review` (`text`), "Review and Run Search", rendering
     `DifferentialAnalysisReviewContent`, open only when
     `isDEReadyToReviewAndSubmit`.

`isReady` is `isDEReadyToReviewAndSubmit`, which finds the computation whose
`descriptor.type === 'differentialexpression'` and delegates to that plugin's
`isConfigurationComplete`: `identifierVariable`, `valueVariable`,
`comparator.groupA` and `comparator.groupB` must all be non-null.

The compute plugin's `createDefaultConfiguration` (in
`core/components/computations/plugins/differentialExpression.tsx`) is
`{pValueFloor: '1e-200', differentialExpressionMethod: 'DESeq'}` (the first key
of the method table). That table maps the wire key `DESeq` to display name
`DESeq2` with the Love et al. 2014 citation, and `limma` to `limma` with Ritchie
et al. 2015. So the notebook titled "Set up DESeq2 Computation" sends
`differentialExpressionMethod: "DESeq"`.

Its `geneExpressionConstraints` add a third input the shared cell does not own:
`comparatorVariable`, required, exactly one variable, `minNumValues: 2`, and
"Must be from a parent entity of the expression data".
`geneExpressionDependencyOrder` is
`[['identifierVariable','valueVariable'],['comparatorVariable']]`.

### antibodyArrayNotebook

`name: 'antibodyArrayNotebook'`, projects: all of `GENOMICS_PROJECTS`. Structurally
the same as the differential expression notebook, with three differences:

- `ab_pca_compute` uses `configOverrides: {dataFormat: 'normalizedValues'}`
  instead of `'rawCounts'`.
- `ab_limma_compute` uses `configOverrides: {differentialExpressionMethod:
  'limma'}`. It is the **same `differentialexpression` compute**, switched to the
  array method. There is no separate antibody-array compute.
- `ab_review` passes label overrides to the shared review component:
  `expressionDataTitle="Antibody Data"`, `valueLabel="Signal type"`,
  `sharedInputsCellId="ab_shared_inputs"`, `computeCellId="ab_limma_compute"`,
  `volcanoCellId="ab_volcano"`.

Its constraints are identical to the differential expression ones, including
`allowedVariableIds`, so an antibody-array study is loaded with the same
reserved variable ids.

### wgcnaCorrelationNotebook

`name: 'wgcnacorrelation'`, `projects: ['PlasmoDB','HostDB','UniDB']` (a
hardcoded three, not `GENOMICS_PROJECTS`). Cells:

1. `wgcna_correlation_compute` (`compute`), `computationName: 'correlation'`,
   `computationId: 'correlation_1'`, with a
   `getAdditionalCollectionPredicate` that keeps only collection id
   `EUPATH_0005051` on PlasmoDB and `EUPATH_0005050` on HostDB, and everything
   on the portal.
   - `wgcna_bipartite` (`visualization`), `bipartitenetwork`, id `bipartite_1`,
     whose `getVizPluginOptions` supplies an
     `additionalOnNodeClickAction`: clicking a node matches its lowercased label
     against the `wgcnaParam` vocabulary (exact, or case-insensitive
     `endsWith('_' + label)` to absorb a data-side prefix) and calls
     `wdkState.updateParamValue` with the matched vocabulary value.
2. `wgcna_params` (`wdkparam`), "Run gene search",
   `paramNames: ['wgcnaParam','wgcna_correlation_cutoff']`,
   `requiredParamNames: ['wgcnaParam']`.

`isReady` reads `wdkState.paramValues['wgcnaParam']` and returns false while it
is empty or contains `choose_module`.

There is **no review cell and no threshold cell**: the network is an exploration
aid, and the gene list comes from a WDK parameter.

`UNVERIFIED:` the collection predicate may not discriminate as intended on
PlasmoDB. Live on study `STUDY_fd06cb37d3` (dataset `DS_eeca6a5476`, the one
PlasmoDB WGCNA search) both eigengene entities carry collection id
`EUPATH_0005051`: `ENT_2caaf3f6` ("pfal3D7 Eigengene (wgcna)", 16 members) and
`ENT_12121f8c` ("hsapREF Eigengene (wgcna)", 23 members). Filtering by
collection id alone would keep both. `EUPATH_0005050` did not appear in that
study. Whether other studies use the two ids as the code assumes was not
checked.

### boxplotNotebook

`name: 'boxplot'`, `projects: ['MicrobiomeDB']`. One `visualization` cell,
`boxplot`, id `boxplot_1`. `index.ts` states outright that it "has no plan for
use yet, just good for testing". It is not bound to any WDK question.

### differentialAnalysisReview.tsx

Not a preset. It exports `isDEReadyToReviewAndSubmit` and the
`DifferentialAnalysisReviewContent` component that both the differential
expression and antibody array notebooks embed in their review cell. The review
card reads the volcano visualization's configuration and displays
`effectSizeThreshold`, `significanceThreshold` and `effectDirection`
(defaulting to `'upAndDown'`) next to the submit button, so the user sees the
values that will become the WDK step's filter before running the search.

## Which WDK question each preset binds to

The binding is a WDK question property list. Live and in source, three
`edaNotebookType` values exist:

| `edaNotebookType` value | Declared in | Question | Query |
|---|---|---|---|
| `differentialExpressionNotebook` | `Model/lib/dst/rnaSeqTemplates.dst` (template `rnaSeqDESeqQuestion`) | `GenesByRNASeq{dataset}DESeq` | `GeneId.GenesByEdaVizWithCompute` |
| `differentialExpressionNotebook` | `Model/lib/wdk/model/questions/geneQuestions.xml` | `GenesByDESeqUserDataset` (VDI user datasets, `userDatasetType: rnaseqrc`) | as above |
| `antibodyArrayNotebook` | `Model/lib/dst/antibodyArray.dst` | `GenesByAntibodyArrayEdaSubset_{dataset}` | subset query |
| `wgcnaCorrelationNotebook` | `Model/lib/dst/rnaSeqTemplates.dst` (template `rnaSeqWGCNAModulesQuestion`) | `GenesByRNASeq{dataset}WGCNAModules` | `GeneId.GenesByWGCNAModule` |

`boxplotNotebook` has no binding.

Live on PlasmoDB (2026-08-27), the transcript record type carries **52**
searches ending in `DESeq`, **1** ending in `WGCNAModules`, **5**
`GenesByAntibodyArrayEdaSubset_*` and **6** `GenesByPhenotypeEdaSubset_*`, out
of 359 total.

`GENOMICS_PROJECTS` resolves, in `wdk-client/src/Utils/ProjectConstants.ts`, to
**13** project ids: UniDB, AmoebaDB, CryptoDB, FungiDB, GiardiaDB, HostDB,
MicrosporidiaDB, PiroplasmaDB, PlasmoDB, ToxoDB, TrichDB, TriTrypDB and
**VectorBase**. So the differential expression and antibody array notebooks are
declared for VectorBase too.

One DESeq search, live:

```
GET /plasmo/service/record-types/transcript/searches/GenesByRNASeqpfal3D7_Pfal3D7_Febrile_temps_RNASeq_ebi_rnaSeq_RSRCDESeq

displayName: "P. falciparum 3D7 Heat shock response in sensitive mutants
              (LRR5, DHC) RNA-Seq (Differential Expression)"
properties.edaNotebookType: ["differentialExpressionNotebook"]
properties.displayCategory:  ["Differential Expression"]
parameters:
  eda_dataset_id     string  default "DS_e973eadd57"  visible false
  eda_analysis_spec  string  default ""               visible true
```

The `.dst` template also sets
`attributesList summary="organism,gene_product,effectSize,pValue"
sorting="effectSize desc"`, so the step's result table shows the two dynamic
columns the compute bridge produces.

## The compute bridge supports volcano plots only

This was the open question. The answer is unambiguous.

`ApiCommonWebService/WSFPlugin/.../eda/GeneEdaVizWithComputePlugin.java`
resolves the computation to use through one private method:

```java
private static JSONObject findVolcanoComputation(JSONArray computations) throws PluginModelException {
  for (int i = 0; i < computations.length(); i++) {
    JSONObject comp = computations.getJSONObject(i);
    JSONArray vizs = comp.optJSONArray("visualizations");
    if (vizs == null) continue;
    for (int j = 0; j < vizs.length(); j++) {
      JSONObject vizDesc = vizs.getJSONObject(j).optJSONObject("descriptor");
      if (vizDesc == null) continue;
      if (!"volcanoplot".equals(vizDesc.optString("type"))) continue;
      JSONObject vizConfig = vizDesc.optJSONObject("configuration");
      if (vizConfig == null) continue;
      if (vizConfig.has("effectSizeThreshold") && vizConfig.has("significanceThreshold")) {
        return comp;
      }
    }
  }
  throw new PluginModelException(
    "Analysis spec does not contain a computation with a volcano plot visualization " +
    "configured with effectSizeThreshold and significanceThreshold.");
}
```

It scans **every** computation but accepts one only if that computation has a
visualization of `type == "volcanoplot"` whose configuration carries both
`effectSizeThreshold` and `significanceThreshold`. A `correlation` computation
with a `bipartitenetwork` visualization can never match, and the plugin throws
rather than falling back. The rest of the plugin reinforces this: the only fields
it parses from the response are `pointID`, `effectSize` and `pValue`, and
`isRetainedRow` is a fixed threshold-plus-direction test over those three.

So the bridge supports exactly the two volcano-producing computes,
`differentialexpression` and `differentialabundance`. It does not support
correlation, WGCNA, dimensionality reduction, alpha or beta diversity, or ranked
abundance. Adding one would mean a new WSF plugin and a new WDK query, not a
configuration change.

Also worth recording from the same file: the compute the plugin drives is
started by the plugin itself. `handleComputeStatus` posts
`{studyId, config, filters, derivedVariables: []}` to
`/computes/{computeName}?autostart=true` and then branches on `status`:
`complete` proceeds, `queued` or `in-progress` throws
`DelayedResultException`, and `no-such-job`, `failed` or `expired` throw
`PluginModelException`. The `studyId` it sends is the **study** id it resolved
from the dataset id through `/eda/permissions`, matching what the compute
endpoint requires.

## How the WGCNA notebook exports genes: not through EDA at all

The search behind `wgcnaCorrelationNotebook` is `GenesByRNASeq{dataset}WGCNAModules`,
and its query in `ApiCommonModel/Model/lib/wdk/model/questions/queries/geneQueries.xml`
is a plain `sqlQuery`, not a `processQuery`:

```xml
<sqlQuery name="GenesByWGCNAModule" >
  <paramRef ref="geneParams.eda_dataset_id"/>
  <paramRef ref="geneParams.eda_analysis_spec"/>
  <paramRef ref="geneParams.wgcnaParam"/>
  <paramRef ref="geneParams.wgcnaDataset"/>
  <paramRef ref="geneParams.wgcna_correlation_cutoff"/>
  <column name="project_id"/><column name="source_id"/>
  <column name="gene_source_id"/><column name="matched_result"/>
  <column name="correlation_coefficient"/>
  <sql><![CDATA[
    SELECT ta.source_id, ta.gene_source_id, 'Y' as matched_result,
           nfw.correlation_coefficient, ta.project_id
    FROM webready.TranscriptAttributes_p ta, apidb.nafeaturewgcnaresults nfw
    WHERE ta.gene_na_feature_id = nfw.na_feature_id
      AND nfw.protocol_app_node_id = $$wgcnaParam$$
      AND nfw.correlation_coefficient >= $$wgcna_correlation_cutoff$$
    ORDER by nfw.correlation_coefficient desc
  ]]></sql>
</sqlQuery>
```

No WSF plugin, no EDA service call, no `statistics` array. The gene list comes
from the pre-loaded table `apidb.nafeaturewgcnaresults`, selected by module
(`protocol_app_node_id = wgcnaParam`) and thresholded by
`correlation_coefficient >= wgcna_correlation_cutoff`, with
`correlation_coefficient` as the step's dynamic column.

`eda_dataset_id` and `eda_analysis_spec` are declared as parameters but are
**not referenced by the SQL**. They exist only so the WDK question form is
replaced by the notebook UI, which needs a dataset to browse and a place to keep
its analysis state. The EDA correlation compute in that notebook is an
exploration aid whose only output into WDK is the module name a user clicks,
written into `wgcnaParam` by the node-click handler.

Live on PlasmoDB, `GenesByRNASeqpfal3D7_Lee_Gambian_ebi_rnaSeq_RSRCWGCNAModules`:

```
properties.edaNotebookType: ["wgcnaCorrelationNotebook"]
parameters:
  eda_dataset_id           string                    default "DS_eeca6a5476"  visible false
  eda_analysis_spec        string                    default ""               visible true
  wgcnaParam               single-pick-vocabulary    default "1_choose_module"  visible true
                           17 values, e.g. ["Module_10_17Nov2025_pfal3D7", ...]
  wgcnaDataset             single-pick-vocabulary    default "pfal3D7_Lee_Gambian_ebi_rnaSeq_RSRC"  visible false
                           2 values: the parasite and the human reference datasets
  wgcna_correlation_cutoff string                    default "0.75"           visible true
```

`1_choose_module` is the placeholder the notebook's `isReady` rejects.

## The delayed result, measured

`pathfinder: docs/knowledge/eda/pathfinder-integration-concept.md` flagged
as unverified what the WDK answer API returns while a compute is still running.
Measured on 2026-08-27 against
`POST /plasmo/service/record-types/transcript/searches/GenesByEdaVizWithCompute/reports/standard`.

The analysis spec used, with `studyId` as the **dataset** id (the plugin requires
`eda_analysis_spec.studyId` to equal `eda_dataset_id`, and both are dataset ids):

```json
{
  "studyId": "DS_e973eadd57",
  "displayName": "...", "description": "", "isPublic": false,
  "descriptor": {
    "subset": { "descriptor": [], "uiSettings": {} },
    "computations": [{
      "computationId": "de2",
      "descriptor": {
        "type": "differentialexpression",
        "configuration": {
          "identifierVariable": {"entityId":"ENT_fd574cd6","variableId":"VEUPATHDB_GENE_ID"},
          "valueVariable": {"entityId":"ENT_fd574cd6","variableId":"SEQUENCE_READ_COUNT_ANTISENSE"},
          "comparator": {
            "variable": {"entityId":"ENT_8151325d","variableId":"VAR_081ab087"},
            "groupA": [{"label":"normal"}], "groupB": [{"label":"febrile"}]
          },
          "differentialExpressionMethod": "DESeq",
          "pValueFloor": "1e-200"
        }
      },
      "visualizations": [{
        "visualizationId": "v2", "displayName": "Volcano",
        "descriptor": {
          "type": "volcanoplot",
          "configuration": {"effectSizeThreshold": 1, "significanceThreshold": 0.05},
          "currentPlotFilters": []
        }
      }]
    }],
    "starredVariables": [], "dataTableConfig": {}, "derivedVariables": []
  }
}
```

sent as `{"searchConfig":{"parameters":{"eda_dataset_id":"DS_e973eadd57",
"eda_analysis_spec": "<the JSON above, stringified>"}}, "reportConfig":{...}}`.

Sequence and results:

| Time (UTC) | Call | Result |
|---|---|---|
| 08:29:40 | job confirmed absent: `POST /eda/computes/differentialexpression?autostart=false` | `{"jobID":"fc845977ae2b9c754da5afbf993498dc","status":"no-such-job"}` |
| 08:29:40 | the WDK answer POST above | **`202 {"message":"WDK-DELAYED-RESULT","status":"accepted"}`**, in 2.0 s |
| 08:29:42 | `POST /eda/computes/...?autostart=false` again | `{"jobID":"fc845977ae2b9c754da5afbf993498dc","status":"in-progress"}` |
| 08:29:56 | `GET /eda/jobs/fc845977ae2b9c754da5afbf993498dc` | `{"status":"complete"}` |
| 08:29:56 | the identical WDK answer POST | `200`, `totalCount` 1060, `displayTotalCount` 1044, first record `PF3D7_0100200` |

Three measured facts:

1. **The delayed result is `HTTP 202` with body
   `{"message":"WDK-DELAYED-RESULT","status":"accepted"}`.** It is not a 200 with
   zero records, not a 4xx, and not a WDK error envelope. A client that only
   branches on `response.ok` will read it as success and find no `records` key.
2. **The WDK request starts the compute.** The job went from `no-such-job` to
   `in-progress` across a request that returned no data, because the bridge
   plugin posts with `autostart=true`. So a caller does not need to pre-start the
   job, but also cannot avoid starting one by mistake.
3. **Retrying the identical request after completion succeeds**, with no cache
   invalidation and no changed parameters. The request is idempotent and the 202
   is purely a "not yet" signal.

For comparison, the same search over the already-complete job used for the
`SEQUENCE_READ_COUNT_SENSE` configuration returned `200` immediately with
`totalCount` 1571 and `displayTotalCount` 1543, matching the 1543 rows that pass
the same thresholds in the raw volcanoplot response (see
[visualizations.md](visualizations.md)).

## What this means for PathFinder

- **Handle 202 explicitly.** `POST .../reports/standard` on an EDA
  compute-backed search has three outcomes, not two: 202 delayed, 200 answer,
  or a plugin error. Treating 202 as an answer produces a silent empty result.
- **Prefer driving the compute first.** Because the job id is a derivable MD5
  (see [computes-and-jobs.md](computes-and-jobs.md)), a tool can poll
  `/computes/{name}?autostart=true` inside a `@durable_tool` job and create the
  step only once `complete`. The step then never surfaces a 202, and progress is
  reportable. This is now measured rather than assumed.
- **The presets are the authoring sheets.** Three of the four encode which
  compute, which reserved variable ids and which comparator shape make sense for
  a data type. They are the direct template for typed authoring sheets, in the
  same spirit as `set_criterion`'s `params_template`.
- **Do not plan a generic compute-to-step bridge.** Upstream's is volcano-only
  by construction. WGCNA reaches WDK through an ordinary SQL query on a
  pre-loaded table, and any other compute has no WDK path at all today.
