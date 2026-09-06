---
type: Reference
title: EDA apps and visualization data
description: The app and visualization catalog with per-project availability, and the request and response shapes of the visualization data endpoints, live-verified on PlasmoDB.
tags: [eda, apps, visualizations, volcanoplot, scatterplot, bipartitenetwork, histogram, barplot]
generated: { by: claude-code/opus-5, at: 2026-08-27T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-27T00:00:00Z }
status: stable
---

# EDA apps and visualization data

An **app** is a named group of visualizations, optionally bound to one compute.
A **visualization** is an endpoint that returns plot **data**, never an image.
`POST /eda/apps/{app}/visualizations/{viz}` is the whole read surface.

Sources. Schema is `VEuPathDB/service-eda` at commit
`b3bb8bac06de4340b4b2c21d9aa4a94d9b3de61f` (default branch `master`):
`api.raml`, `schema/url/data/apps.raml`, `schema/url/data/visualizations.raml`,
`schema/url/data/plots.raml`, and one file per plugin under
`schema/url/data/{app}/`. Live calls ran against `https://plasmodb.org/eda` on
2026-08-27. Each shape below is marked live-verified or schema-derived.

## The catalog

`GET /eda/apps` returned **23 apps** on PlasmoDB on 2026-08-27. The response is
cross-project: every app is listed with the `projects` array that gates it, so
one call describes the whole family. `AppOverview` is
`{name, displayName, description, projects[], computeName?, visualizations[]}`;
`VisualizationOverview` is `{name, displayName, description, projects[],
maxPanels, dataElementConstraints?, dataElementDependencyOrder?}`.

`GENOMICS` below means the 12 genomics projects listed together in the live
response: AmoebaDB, CryptoDB, FungiDB, GiardiaDB, HostDB, MicrosporidiaDB,
PiroplasmaDB, PlasmoDB, ToxoDB, TrichDB, TriTrypDB, UniDB. VectorBase is called
out separately below wherever it appears, because it is inconsistent: the
frontend's `GENOMICS_PROJECTS` constant includes VectorBase (13 ids) while
several `projects` arrays in `GET /eda/apps` do not. Do not treat "genomics" as
one fixed set.

| App | Compute | Visualizations | Projects |
|---|---|---|---|
| `differentialexpression` | `differentialexpression` | `volcanoplot` | GENOMICS + VectorBase |
| `dimensionalityreduction` | `dimensionalityreduction` | `scatterplot` | GENOMICS + VectorBase + MicrobiomeDB |
| `correlation` (WGCNA Correlation, Eigengene v. Eigengene, Metadata) | `correlation` | `bipartitenetwork` | GENOMICS |
| `distributions` | none | `histogram`, `boxplot` | GENOMICS + VectorBase + MicrobiomeDB |
| `countsandproportions` | none | `barplot`, `twobytwo`, `conttable` | GENOMICS + VectorBase + MicrobiomeDB |
| `xyrelationships` | none | `scatterplot`, `lineplot` | GENOMICS + VectorBase + MicrobiomeDB |
| `alphadiv` | `alphadiv` | `boxplot`, `scatterplot` | MicrobiomeDB |
| `abundance` (Ranked Abundance) | `rankedabundance` | `boxplot`, `scatterplot` | MicrobiomeDB |
| `betadiv` | `betadiv` | `scatterplot` | MicrobiomeDB |
| `differentialabundance` | `differentialabundance` | `volcanoplot` | MicrobiomeDB |
| `correlationassayassay` | `correlation` | `bipartitenetwork` | MicrobiomeDB |
| `correlationassaymetadata` | `correlation` | `bipartitenetwork` | MicrobiomeDB |
| `selfcorrelation` | `selfcorrelation` | `unipartitenetwork` | MicrobiomeDB |
| `maps` | none | `map-markers`, `map-markers-overlay` | MicrobiomeDB |
| `pass` (Pass-Through) | none | `histogram`, `barplot`, `scatterplot`, `boxplot`, `twobytwo`, `conttable`, `lineplot`, `densityplot`, `heatmap`, `map-markers`, `map-markers-overlay` | ClinEpiDB, AllClinEpiDB, VectorBase |
| `standalone-map` | none | `map-markers`, `map-markers-bubbles`, `map-markers-bubbles-legend` | VectorBase |
| `standalone-map-xyrelationships` | none | `lineplot`, `timeseries` | VectorBase |
| `standalone-map-distributions` | none | `histogram`, `timeline`, `boxplot` | VectorBase |
| `standalone-map-countsandproportions` | none | `barplot`, `conttable` | VectorBase |
| `standalone-map-categorical-collections` | none | `lineplot`, `barplot`, `conttable` | VectorBase |
| `standalone-map-continuous-collections` | none | `lineplot`, `barplot`, `histogram` | VectorBase |
| `sample` | none | `record-count`, `multi-stream`, `collections-test`, `categorical-distribution` | none (test) |
| `samplewithcompute` | `example` | `viz-with-compute` | none (test) |

Three things a reader should not assume:

- **`pass` is not available on the genomics projects.** Its `projects` array is
  ClinEpiDB, AllClinEpiDB and VectorBase only. Genomics sites get the same plot
  types through the three narrower compute-less apps `distributions`,
  `countsandproportions` and `xyrelationships`.
- **`correlation` is live on the genomics projects**, as the WGCNA eigengene app.
  It is not MicrobiomeDB-only. `selfcorrelation` is MicrobiomeDB-only.
- **`correlation` is not on VectorBase**, while `differentialexpression` and
  `dimensionalityreduction` are.

## Pass-through apps

An app with no `computeName` is a pass-through: the plot data is derived from the
subset alone, with no R job in the path. Upstream expresses this in
`data/core/AbstractEmptyComputePlugin.java`, whose comment states plainly that
"pass app viz plugins don't have a compute", and which pins the plugin's compute
type parameter to `Void`. Pass-through visualization requests therefore have
**no `computeConfig` field at all**; a compute-backed one requires it.

## config against computeConfig

Every visualization POST body extends `DataPluginRequestBase`
(`schema/url/data/visualizations.raml`), which allows exactly
`{studyId, filters?, derivedVariables?}` and forbids extra properties. A
compute-backed visualization adds two fields, and the split is the single most
important thing to get right:

- **`computeConfig`** is the compute's configuration, byte-for-byte the same
  object as the `config` of the corresponding
  `POST /computes/{name}` body (see
  [computes-and-jobs.md](computes-and-jobs.md)). It selects **which job's output
  to read**, because the job id is a hash of it.
- **`config`** is the visualization's own specification: axes, bins, overlays,
  thresholds. It is per plugin and never affects which compute job is read.

Live-verified: the visualization endpoint does **not** start a compute. A
`volcanoplot` POST whose `computeConfig` addressed a never-computed job returned

```
400 {"status":"bad-request","message":"Compute results are not available for the requested job."}
```

The caller must drive the compute to `complete` first. `studyId` in a
visualization body is a `STUDY_xxx`, as it is for computes.

## volcanoplot (live-verified)

The flagship for PathFinder. Request type
`DifferentialExpressionVolcanoplotPostRequest`:

```json
{
  "studyId": "STUDY_e973eadd57",
  "filters": [],
  "computeConfig": { /* DifferentialExpressionComputeConfig */ },
  "config": {}
}
```

**`config` is `EmptyDataPluginSpec`: an object with no properties allowed.** The
thresholds a user drags on a volcano plot are **never sent to the service**. The
plugin (`data/plugin/differentialexpression/DifferentialExpressionVolcanoplotPlugin.java`)
requests no data streams at all and its `writeResults` is a single call to
`writeComputeStatsResponseToOutput`: it pipes the compute's statistics file
straight through. Thresholding happens in the consumer, whether that is the
React plot or the WDK bridge plugin.

Live response on `STUDY_e973eadd57`, `SEQUENCE_READ_COUNT_SENSE`, DESeq,
`normal` against `febrile`:

```json
{
  "effectSizeLabel": "log2(Fold Change)",
  "pValueFloor": "1e-200",
  "adjustedPValueFloor": null,
  "statistics": [
    { "effectSize": "-0.218035922112735",
      "pValue": "0.350285751849808",
      "adjustedPValue": "0.46960449943855",
      "pointID": "PF3D7_0100100" },
    { "effectSize": "3.94437533216012",
      "pValue": "1.95781599815607e-05",
      "adjustedPValue": "0.000137772236907279",
      "pointID": "PF3D7_0100200" },
    ...
  ]
}
```

Measured facts:

- **5511** statistics rows from 5720 genes in the study; DESeq drops the rest.
- The response was **byte-identical** (712323 bytes, same SHA-1) to
  `POST /computes/differentialexpression/statistics` and to
  `GET /jobs/{id}/files/output-stats`. There is no added value in going through
  the app endpoint for this visualization.
- Every numeric field is a **string**, not a number.
- **The wire field is `pointID`, capital ID.** `schema/url/compute/computes/differentialExpression.raml`
  declares `pointId`. The RAML is wrong about the case; the WDK bridge plugin
  parses `pointID`, and the live response uses `pointID`.
- `pValueFloor` and `adjustedPValueFloor` are on the wire but are **not in the
  RAML** `DifferentialExpressionStatsResponse`, which lists only
  `effectSizeLabel` and `statistics`. `adjustedPValueFloor` was `null`.
- **A row can omit `pValue` and `adjustedPValue`.** Exactly one of 5511 did:
  `{"effectSize":"-1.49447459261845","pointID":"PF3D7_MIT04200"}`. A consumer
  that assumes four keys per row will throw. The WDK bridge plugin survives this
  by catching `NumberFormatException` per row and dropping it.
- `pointID` is the gene id directly (`PF3D7_0100100`) when `identifierVariable`
  is the gene column. On `differentialabundance` it is
  `{entityId}.{collectionId}_{member}`.

Applying `effectSizeThreshold: 1` and `significanceThreshold: 0.05` to this
response by hand yields **1543** genes (529 with positive effect size, 1014
negative). The same thresholds through the WDK bridge search
`GenesByEdaVizWithCompute` returned `displayTotalCount` **1543** and
`totalCount` **1571** transcripts, first record `PF3D7_0100200`. The client-side
threshold and the WDK step agree exactly. See
[eda-wdk-bridge.md](eda-wdk-bridge.md) and
[notebook-presets.md](notebook-presets.md) for that path.

The `differentialabundance` volcanoplot is the same request shape
(`config: EmptyDataPluginSpec`) but its response is
`DifferentialAbundanceStatsResponse`, where `statistics` is a **single object of
parallel arrays** (`{effectSize: string[], pValue: string[], adjustedPValue:
string[], pointId: string[]}`), not an array of objects. Schema-derived; not
live-verified, since the app is MicrobiomeDB-only.

## dimensionalityreduction scatterplot (live-verified)

Request type `DimensionalityReductionScatterplotPostRequest`:
`computeConfig: DimensionalityReductionComputeConfig`, `config: ScatterplotSpec`
(the **full** pass-through scatterplot spec, not the narrowed
`ScatterplotWith1ComputeSpec`).

The axes are the compute's **computed variables**. Read `PC1` and `PC2` from
`POST /computes/dimensionalityreduction/meta` and then name them as ordinary
`VariableSpec` values:

```json
{
  "studyId": "STUDY_e973eadd57",
  "filters": [],
  "computeConfig": {
    "identifierVariable": {"entityId":"ENT_fd574cd6","variableId":"VEUPATHDB_GENE_ID"},
    "valueVariable": {"entityId":"ENT_fd574cd6","variableId":"SEQUENCE_READ_COUNT_SENSE"},
    "nPCs": 2, "dataFormat": "rawCounts"
  },
  "config": {
    "outputEntityId": "ENT_8151325d",
    "valueSpec": "raw",
    "correlationMethod": "none",
    "xAxisVariable": {"entityId":"ENT_8151325d","variableId":"PC1"},
    "yAxisVariable": {"entityId":"ENT_8151325d","variableId":"PC2"},
    "overlayVariable": {"entityId":"ENT_8151325d","variableId":"VAR_081ab087"},
    "returnPointIds": true
  }
}
```

Omitting `yAxisVariable` returned `500 {"status":"server-error","message":"No
value present","requestId":"..."}`. A missing required field in a visualization
`config` is a **500, not a 422**; the compute endpoints validate better than the
visualization endpoints do.

Live response, one series per overlay value, axes as parallel string arrays:

```json
{"scatterplot":{"data":[
  {"overlayVariableDetails":{"variableId":"VAR_081ab087","entityId":"ENT_8151325d","value":"febrile"},
   "seriesX":["0.443609763729234","45.4558380786033", ...],
   "seriesY":["5.12424133133646","1.92767239157473", ...],
   "pointIds":["PB31_41C_Rep1","PB31_41C_Rep2", ...]},
  {"overlayVariableDetails":{... "value":"normal"}, "seriesX":[...], "seriesY":[...], "pointIds":[...]}],
 "config":{"variables":[
   {"variableClass":"native","variableSpec":{"variableId":"VAR_081ab087","entityId":"ENT_8151325d"},
    "plotReference":"overlay","dataType":"string","dataShape":"categorical", ...},
   {"variableClass":"computed","variableSpec":{"variableId":"PC1","entityId":"ENT_8151325d"},
    "plotReference":"xAxis","displayName":"PC 1 (54.35% variance)",
    "displayRangeMin":"-61.4351512946123","displayRangeMax":"63.5443711576177", ...},
   {"variableClass":"computed","variableSpec":{"variableId":"PC2","entityId":"ENT_8151325d"},
    "plotReference":"yAxis","displayName":"PC 2 (12.79% variance)", ...}],
  "completeCasesAllVars":12,"completeCasesAxesVars":12}},
 "sampleSizeTable":[...],"completeCasesTable":[...]}
```

`config.variables` is a `VariableMapping[]` and is where the per-cent-variance
axis labels come from. `variableClass` is `native | derived | computed`;
`plotReference` is one of `xAxis, yAxis, zAxis, overlay, facet1, facet2, geo,
latitude, longitude, undefined`.

The app's `dataElementConstraints` from `GET /eda/apps` restrict only
`overlayVariable`: not required, exactly one variable, and either at most 8
distinct values or a `number`/`integer` type. Its `dataElementDependencyOrder`
is `[["yAxisVariable","xAxisVariable"],["overlayVariable"]]`.

## correlation bipartitenetwork (live-verified)

Request type `CorrelationBipartitenetworkPostRequest`:
`computeConfig: CorrelationConfig`, `config: CorrelationNetworkSpec`.

`CorrelationNetworkSpec`:

| Field | Type | Required |
|---|---|---|
| `significanceThreshold` | number | no |
| `correlationCoefThreshold` | number | no |
| `layout` | `none \| force \| circle \| nicely` | no |
| `degree` | boolean | yes |
| `correlationDirection` | `both \| positive \| negative` | no |

Unlike volcanoplot, **this visualization does apply its thresholds
server-side**: the response echoes them and the node and link sets are already
filtered. Live on `STUDY_fd06cb37d3` with `significanceThreshold: 0.05` and
`correlationCoefThreshold: 0.5`:

```json
{"bipartitenetwork":{"data":{
  "nodes":[{"id":"ENT_2caaf3f6.VAR_08d9c284","degree":1},
           {"id":"ENT_8151325d.VAR_0e0a2992","degree":1},
           {"id":"ENT_2caaf3f6.VAR_01a5d30e","degree":1},
           {"id":"ENT_8151325d.VAR_743d1321","degree":1}],
  "links":[{"source":{"id":"ENT_2caaf3f6.VAR_08d9c284"},
            "target":{"id":"ENT_8151325d.VAR_0e0a2992"},
            "weight":"0.6254682","color":"1"},
           {"source":{"id":"ENT_2caaf3f6.VAR_01a5d30e"},
            "target":{"id":"ENT_8151325d.VAR_743d1321"},
            "weight":"0.5318815","color":"1"}],
  "partitions":[{"nodeIds":["ENT_2caaf3f6.VAR_08d9c284","ENT_2caaf3f6.VAR_01a5d30e"]},
                {"nodeIds":["ENT_8151325d.VAR_0e0a2992","ENT_8151325d.VAR_743d1321"]}]},
 "config":{"partitionsMetadata":["assay","sampleMetadata"]}},
 "significanceThreshold":0.05,"correlationCoefThreshold":0.5}
```

Node ids are `{entityId}.{variableId}`. `partitions` always has exactly two
entries for a bipartite network and `partitionsMetadata` names them. `weight`
is a string; `color` is a string flag. `selfcorrelation`'s `unipartitenetwork`
uses the same `config` type but returns `NetworkPostResponse` (a flat
`network` with no partitions); schema-derived.

## Pass-through plot shapes

All from `schema/url/data/pass/` and `schema/url/data/plots.raml`. Every
pass-through response has the same envelope: one key named after the plot, plus
`sampleSizeTable[]` and `completeCasesTable[]`.

### histogram (live-verified)

`HistogramSpec` requires `outputEntityId`, `xAxisVariable`, `barMode`
(`overlay | stack`), `valueSpec` and `binSpec`; optional `overlayVariable`,
`facetVariable` (at most 2), `showMissingness`, `viewport`. `BinSpec` is
`{type?: binWidth | numBins, value?, units?, range?}`.

```
POST /eda/apps/distributions/visualizations/histogram
{"studyId":"STUDY_e973eadd57","filters":[],"config":{
  "outputEntityId":"ENT_8151325d",
  "xAxisVariable":{"entityId":"ENT_8151325d","variableId":"VAR_7033e90f"},
  "barMode":"stack","valueSpec":"count","binSpec":{"type":"binWidth","value":1}}}

-> 200
{"histogram":{"data":[{"binLabel":["[37, 38)","[41, 42]"],"value":[6,6],
                       "binStart":["37","41"],"binEnd":["38","42"]}],
  "config":{"variables":[{"variableClass":"native", ...,"plotReference":"xAxis",
                          "dataType":"integer","dataShape":"continuous", ...}],
            "completeCasesAllVars":12,"completeCasesAxesVars":12,
            "summary":{"min":"37","q1":"37","median":"39","mean":"39","q3":"41","max":"41"},
            "viewport":{"xMin":"37","xMax":"41"},
            "binSpec":{"type":"binWidth","value":1},
            "binSlider":{"min":1,"max":2,"step":1}}},
 "sampleSizeTable":[{"xVariableDetails":{"variableId":"VAR_7033e90f","entityId":"ENT_8151325d",
                                          "value":["37","41"]},"size":[6,6]}],
 "completeCasesTable":[{"variableDetails":{"variableId":"VAR_7033e90f","entityId":"ENT_8151325d"},
                        "completeCases":12}]}
```

`HistogramData` is parallel arrays (`value: number[]`, `binStart`, `binEnd`,
`binLabel` as `string[]`) with optional `overlayVariableDetails` and
`facetVariableDetails`. `HistogramConfig` adds `binSlider`, `binSpec`,
`summary` and `viewport` on top of `PlotConfig`.

### barplot (live-verified)

`BarplotSpec` requires `outputEntityId`, `xAxisVariable`, `barMode`
(`group | stack`) and `valueSpec`; optional `overlayVariable`, `facetVariable`,
`showMissingness`. Note the `barMode` enum differs from histogram's.

```
POST /eda/apps/countsandproportions/visualizations/barplot
{"studyId":"STUDY_e973eadd57","filters":[],"config":{
  "outputEntityId":"ENT_8151325d",
  "xAxisVariable":{"entityId":"ENT_8151325d","variableId":"VAR_84f17484"},
  "overlayVariable":{"entityId":"ENT_8151325d","variableId":"VAR_081ab087"},
  "barMode":"group","valueSpec":"count"}}

-> 200
{"barplot":{"data":[
   {"overlayVariableDetails":{"variableId":"VAR_081ab087","entityId":"ENT_8151325d","value":"febrile"},
    "label":["delta-DHC mutant","delta-LRR5 mutant","wildtype"],"value":[2,2,2]},
   {"overlayVariableDetails":{... "value":"normal"},
    "label":["delta-DHC mutant","delta-LRR5 mutant","wildtype"],"value":[2,2,2]}],
  "config":{"variables":[ ... xAxis ..., ... overlay ... ],
            "completeCasesAllVars":12,"completeCasesAxesVars":12}},
 "sampleSizeTable":[...],"completeCasesTable":[...]}
```

`BarplotData` is `{label: string[], value: number[]}` plus optional strata
details. One `data` entry per overlay/facet combination.

### boxplot (schema-derived)

`BoxplotSpec` requires `outputEntityId`, `xAxisVariable`, `yAxisVariable`,
`points` (`outliers | all`), `mean` and `computeStats` (both the string enum
`'TRUE' | 'FALSE'`, not booleans); optional `overlayVariable`,
`facetVariable`, `maxAllowedDataPoints`, `showMissingness`.
`BoxplotPostResponse` is `{boxplot: {data: BoxplotData[], config: PlotConfig},
sampleSizeTable[], completeCasesTable[], statsTable?: BoxplotStatsTable[]}`.
`BoxplotData` carries parallel `lowerfence`, `upperfence`, `q1`, `q3` number
arrays plus strata details.

The compute-backed boxplots (`alphadiv`, `abundance`) use the narrowed
`BoxplotWith1ComputeSpec` instead: no `yAxisVariable`, because the y axis is
always the computed variable, and `xAxisVariable` becomes optional.

### scatterplot, pass-through (schema-derived)

`ScatterplotSpec` requires `outputEntityId`, `valueSpec`
(`raw | smoothedMeanWithRaw | bestFitLineWithRaw`), `xAxisVariable`,
`yAxisVariable` and `correlationMethod`
(`none | spearman | pearson | sparcc`); optional `overlayVariable`,
`facetVariable`, `maxAllowedDataPoints`, `returnPointIds`. `ScatterplotData`
carries `seriesX`/`seriesY` as `string[]` plus optional `smoothedMeanX`,
`smoothedMeanY`, `smoothedMeanSE`, `smoothedMeanError` and `pointIds`.
`betadiv`'s scatterplot uses a further narrowed `BetaDivScatterplotSpec` with no
axes and no faceting at all.

## Shared response types

From `schema/url/data/plots.raml`:

- `PlotConfig` = `{completeCasesAllVars: number, completeCasesAxesVars: number,
  variables: VariableMapping[]}`.
- `SampleSizeTable` = `{xVariableDetails?: StrataVariableDetails[],
  overlayVariableDetails?, facetVariableDetails?, size: number[]}`.
- `VariableCompleteCases` = `{variableDetails: VariableSpec, completeCases:
  number}`.
- `StrataVariableDetails` = `VariableSpec` plus `value: string`.
- `VariableMapping` (in `schema/url/common/compute.raml`) =
  `{variableClass, variableSpec, plotReference, dataType, dataShape,
  displayName?, displayRangeMin?, displayRangeMax?, vocabulary?, imputeZero,
  hasStudyDependentVocabulary?, isCollection, members?}`.

One legacy shape to expect in stored analyses: `LegacyLabeledRange` is
`{binStart, binEnd, binLabel}`, and `schema/url/data/visualizations.raml`
carries a FIXME saying conversion to `LabeledRange`
(`{min, max, label}`) would need a database migration. Compute
comparators use the `LabeledRange` form; some visualization payloads use the
legacy one. The two are not interchangeable.

## What this means for PathFinder

- **EDA sends data, never images.** Every response above is JSON arrays. Our own
  chart components can render all of it, and nothing from
  `web-monorepo`'s React needs importing.
- **The volcanoplot endpoint adds nothing over the compute's statistics file.**
  They were byte-identical live. A client can read `/computes/{name}/statistics`
  and skip the app endpoint for this app.
- **Thresholding is a client concern for volcano, a server concern for network.**
  The volcanoplot `config` is an empty object; the bipartitenetwork `config`
  filters. Do not build one abstraction over both.
- **Visualization `config` validation is weak.** A missing required field
  returned 500. Validate the spec against the app's
  `dataElementConstraints` from `GET /eda/apps` before posting.
- **Per-project availability is data, from `GET /eda/apps`.** It changes between
  releases and is already returned in one call; do not hardcode the table above.
