---
type: Reference
title: EDA's genomics and WDK relations
description: How dataset presenters stamp per-dataset EDA searches, how VDI user datasets become EDA studies a WDK search can bind, how /eda/permissions gates both, and every place EDA reaches a genomics site beyond the analysis-spec parameter.
tags: [eda, wdk, apicommonmodel, vdi, permissions, dataset-presenters, dst-templates, genomics]
generated: { by: claude-code/opus-5, at: 2026-08-27T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-27T00:00:00Z }
status: stable
---

# EDA's genomics and WDK relations

[eda-wdk-bridge.md](eda-wdk-bridge.md) covers the one seam that turns an EDA
analysis into a WDK step. This document covers everything else EDA touches on a
genomics site: how the per-dataset searches are generated, how a user's own
upload becomes a study those searches can bind, how access is enforced, and the
two EDA relations that never go through `eda_analysis_spec` at all.

Upstream commits read on 2026-08-27:
`ApiCommonModel` `b4acd83696ac7706699078db7759f1b07a589a32`,
`ApiCommonWebService` `069d7257e22e9a53c4ec61c7828393a7ae5c588a`,
`EbrcModelCommon` `dfe7cc6bcfe7abd88d08cef4ae5a49607411689f`,
`web-monorepo` `3e04f4ff37b7a960fcb2edcf3f65dba876d14815`,
`service-eda` `b3bb8bac06de4340b4b2c21d9aa4a94d9b3de61f`,
`vdi-lib-plugin-eda` `a09a1606018612696e0cf177bd571e089b36f91b`.
Live values are from plasmodb.org on 2026-08-27 with a registered
(non-guest) `Authorization` cookie.

## Four relations, not one

EDA reaches a genomics WDK in four independent ways. Only the first is the
bridge.

| Relation | Mechanism | Who resolves it |
|---|---|---|
| 1. Subset or compute as a gene result | `eda_analysis_spec` + `eda_dataset_id` on a process query | `org.apidb.apicomplexa.wsfplugin.eda.*` calling the EDA service over HTTP |
| 2. Record-page tables and per-gene attribute columns | SQL against `eda.attributevalue_*` / `eda.attributegraph_*` / `eda.ancestors_*`, injected by `.dst` templates | the site database, no EDA service call |
| 3. Vocabulary and metadata for a classic WDK param | SQL against the same `eda.*` tables, feeding a `filterParam`'s ontology and metadata queries | the site database |
| 4. Sample and strain identity for SNP / CNV searches | `variantParams.eda_sample_table_suffix` interpolated into an `eda.attributevalue_*` table name | the site database, then HSSS plugins |

Relations 2, 3 and 4 read the installed EDA tables directly and never call
`/eda`. A consumer that models EDA as "the service behind the spec parameter"
misses three quarters of the surface.

## Per-dataset search generation

### The injector computes the ids

A curated EDA-backed dataset has a `DatasetInjector` subclass of
`GenomicsEDAStudy`
(`EbrcModelCommon/Model/src/main/java/org/apidb/apicommon/model/datasetInjector/GenomicsEDAStudy.java`).
Its `injectTemplates()` runs `setEdaStudyInternalAbbrev()` and
`setEdaEntityAbbrev()` before injecting any template, and the first of those is
the whole id story:

```java
public void setEdaStudyInternalAbbrev() {
    String datasetName = getDatasetName();
    String stableId = "s" + sha1First10(datasetName);
    setPropValue("edaStudyStableId", stableId);
}
```

`sha1First10` is the first 10 hex characters of `SHA-1(datasetName)`. Three
identifiers fall out of that one hash, and the naming is misleading in two of
them:

- `${edaStudyStableId}` (the `.dst` property) is the study's **internal
  abbreviation**, `s<sha1[:10]>`, not a `STUDY_` id. It is half of every EDA
  table name the templates write.
- `${presenterId}` (the dataset presenter id, and the `eda_dataset_id` default)
  is `DS_<sha1[:10]>`.
- `/eda/studies[].sha1hash` is the full `SHA-1(datasetName)`.

Measured, live: `SHA-1("PlasmoDB_Rod_Mal_Phenotype_RSRC")` is
`53f554ec6aee372f6489f0bccc0b58fbdb7ad643`; `/eda/studies` reports that exact
string as the `sha1hash` of `DS_53f554ec6a`; and
`GenesByPhenotypeEdaSubset_PlasmoDB_Rod_Mal_Phenotype_RSRC` defaults
`eda_dataset_id` to `DS_53f554ec6a`. The same held for
`SHA-1("PlasmoDB_Crompton_Mali_AntibodyArray_RSRC")` -> `24d441b301` ->
`DS_24d441b301`. Across all 747 curated studies live,
`sha1hash[:10] == datasetId[3:]` held **747 of 747**.

**The `STUDY_` id is not derivable.** `id[6:] == datasetId[3:]` held for only
**684 of 747** curated studies. A live counterexample sits on a shipped search:
`GenesByRNASeqpfal3D7_Lee_Gambian_ebi_rnaSeq_RSRCWGCNAModules` defaults
`eda_dataset_id` to `DS_eeca6a5476`, whose study is `STUDY_fd06cb37d3`. This is
why the WSF plugin resolves the pair through `/eda/permissions` rather than
computing it (see [Permissions](#permissions-and-dataset-access)).

### The entity abbreviation is a constant per family

`setEdaEntityAbbrev()` is abstract on `GenomicsEDAStudy` and each subclass
hard-codes a literal. The EDA tables a template writes are therefore
`eda.attributevalue_s<sha1[:10]>_<literal>`.

| Injector | `edaEntityAbbrev` | `.dst` file | Templates injected | Question stamped | Query ref | `edaNotebookType` |
|---|---|---|---|---|---|---|
| `PhenotypeEDAStudy` | `gnPhntyD` | `phenotype.dst` | `phenotypeEdaQuestion`, `phenotypeEdaGeneTableSql`, `phenotypeDataTableGeneTableSql`, `phenotypeEdaAttributeQueriesNumeric`, `phenotypeEdaAttributeQueriesString`, `phenotypeEdaAttributeRef`, `phenotypeEdaAttributeCategory` | `GenesByPhenotypeEdaSubset_${datasetName}` | `GeneId.GenesByEdaSubsetGeneric` | none |
| `AntibodyArrayEDAStudy` | `AntbdyAr` | `antibodyArray.dst` | `antibodyArrayEdaQuestion`, `antibodyArrayEdaGeneTableSql`, `antibodyArrayDataTableGeneTableSql` | `GenesByAntibodyArrayEdaSubset_${datasetName}` | `GeneId.GenesByEdaVizWithCompute` | `antibodyArrayNotebook` |
| `CellularLocalizationEDAStudy` | `hyprLptD`, or `lopitDat` for `ToxoDB_tgonME49_LOPIT_CellularLocalization_RSRC` | `cellularLocalization.dst` | the seven `cellularLocalizationEda*` templates, mirroring phenotype | `GenesByCellularLocalizationEdaSubset_${datasetName}` | `GeneId.GenesByEdaSubsetGeneric` | none |
| `ChIPChip` | `sample` | `chipchip.dst` | `chipchipFilterParam`, `chipchipParamQueries`, `chipchipQuery`, `chipchipQuestion`, only when `hasCalledPeaks` | `GenesByChIPchip${cleanDatasetName}` | `GeneId.GenesByChIPchip${cleanDatasetName}` (SQL) | none |
| `RFLPEDAStudy` | (empty override) | none | `injectTemplates()` is empty | none | none | none |

Two corrections this table carries against a name-based reading of the `.dst`
set:

- **`chipchip.dst` stamps no EDA search.** Its gene query is a `sqlQuery` over
  `webready.ChIPchipTranscript_p` and `study.ProtocolAppNode`. EDA appears only
  as relation 3, below.
- **`RFLPEDAStudy` injects nothing.** It exists to set the public-access
  properties and the sha1-derived abbreviations, so an RFLP study is an EDA
  study with no WDK search of its own.

The RNA-Seq differential-expression and WGCNA searches come from
`rnaSeqTemplates.dst` (`rnaSeqDESeqQuestion`, `rnaSeqWGCNAModulesQuestion`),
which is injected by the RNA-Seq presenters rather than by a `GenomicsEDAStudy`
subclass; those templates take `presenterId` directly.

### The question template, quoted

`phenotype.dst`, template `phenotypeEdaQuestion` (props `presenterId`,
`datasetName`, `datasetDisplayName`, `datasetShortDisplayName`,
`buildNumberIntroduced`, `includeProjects`, `phenotypeWdkAttributes`):

```xml
<question name="GenesByPhenotypeEdaSubset_${datasetName}" ...
     queryRef="GeneId.GenesByEdaSubsetGeneric"
     recordClassRef="TranscriptRecordClasses.TranscriptRecordClass">
    <paramRef ref="geneParams.eda_dataset_id" default="${presenterId}" visible="false"/>
    <paramRef ref="geneParams.eda_analysis_spec" allowEmpty="true" prompt="Filter genes based on phenotype data"/>
```

`antibodyArray.dst`, template `antibodyArrayEdaQuestion`, differs in three
places and those three places are the whole compute story: `queryRef` is
`GeneId.GenesByEdaVizWithCompute`, it declares
`<propertyList name="edaNotebookType"><value>antibodyArrayNotebook</value></propertyList>`,
and it declares `effectSize` and `pValue` as `<dynamicAttributes>` with
`sorting="effectSize desc"`. The same three appear in `rnaSeqDESeqQuestion`
with `differentialExpressionNotebook`.

### Record pages read the EDA tables in SQL

The remaining templates in each `.dst` file are pure SQL against the installed
tables, injected into `geneTableQueries.xml`, `transcriptAttributeQueries.xml`
and `transcriptRecord.xml`. `phenotypeEdaGeneTableSql`, in full:

```sql
UNION
SELECT '${datasetName}' AS dataset_name , string_value AS source_id
FROM eda.ATTRIBUTEvalue_${edaStudyStableId}_${edaEntityAbbrev} av
WHERE av.attribute_stable_id = 'VEUPATHDB_GENE_ID'
```

Three shapes follow from there:

- **A dataset-listing table.** `phenotypeEdaGeneTableSql` and
  `antibodyArrayEdaGeneTableSql` add one `UNION` arm per dataset to the table
  that answers "which EDA datasets mention this gene".
- **A per-value data table.** `phenotypeDataTableGeneTableSql` joins
  `attributevalue` to `attributegraph` for the variable's `display_name`, and
  to `apidbtuning.GeneId` to map the gene id, excluding the
  `VEUPATHDB_GENE_ID` attribute itself.
  `antibodyArrayDataTableGeneTableSql` additionally joins
  `eda.ancestors_${edaStudyStableId}_${edaEntityAbbrev}` to recover the sample,
  because the measurement entity is a child of the sample entity, and it uses
  `UNION ALL` with a comment stating why: two samples may record the same
  intensity for the same gene, and `UNION` would silently drop one.
- **Per-gene attribute columns.** `phenotypeEdaAttributeQueriesNumeric` and
  `...String` wrap `public.crosstab` over the EDA tables to pivot each variable
  into a transcript attribute column, named
  `CONCAT('${edaStudyStableId}_', stable_id)`. They filter on
  `ag.has_values = 1`, split on `data_type IN ('number','integer')`, and skip
  variables whose `hidden` JSON array contains `"variableTree"`. The matching
  `Meta...` query declares each column's reporter: `histogram` for numeric,
  `wordCloud` (`EbrcWordCloudAttributeReporter`) for string.

Live on plasmodb.org, the `gene` record class exposes 75 tables, of which four
are EDA-injected: `EdaPhenotypeDatasets`,
`EdaPhenotypeGraphsDataTable`, `EdaAntibodyArrayDatasets`,
`EdaAntibodyArrayGraphsDataTable`. Those names come from the injectors'
`addModelReferences()`. Fetching gene `PF3D7_1133400` returned 1
`EdaPhenotypeDatasets` row and 5 `EdaAntibodyArrayDatasets` rows.

## The 68-search census, and why names do not find them

On plasmodb.org, the `transcript` record type lists **359** searches. **68** of
them declare `eda_analysis_spec` in `paramNames`. Only **13** have `Eda` in the
name.

| `queryName` | searches |
|---|---|
| `GenesByEdaVizWithCompute` | 58 |
| `GenesByEdaSubsetGeneric` | 6 |
| `GenesByEdaSubset` | 1 |
| `GenesByPhenotypeUserDataset` | 1 |
| `GenesByDESeqUserDataset` | 1 |
| `GenesByWGCNAModule` | 1 |

The 58 `GenesByEdaVizWithCompute` searches are 52 named
`GenesByRNASeq<dataset>DESeq`, 5 named `GenesByAntibodyArrayEdaSubset_*`, and
the bare generic search. **The invariant: an EDA-backed search is identified by
the presence of the `eda_analysis_spec` parameter, never by its name.** A
name-based filter finds 13 of 68.

Of the 68, **59** carry an `edaNotebookType` property: 53
`differentialExpressionNotebook` (the 52 per-dataset DESeq searches plus
`GenesByDESeqUserDataset`), 5 `antibodyArrayNotebook`, 1
`wgcnaCorrelationNotebook`. The other 9 do not.

## `GenesByWGCNAModule`: a spec parameter nothing reads

`geneQueries.xml` declares `GenesByWGCNAModule` as a `sqlQuery`, not a
`processQuery`, and it takes five parameters: `eda_dataset_id`,
`eda_analysis_spec`, `wgcnaParam`, `wgcnaDataset`,
`wgcna_correlation_cutoff`. Its SQL is:

```sql
SELECT ta.source_id, ta.gene_source_id, 'Y' as matched_result,
       nfw.correlation_coefficient, ta.project_id
FROM webready.TranscriptAttributes_p ta, apidb.nafeaturewgcnaresults nfw
WHERE ta.gene_na_feature_id = nfw.na_feature_id
  AND nfw.protocol_app_node_id = $$wgcnaParam$$
  AND nfw.correlation_coefficient >= $$wgcna_correlation_cutoff$$
```

Neither `$$eda_analysis_spec$$` nor `$$eda_dataset_id$$` appears. The two EDA
parameters exist so that the `wgcnaCorrelationNotebook` can mount (it needs a
study to explore, which is `eda_dataset_id`) and so that the notebook's own
state has somewhere to live; the gene result comes entirely from
`wgcnaParam` and `wgcna_correlation_cutoff`, which the notebook writes through
its `wdkparam` cell. Live, that search defaults `wgcnaParam` to the string
`1_choose_module`.

So `eda_analysis_spec` has two distinct roles across the 68 searches: on 67 it
is the input the WSF plugin parses, and on one it is inert notebook state. A
consumer that sets only the spec on `GenesByWGCNAModule` changes nothing about
the answer.

## Relation 3: EDA as the vocabulary behind a classic parameter

`chipchip.dst` template `chipchipParamQueries` builds a WDK `filterParam`
(`chipchip_samples_${cleanDatasetName}`) whose ontology and metadata queries
are SQL over the EDA tables. The ontology query walks the variable tree with a
recursive CTE:

```sql
WITH RECURSIVE ontology_tree AS (
  SELECT stable_id, parent_stable_id, display_name, definition, data_type
  FROM eda.attributegraph_${edaStudyStableId}_${edaEntityAbbrev}
  WHERE has_values = 1
  UNION
  SELECT ag.stable_id, ag.parent_stable_id, ag.display_name, ag.definition, ag.data_type
  FROM eda.attributegraph_${edaStudyStableId}_${edaEntityAbbrev} ag
  JOIN ontology_tree ot ON ag.stable_id = ot.parent_stable_id
  WHERE ag.stable_id != 'sample'
)
```

and maps `data_type = 'category'` to a null WDK `type`. The metadata query
reads `attributevalue`, keyed to the sample by the hard-coded variable id
`VAR_709a2322`. The gene query then ignores EDA entirely.

This is the pattern to keep in mind whenever a search "feels" EDA-shaped: EDA
supplies the variable tree and the sample metadata, and the answer is a plain
WDK filterParam over GUS tables.

## Relation 4: EDA sample identity for SNP and CNV searches

`variantParams.xml` declares `eda_sample_table_suffix` as a hidden
`flatVocabParam` depending on `organismParams.organismSinglePick`, over
`VariantVQ.EdaSampleTableSuffix`:

```sql
SELECT DISTINCT
  s.internal_abbrev || '_' || lower(e.internal_abbrev) AS internal, ...
FROM apidb.datasource ds
  ... JOIN eda.studyexternaldatabaserelease sedr ON ...
  JOIN eda.study s ON s.study_id = sedr.study_id
  JOIN eda.entitytypegraph e ON e.study_id = s.study_id
WHERE ds.type = 'isolates' AND ds.subtype = 'Dna_Seq'
  AND tn.name = '$$organismSinglePick$$'
  AND s.internal_abbrev IS NOT NULL
```

The value is then interpolated into a table name by
`VariantVQ.SamplesMetadataByStudyWithRef`
(`eda.attributevalue_$$eda_sample_table_suffix$$`), which supplies the
`variation_sample_meta` filterParam. That param's internals are EDA sample
stable ids, plus one synthesized reference strain from
`apidb.organism.strain_abbrev`, and the HSSS `FindPolymorphisms*` plugins
consume them as strain names. The model file carries the constraint in a
comment: `variation_sample_meta` is a name contract with
`FindPolymorphismsPlugin.getStrainFilterParamName()`.

## VDI user datasets become EDA studies

### The type registry

VDI's plugin and dataset-type registry is the deployment config,
`webservices-quadlets` `vdi/config/config.yml` (read via the contents API on
2026-08-27; the raw URL 404s). The `plugins` map names each handler container
and the data types it serves:

| Plugin | `name` | `category` | `projectIds` | Becomes an EDA study |
|---|---|---|---|---|
| `wrangler` | `phenotype` | Phenotype | genomics projects | yes |
| `wrangler` | `rnaseqrc` | RNA-Seq raw counts | genomics projects | yes |
| `wrangler` | `isasimple` | Data Table | ClinEpiDB + 12 genomics projects | yes |
| `wrangler` | `stf` | Simple Dataset | ClinEpiDB | yes |
| `biom` | `biom` | BIOM | MicrobiomeDB | yes |
| `rnaseq` | `rnaseq` | RNA-Seq normalized counts | genomics projects | no (GUS `ud_nafeatureexpression`) |
| `genelist` | `genelist` | Gene List | genomics projects | no |
| `bigwig` | `bigwigfiles` | bigWig | genomics projects | no |
| `noop` | `lightweight` | Lightweight | - | no |

`phenotype` and `isasimple` set `usesDataProperties: true`, which is what
turns on the variable-annotations file that `install-meta` reads.

### The plugin lifecycle

A VDI handler plugin is a container exposing five scripts. `vdi-lib-plugin-eda`
ships the EDA-loading four - `check-compatibility`, `install-data`,
`install-meta`, `uninstall` - and both `vdi-plugin-wrangler` and
`vdi-plugin-biom` clone it in their `Dockerfile`;
`vdi-plugin-isasimple` clones the same code under its earlier name
`lib-vdi-plugin-study`. `vdi-plugin-wrangler` additionally installs
`VEuPathDB/study-wrangler` from GitHub at a pinned ref and runs
`bin/wrangle.R` in its `import` step, which is what "general purpose VDI plugin
to process files for EDA loading using the study-wrangler" means.

`install-data` is a thin wrapper over
`ApiCommonData::Load::InstallEdaStudyFromArtifacts`, taking
`(vdi_dataset_id, files_dir)` where `files_dir` holds an `install.json`
manifest and `*.cache` tabular files.

`install-meta` is the interesting one, because it names the join that links VDI
to EDA:

```sql
SELECT s.internal_abbrev AS study_abbrev,
       e.internal_abbrev AS entity_abbrev,
       e.stable_id AS entity_id
FROM   $schema.study s
JOIN   $schema.entitytypegraph e ON e.study_stable_id = s.stable_id
WHERE  s.user_dataset_id = ?
```

and then builds `"$schema.attributegraph_${studyAbbrev}_${entityAbbrev}"`. Two
consequences:

- **A user dataset lands in the same `eda.attributegraph_*` /
  `eda.attributevalue_*` tables as a curated study**, under the same
  `<study internal_abbrev>_<entity internal_abbrev>` naming. `eda.study` carries
  a `user_dataset_id` column, which is the only structural difference.
- **`install-meta` refuses a multi-entity user dataset**: "Multiple entities
  found for dataset '...'; multi-entity datasets not yet supported". It also
  validates the uploaded annotations file (columns `variable`, `label`,
  `definition`, in any order, 1 MB cap) against `provider_label` in the
  attributegraph table, and writes `display_name` and `definition` into both
  the per-study table and the shared `$schema.variable` table.

### The `EDAUD_` identifier, and the two searches that bind it

A user dataset's EDA **dataset** id is `EDAUD_<vdi_user_dataset_id>`, minted in
SQL by the WDK vocabulary queries rather than by EDA. From
`ApiCommonModel/Model/lib/wdk/model/questions/params/geneParams.xml`,
`GeneVQ.PhenotypeUserDataset`:

```sql
SELECT CONCAT('EDAUD_', aud.user_dataset_id) as term
     , CONCAT('EDAUD_', aud.user_dataset_id) as internal
     , aud.name as display
FROM @VDI_CONTROL_SCHEMA@.availableuserdatasets aud
WHERE (user_id = $$user_id$$ or is_public = true)
  AND type = 'phenotype'
  AND (project_id = '@PROJECT_ID@' or ('UniDB' = '@PROJECT_ID@' and 'ClinEpiDB' != project_id))
```

`GeneVQ.DESeqUserDataset` is the same query with `type = 'rnaseqrc'`. So the
VDI data-type name is the discriminant that decides which WDK search a user's
upload can feed.

The two searches, from `geneQueries.xml`:

```xml
<processQuery name="GenesByPhenotypeUserDataset" processName="org.apidb.apicomplexa.wsfplugin.eda.GeneEdaSubsetPlugin">
  <paramRef ref="userDatasetParams.eda_dataset_id" />
  <paramRef ref="geneParams.eda_analysis_spec"/>
  ...
<processQuery name="GenesByDESeqUserDataset" processName="org.apidb.apicomplexa.wsfplugin.eda.GeneEdaVizWithComputePlugin">
  <paramRef ref="userDatasetParams.eda_dataset_id"
            queryRef="GeneVQ.DESeqUserDataset"
            prompt="RNA-Seq Raw Counts User Dataset">
```

Both use the same two WSF plugins as the curated searches; only the dataset
parameter changes, from a hidden `stringParam` with a presenter-id default to a
visible `flatVocabParam` over the user's installed datasets.
`userDatasetParams.deseq_dataset_id` is declared in `geneParams.xml` with the
same vocabulary but is referenced by no query; `GenesByDESeqUserDataset`
overrides `eda_dataset_id`'s `queryRef` instead.

### The sentinel vocabulary term, and what it does

Both vocabulary queries end with a `UNION ALL` arm that fires only when the
primary result is empty:

```sql
select 'EDAUD_slI5M0RwIg0Zw' as term, 'EDAUD_slI5M0RwIg0Zw' as internal,
       'Upload a Phenotype User Dataset in My Workspace' as display
WHERE NOT EXISTS (SELECT 1 FROM primary_result)
```

This is a real WDK vocabulary entry pointing at no dataset. Measured live, with
an account that has no installed phenotype or raw-counts datasets on PlasmoDB,
`GET /record-types/transcript/searches/GenesByPhenotypeUserDataset?expandParams=true`
returns exactly one vocabulary row:

```
["EDAUD_slI5M0RwIg0Zw", "Upload a Phenotype User Dataset in My Workspace", null]
```

and `initialDisplayValue` is that same term. Running the search with it returns
**HTTP 400**, body:

```
Dataset with ID 'EDAUD_slI5M0RwIg0Zw' could not be found for this user.
```

That message is `AbstractEdaGenesPlugin.java:224`, the `orElseThrow` on
`findStudyId`. **The invariant: a `flatVocabParam` vocabulary of size one whose
display text starts with "Upload a" is an empty-state placeholder, not a
choice.** Any automated consumer that treats a vocabulary as the set of valid
values will pick it and get a 400.

### User studies live in the EDA APIs

On plasmodb.org, `GET /eda/studies` returned 759 entries: `sourceType`
`curated` 747, `user_submitted` 12. A `user_submitted` entry keys its
`datasetId` on `EDAUD_*` and carries an **empty** `sha1hash`:

```json
{
  "id": "STUDY_d77d15d7a5",
  "datasetId": "EDAUD_hpI5oZNAwl0AY",
  "sha1hash": "",
  "sourceType": "user_submitted",
  "displayName": "T. gondii PCR-RFLP genotypes in sea birds (Brazil), chickens (Mexico), and dolphins (Australia) - HARMONIZED",
  "lastModified": "2026-08-17T20:00:00-04:00",
  "description": "..."
}
```

`/eda/permissions` reports the same 12 with `isUserStudy: true` and
`sha1Hash: ""`. So the study `sha1hash` is not an invalidation key for a user
study; it is empty. Two of the 12 also carry no `shortDisplayName` and one
carries neither `shortDisplayName` nor `description` (a test dataset named
`test-dt-b2-july15-2026-1`).

None of the 12 appears in PlasmoDB's WDK user-dataset vocabularies, because
those filter on VDI `type` and `project_id` and these are ToxoDB-scoped
`isasimple` datasets. **A study being visible in `/eda` does not imply a WDK
search can bind it.**

## Permissions and dataset access

### The live shape

`GET https://plasmodb.org/eda/permissions` with a registered cookie returned
HTTP 200, 1,021,448 bytes, one top-level key `perDataset` with **880** entries.
A real entry for a public genomics dataset, verbatim:

```json
"DS_16bc228c8e": {
  "studyId": "STUDY_16bc228c8e",
  "sha1Hash": "16bc228c8ea7332e8b7a2df47e333ccc51c7f3cd",
  "isUserStudy": false,
  "displayName": "The role of the SREBP pathway in the secretion of lignocellulolytic enzymes",
  "shortDisplayName": "RNA-Seq WT, delta sah-2, Mclr-2 and Mclr-2 delta sah-2 strains",
  "description": "The SREBP pathway functions in ergosterol biosynthesis and adaptation to hypoxia. ...",
  "type": "end-user",
  "actionAuthorization": {
    "studyMetadata": true,
    "subsetting": true,
    "visualizations": true,
    "resultsFirstPage": true,
    "resultsAll": true
  },
  "isManager": false,
  "accessRequestStatus": "unrequested"
}
```

Across all 880 entries on this account: `type` was `end-user` 880 times,
`isUserStudy` false 868 / true 12, `accessRequestStatus` `unrequested` 880
times, `isManager` false 880 times, and `actionAuthorization` was all-true 880
times. Field presence varied: 856 entries carried all ten keys, 22 omitted
`shortDisplayName`, 2 omitted `description`.

Note the casing difference between endpoints: `/eda/permissions` uses
`sha1Hash`, `/eda/studies` uses `sha1hash`.

### The declared model

`service-eda` `schema/library.raml`:

- `PermissionsGetResponse { isStaff?: boolean = false, isOwner?: boolean = false, perDataset?: {<datasetId>: DatasetPermissionEntry} }`.
  All three are optional; `perDataset` "will be omitted" when the user is
  neither a provider nor an end user of any dataset. Our live response carried
  `perDataset` only, so `isStaff` and `isOwner` fell to their defaults.
- `DatasetPermissionEntry { studyId, sha1Hash, isUserStudy, displayName, shortDisplayName, description, type: DatasetPermissionLevel, actionAuthorization: ActionList, isManager?, accessRequestStatus: ApprovalStatus }`,
  `additionalProperties: false`.
- `DatasetPermissionLevel` is `provider | end-user`. `isManager` is documented
  as present only when `type = provider`; live it was present on every entry
  with value false.
- `ApprovalStatus` is `unrequested | approved | requested | denied`.
- `ActionList` is five booleans, and the RAML documents each one's scope:
  `studyMetadata` ("study metadata"), `subsetting` ("count, distribution"),
  `visualizations` ("all viz plugins"), `resultsFirstPage`
  ("offset:0, numRecords: <=20"), `resultsAll` ("any other tabular response").
- `StudyPermissionInfo`, the body of `GET /permissions/{dataset-id}`, is the
  narrow four-field form: `studyId`, `datasetId`, `isUserStudy`,
  `actionAuthorization`.

**`resultsAll` is the flag the bridge depends on.** The gene plugin POSTs
`/entities/{e}/tabular` and streams the whole gene column; that is "any other
tabular response". A dataset granting `resultsFirstPage` but not `resultsAll`
would authorize the subset count and the plot and refuse the gene list.

**RAML is not a strict schema for the wire.** `DatasetPermissionEntry` declares
`shortDisplayName` and `description` as required with
`additionalProperties: false`, and 24 of 880 live entries omit one or both. A
consumer must parse permissively.

### Restricted access, and where genomics differs from ClinEpiDB

`service-eda` `api.raml` carries the whole access-management surface alongside
the read endpoints: `/staff` (list, create, `PATCH /{staff-id}`),
`/dataset-providers` (list by `datasetId`, `PATCH /{provider-id}`),
`/dataset-end-users` (list by `datasetId` with an `approval` filter over
`ApprovalStatus`, create, `PATCH /{end-user-id}` where the id "consists of the
WDK user ID" plus the dataset), `/history`, and
`POST /approve-eligible-access-requests` ("Approve protected study requests in
which auto-approval duration has elapsed").

The model is therefore: a dataset has staff, providers and end users; an end
user's `ApprovalStatus` moves `unrequested -> requested -> approved | denied`,
possibly by an auto-approval timer; and the per-dataset `ActionList` is the
projection of that state onto five capabilities. This is the machinery
ClinEpiDB's protected studies need. On the genomics side, measured above, every
one of 880 datasets came back `end-user` / `unrequested` / all-true, so the
access state exists but is not exercised: genomics EDA datasets are effectively
open to any registered login, and the machinery is uniform rather than unused.

### Three invariants from `/eda/permissions`

`ApiCommonWebService/WSFPlugin/src/main/java/org/apidb/apicomplexa/wsfplugin/eda/AbstractEdaGenesPlugin.java`
resolves the dataset through this endpoint and nothing else:

```java
private Optional<String> findStudyId(String edaBaseUrl, String datasetId, Map<String,String> authHeader) {
  return readGetRequest(edaBaseUrl + "/permissions", authHeader, responseJson -> {
    JSONObject datasets = responseJson.getJSONObject("perDataset");
    if (!datasets.has(datasetId)) { ... }
    return Optional.of(datasets.getJSONObject(datasetId).getString("studyId"));
```

1. **Resolution and authorization are the same call.** A dataset the user
   cannot see is a dataset with no `perDataset` entry, so it resolves to
   nothing and the plugin raises "could not be found for this user". There is
   no separate access check to forget.
2. **`perDataset` is a superset of `/studies`.** Live, 880 permission entries
   against 759 studies: 121 dataset ids had a `studyId` but no `/studies` row,
   and 0 studies were missing from `perDataset`. The 121 are DNA-Seq and
   comparative-genomics datasets (for example `DS_0047daf254` ->
   `STUDY_a353a4fda1`, "SNP calls on WGS of F. verticillioides isolates"),
   and `GET /eda/studies/STUDY_a353a4fda1` returned 200 with a root entity
   `sample` described as "Sequenced isolates aligned to the fver7600 reference
   genome, across all dnaseq experiments". These back relation 4. So
   `/studies` is the browsable catalog, not the study universe.
3. **The spec's `studyId` field holds a DATASET id.** The plugin's own comment
   says so: `_datasetId = _analysisSpec.getString("studyId"); // misnamed; still
   need to look up study ID`, and its mismatch error ends "Note both values
   should be dataset IDs, not study IDs (old API)." The frontend agrees:
   `EdaSubsetParameter.tsx` reads `props.ctx.paramValues['eda_dataset_id']`
   into a local named `studyId` and passes it to both
   `<WorkspaceContainer studyId={...}>` and `makeNewAnalysis(studyId)`.

Two smaller plugin facts worth recording. The dataset parameter is documented
as optional in `getRequiredParameterNames()` ("value will be pulled off
analysis spec if omitted") but `getAnalysisSpec` throws
`PostValidationUserException` when it is null or blank, so it is required in
practice. And the plugin calls EDA over an internal URL,
`props.get("LOCALHOST") + props.get("EDA_SERVICE_URL")`, with
`Authorization: Bearer <the user's token>` taken from
`Utilities.CONTEXT_KEY_BEARER_TOKEN_STRING`; a missing token is a
`PluginModelException`, not a user error.

## Where EDA appears in the genomics-site UI

`web-monorepo/packages/sites/genomics-site/webapp/wdkCustomization/js/client/`
holds five EDA files: `pluginConfig.tsx` and, under
`components/questions/`, `EdaSubsetParameter.tsx` (plus its `.scss`),
`EdaNotebookParameter.tsx`, `EdaNotebookQuestionForm.tsx`, and
`GenesByEdaSubset.tsx`. Nothing else in the site imports `@veupathdb/eda`;
`routes.jsx` registers no EDA route.

`pluginConfig.tsx` routes on two predicates and nothing else.

```tsx
const isPhenotypeSubsetSearch: ClientPluginRegistryEntry<any>['test'] = ({ question }) =>
  question?.queryName === 'GenesByEdaSubsetGeneric' ||
  question?.queryName === 'GenesByPhenotypeUserDataset';
```

| Entry `type` | Selector | Component |
|---|---|---|
| `questionForm` | `name: 'GenesByPhenotypeUserDataset'` | `GenesByEdaSubset` |
| `questionFormParameter` | `name: 'eda_analysis_spec'`, `test: isPhenotypeSubsetSearch` | `EdaSubsetParameter` |
| `stepDetails` | `test: isPhenotypeSubsetSearch` | `EdaSubsetStepDetails` |
| `stepDetails` | `test: ({ question }) => (question?.properties?.edaNotebookType?.length ?? 0) > 0` | `EdaNotebookStepDetails` |
| `questionForm` | `test: ({ question }) => (question?.properties?.edaNotebookType?.length ?? 0) > 0` | `EdaNotebookQuestionForm` |

Two paths, therefore, and they are keyed on different things:

- **Subset-parameter path**, keyed on `queryName`. Only the
  `eda_analysis_spec` parameter's widget is replaced, by
  `EdaSubsetParameter`, which mounts `<WorkspaceContainer>` and EDA's
  `Subsetting` view with a `FilterChipList` and live counts from
  `useEntityCounts(filters)`; the rest of the form stays standard WDK. It
  serializes with `onParamValueChange(JSON.stringify(analysis))`.
- **Notebook path**, keyed on the `edaNotebookType` question property. The
  entire question form is replaced by `EdaNotebookQuestionForm`;
  `EdaNotebookParameter` mounts `EdaNotebookAnalysis` for
  `wdkState.questionProperties['edaNotebookType']?.[0]` and persists with
  `updateParamValue(param, JSON.stringify(analysis))`. Because it receives the
  whole `wdkState`, a notebook cell can write parameters other than
  `eda_analysis_spec` - which is how `wgcnaCorrelationNotebook` sets
  `wgcnaParam`.

Both step-details entries render through
`makeFormatEdaAnalysisSpec(edaServiceUrl)` from
`@veupathdb/eda/lib/notebook/Utils`, so a saved step shows a readable filter
summary rather than JSON.

**The two searches with no UI plugin.** `GenesByEdaSubset` and
`GenesByEdaVizWithCompute` match neither predicate: their `queryName` is not in
`isPhenotypeSubsetSearch` and they declare no `edaNotebookType`. They render
`eda_analysis_spec` as WDK's plain multiline string input. They are the
API-facing entry points, and they are the two an automated consumer should
prefer, because their behaviour is fully determined by the JSON.

## What to re-measure

Every count here is a live reading of one site on one day, and the underlying
data reloads per release. The stable facts are the mechanisms: the sha1
derivation, the `EDAUD_` scheme, the `perDataset` resolution path, the two UI
predicates, and the four relations. The counts (759 studies, 880 permission
entries, 68 spec-carrying searches, 4 gene tables) are measurements. Re-measure
them per site and per release rather than caching them; a study's
`/eda/studies[].sha1hash` is the invalidation key for a curated study, and is
empty for a user study.
