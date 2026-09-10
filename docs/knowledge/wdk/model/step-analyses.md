---
type: Reference
title: Step analyses - types, forms, and the four-call async protocol
description: What a step analysis is, why its form defaults are advisory rather than applied, the create-run-poll-fetch sequence and the two non-200 successes in it, and which parts of the surface a consuming application uses today.
tags: [wdk-alignment, step-analyses, enrichment, async, model]
generated: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
status: stable
---

Every permalink below is pinned to the sha recorded in [sources.md](../sources.md).

# A step analysis is a plugin the site model attaches to a search

WDK owns the lifecycle; it does not own the analysis.
[`StepAnalysis`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/analysis/StepAnalysis.java#L8-L24)
is an interface extending `ParameterContainer` - a name, display metadata, a
timeout, an analyzer instance, and a set of parameters exactly like a search's.
The implementations live in the site model, not in WDK, which is why
[sources.md](../sources.md) has to pin a fourth repository to say anything about
what an enrichment result contains ([WDK-ANS-007](../rules/searches-and-answers.md)).

Analyses are declared per question, so the available set is a property of the
step's search. `GET /users/{id}/steps/{stepId}/analysis-types`
[reads them off the step's question](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/user/StepAnalysisFormService.java#L92-L99).
On 2026-08-10, a `GenesByMolecularWeight` step on plasmodb.org and on
toxodb.org each offered exactly the same three: `go-enrichment`,
`pathway-enrichment`, `word-enrichment`, all reporting `isCacheable: false`.

The list is the summary form -
[`getStepAnalysisTypeJsonWithoutParams`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/StepAnalysisFormatter.java#L39-L51)
gives `name`, `displayName`, `shortDescription`, `description`,
`releaseVersion`, `customThumbnail`, `isCacheable`, plus `paramNames` and
`groups`, and no parameter documents. Fetch one by name to get those.

# The form endpoint returns defaults you must send back yourself

`GET .../analysis-types/{name}` returns a `{searchData, validation}` envelope,
the same shape as a search document. It is built at `ValidationLevel.DISPLAYABLE`
with `FILL_PARAM_IF_MISSING`
([`getStepAnalysisTypeDataFromName`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/user/StepAnalysisFormService.java#L108-L130)),
so every parameter comes back carrying an `initialDisplayValue`. Live on
plasmodb.org, `go-enrichment` reports five parameters:

| Parameter | Type | `initialDisplayValue` |
|---|---|---|
| `organism` | `single-pick-vocabulary` | `Plasmodium falciparum 3D7` |
| `goAssociationsOntologies` | `single-pick-vocabulary` | `Biological Process` |
| `goEvidenceCodes` | `multi-pick-vocabulary` | `["Computed","Curated"]` |
| `goSubset` | `single-pick-vocabulary` | `No` |
| `pValueCutoff` | `number` | `0.05` |

Creation does not use any of them.
[`createStepAnalysis`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/user/StepAnalysisInstanceService.java#L117-L155)
builds the form spec at `ValidationLevel.RUNNABLE` with **`FillStrategy.NO_FILL`**.
Posting `{"analysisName":"word-enrichment","parameters":{}}` is a 422 on both
sites, with `byKey` reporting `Cannot be empty.` for every parameter the form
had just supplied a default for. The two levels are the same document read
twice: `DISPLAYABLE` fills, `RUNNABLE` refuses to. Read the form, copy its
values, send them ([WDK-VALID-011](../rules/validation.md)).

Everything about the parameters themselves - the eleven types, the exact string
each puts on the wire, dependent vocabularies - is the search parameter system
unchanged, described in [parameters](parameters.md) and
[dependent parameters and vocabularies](dependent-params-and-vocabularies.md).
The analysis form endpoints mirror the search ones, including
[`refreshed-dependent-params`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/user/StepAnalysisFormService.java#L211-L220),
which takes the same `{changedParam, contextParamValues}` body.

# Create, run, poll, fetch - and two of the four are not 200

The four calls, all under `/users/{id}/steps/{stepId}/analyses`:

| Call | Success status | Body |
|---|---|---|
| `POST .../analyses` | 200 | the instance, `status: "CREATED"` |
| `POST .../analyses/{id}/result` | **202** | `{"status": "RUNNING"}` |
| `GET .../analyses/{id}/result/status` | 200 | `{"status": "<ExecutionStatus>"}` |
| `GET .../analyses/{id}/result` | 200, **or 204 with an empty body** | the plugin's JSON plus four keys |

[`runAnalysis`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/user/StepAnalysisInstanceService.java#L293-L309)
returns `Response.accepted()`, so the kick-off is a 202 by design and not the
delayed-result sentinel that shares the status code
([WDK-HTTP-003](../rules/auth-and-transport.md)). Its body carries the status
the run reached synchronously, which on both sites was `RUNNING`.

[`getStepAnalysisResult`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/user/StepAnalysisInstanceService.java#L258-L285)
returns `Response.noContent()` when there is no execution result, and otherwise
the plugin's own JSON with `contextHash`, `accessToken`, `downloadUrl` and
`propertiesUrl` added. Measured on both sites: fetching the result of a freshly
created instance is `204`, zero bytes, no content type
([WDK-VALID-008](../rules/validation.md)). It is not an empty result; it is not
a result.

[`getStepAnalysisResultStatus`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/user/StepAnalysisInstanceService.java#L311-L322)
is the only call that answers "is it done". A full lifecycle on plasmodb.org on
2026-08-10, `word-enrichment` over a 2365-gene step: `GET result` -> 204;
`GET status` -> `CREATED`; `POST result` -> 202 `RUNNING`; `GET status` three
seconds later -> `COMPLETE`; `GET result` -> 200. Identical on toxodb.org.

# Eleven statuses, and six of them mean "run it again"

[`ExecutionStatus`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/analysis/ExecutionStatus.java#L3-L14)
carries two booleans per constant, and they are not the same partition:

| Status | `requiresRerun` | `isTerminal` |
|---|---|---|
| `CREATED` | yes | no |
| `STEP_REVISED` | yes | no |
| `INVALID` | no | no |
| `PENDING` | no | no |
| `RUNNING` | no | no |
| `COMPLETE` | no | yes |
| `INTERRUPTED` | yes | yes |
| `ERROR` | yes | yes |
| `EXPIRED` | yes | no |
| `OUT_OF_DATE` | yes | no |
| `UNKNOWN` | no | no |

`isTerminal` means the plugin finished, successfully or not. `requiresRerun`
means re-running **the same instance** is the correct response, and it is the
flag WDK itself branches on:
[`runAnalysis`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/analysis/StepAnalysisFactoryImpl.java#L338-L374)
resets the execution to `PENDING` and re-executes when the stored status carries
it, and otherwise returns the stored status untouched. So a second `POST` to the
result path is either a re-run or a no-op, decided by the platform - there is
never a need to create a second instance. Six statuses carry the flag.
`INTERRUPTED` and `ERROR` carry both flags at once, which is the pair a client
written around "terminal means stop" gets wrong
([WDK-VALID-009](../rules/validation.md)).

A separate enum,
[`RevisionStatus`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/analysis/RevisionStatus.java#L3-L7),
tracks whether the instance has run since its step was last revised:
`STEP_CLEAN`, `NEW`, `STEP_DIRTY`. It never appears on the wire itself. What it
does is decide the status you get back when there is no cached execution:
[`calculateStatus`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/analysis/StepAnalysisFactoryImpl.java#L545-L581)
returns `INVALID` for an instance that is not runnable, then - if either the
execution record or the results directory is missing - maps `NEW` to `CREATED`,
`STEP_DIRTY` to `STEP_REVISED` and `STEP_CLEAN` to `OUT_OF_DATE`. Only when both
are intact does it return the execution's own stored status.

So three of the eleven statuses are not states an execution was ever in. They
are derived on read, which is why polling can hand you `OUT_OF_DATE` for an
analysis that completed successfully an hour ago: the cache was cleared, and the
correct response is to run it again.

# The instance list is two fields, and the instance detail is ten

This asymmetry is easy to miss and it breaks typed clients.
[`getStepAnalysisInstancesJson`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/StepAnalysisFormatter.java#L84-L95)
emits `analysisId` and `displayName` and nothing else. Confirmed on both sites:
`GET .../analyses` returns `[{"displayName":"Word Enrichment","analysisId":203635253}]`.
The service
[builds the instances at `ValidationLevel.NONE`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/user/StepAnalysisInstanceService.java#L172-L181)
for that call, which is consistent: there is nothing in the summary that a
validation could be about.

The single-instance document is
[the full shape](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/StepAnalysisFormatter.java#L53-L82):
`analysisId`, `stepId`, `analysisName`, `displayName`, `shortDescription`,
`description`, `userNotes`, `status`, `parameters`, `validation`. Two notes on
it. The formatter's own javadoc calls the parameter map `formParams`; the code
writes `JsonKeys.PARAMETERS`, so the key is `parameters`. And `userNotes` is
omitted entirely when null, as observed on both sites.

# Where the result shape comes from

Nothing in the result body except four keys is WDK's, and the rest is the
plugin's view model. That is [WDK-ANS-007](../rules/searches-and-answers.md),
which names the three plugins, their column keys, the fact that every value is
a JSON string, and the one column whose key does not match its label. It is not
restated here.

Worth repeating only as a pointer: the response carries `headerRow` and
`headerDescription`, a manifest keyed by exactly the `resultData` keys, so a
client can render an unfamiliar column instead of dropping it.

# Ownership, and the 404 that should have been a 403

All three verbs on `.../analyses/{analysisId}/result` route through
`StepAnalysisLookupMixin.getAnalysis`, which does its ownership check by hand in
two stages: a bad id or a path user who does not own the step is a 404, and a
third party without a matching `accessToken` is a 403. A caller can only ever
reach the first stage. The full account, including why that is a consequence of
addressing concrete user ids, is in
[users, auth and sessions](users-auth-and-sessions.md) and is not repeated here.

Confirmed live on both sites on 2026-08-10: `GET .../analyses/999999999/result`
returns **404** `Resource 'step analysis: 999999999' does not exist.`

# What the consuming applications run today

The analysis surface reaches one feature: enrichment.
`veupathdb-mcp: src/veupathdb_mcp/wdk/enrichment/parser.py:ANALYSIS_TYPE_MAP` maps
five internal analysis types onto the three WDK plugins - the three GO flavours
all resolve to `go-enrichment` and are separated by the
`goAssociationsOntologies` parameter. The lifecycle in
`src/veupathdb/wdk/strategy_api/analyses.py:run_step_analysis` is create, run,
poll, fetch, preceded by a zero-record standard report to force the step's answer
to be materialised, and
`veupathdb-mcp: src/veupathdb_mcp/wdk/params.py:extract_default_params`
reads the form document and sends its defaults back, which is the behaviour the
`NO_FILL` rule above requires.

The near frontier is everything else the platform already exposes and no caller
touches:

- `PATCH .../analyses/{id}` - rename an instance or attach user notes, so a
  researcher can label two enrichments of the same step.
- `DELETE .../analyses/{id}` - a new instance is created per run and none is
  ever removed.
- `GET .../analyses/{id}/resources?path=...` and `.../properties` - the
  `downloadUrl` and `propertiesUrl` already handed back in every result body,
  unused.
- `POST .../analysis-types/{name}/refreshed-dependent-params` and the two
  ontology-term-summary endpoints on the same path - the analysis form has the
  same dependent-parameter machinery as a search, and the form is currently read
  once and never refreshed, which is the same defect class as
  a dependent vocabulary read without its parents
  (`pathfinder: docs/knowledge/decisions/a-dependent-vocabulary-is-read-under-its-parents.md`).
- Non-enrichment plugins. The three seen here are what a transcript search
  offers on these two sites; the set is a property of the question, so a
  different record class can offer a different list, and a caller that assumes
  otherwise is wrong.
