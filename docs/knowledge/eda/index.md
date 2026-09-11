# EDA

The specification and manual for VEuPathDB's Exploratory Data Analysis
platform: what it is, its semantics inside and out, how it reaches WDK
strategies. Every assertion was verified on
2026-08-27 against the VEuPathDB GitHub org (commit-pinned) or the live
deployments (plasmodb.org, clinepidb.org, microbiomedb.org), with real ids and
real counts; each document names its upstream and labels live-verified against
schema-derived claims.

Start with [What EDA is](what-eda-is.md), then read by subject.

## Orientation

- [What EDA is](what-eda-is.md) - the services, the study/entity/variable data model in brief, filters, computes, analyses, frontends

## The data and its semantics

- [Data model](data-model.md) - every field of study, entity, variable and collection on the wire, real entity trees from three deployments, the storage tables
- [Subsetting and tabular](subsetting-and-tabular.md) - cross-entity filter propagation proven with live counts, and the exact shapes of count, tabular, distribution, root-vocab and filter-aware-metadata
- [Filter algebra](filters.md) - the authoring contract: every filter type's JSON, AND composition, multiFilter, wire traps, and the service's error classes
- [Derived variables and merging](derived-variables-and-merging.md) - the twelve derivation plugins with exact configs, merge traversal semantics, persistence, and access control on row output

## Computation

- [Computes and jobs](computes-and-jobs.md) - every compute plugin's config schema, the derivable job identity, the six-state lifecycle live-observed, job control and output files
- [Apps and visualization data](visualizations.md) - the app catalog with per-project availability, and the request/response shapes of the plot-data endpoints

## The WDK side

- [The EDA-WDK bridge](eda-wdk-bridge.md) - how an EDA analysis becomes a WDK step, with live proofs of both the subset and the compute path
- [Notebook presets and the bridge boundary](notebook-presets.md) - the cell vocabulary, every upstream preset, the measured HTTP 202 delayed result, and why the compute bridge is volcano-only
- [Genomics and WDK relations](genomics-and-wdk-relations.md) - the four relations beyond the bridge: per-dataset search generation, record-page SQL, VDI user datasets, permissions, and SNP/CNV sample identity

## The API

- [REST surface](rest-surface.md) - the endpoints this client consumes, authentication, and the ten measured divergences from the pinned `service-eda` RAML that the recorded fixtures are gated against
