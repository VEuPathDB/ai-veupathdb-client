---
type: Reference
title: The WDK REST surface, and which of it PathFinder actually calls
description: Every endpoint PathFinder touches plus the near-frontier ones it does not, with request and response shapes and the client method behind each.
tags: [wdk-alignment, rest, api]
generated: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
status: stable
---

# How to read this

Paths are relative to a site's service base, listed in [sources.md](../sources.md).
Every path and verb below was read from the JAX-RS annotations in WDK's service classes at
the pinned sha in [sources.md](../sources.md); no row repeats that permalink. The client
column names the PathFinder method that issues the call, relative to
`src/veupathdb/wdk/`, or says `unused` where WDK offers an
endpoint we do not call. The unused rows are here on purpose: they are the near frontier,
and knowing an endpoint exists is what stops the next feature from being built out of
three that do not fit.

`{userId}` is always a concrete numeric id in PathFinder, never the `current` alias, for
the reason in [WDK-HTTP-001](../rules/auth-and-transport.md). The single exception is the
call that resolves it.

**How the caller column was derived, and how to redo it.** Not by inspection. Every WDK
path literal under `apps/api/src/pathfinder`, excluding `tests/`, was extracted and mapped
to its enclosing function, and the column is that mapping. Anything absent from the
extraction is marked `unused`, so `unused` is a claim about the whole backend rather than
about one package. Redo it by grepping the backend
for string literals beginning `/users`, `/record-types`, `/strategy-lists`,
`/temporary-results`, `/ontologies`, `/login`, `/logout`, and then handling three things
that will otherwise give a wrong answer. Each of these has already caused a wrong row or a
false alarm once.

- **Discard PathFinder's own FastAPI route decorators.** `dev.py` and
  `veupathdb_auth.py` declare `/login` and `/logout` routes of their own, which look
  identical to the WDK paths in a grep and are not calls to WDK at all.
- **Discard non-service literals.** The `/service` to `/app` rewrite in
  `_http.py:_init_wdk_session` and the `removesuffix("/service")` in `site_router.py` both
  match a naive pattern and neither is an endpoint.
- **Join implicit string concatenation before matching.** Python adjacent-literal
  concatenation splits a path across lines, and a line-oriented grep sees only fragments.
  `records.py:95-96` is the live case: `f"/users/{...}/steps/{step_id}"` on one line and
  `f"/columns/{column_name}/reports/byValue"` on the next are one path. Matched
  separately, the first looks like a plain step fetch and the second does not start with
  any WDK prefix, so the column-reporter row appears uncalled. Join consecutive lines from
  the same file before deciding.
- **Grep the whole backend, not one package.** The first version of this column was
  derived from `src/veupathdb/wdk/strategy_api/` alone and got two rows wrong, both
  of them outside it: the callers live in `catalog_metadata.py` and
  `transport/http/routers/`. A narrowed extraction does not just miss rows, it makes the
  reverse check pass vacuously, so nothing reports the gap.

Two things deliberately absent from the table. The `/app` webapp URL that
`_init_wdk_session` fetches is a page, not a service endpoint. Site search
(`POST /site-search` at the site origin) is a separate VEuPathDB microservice, not WDK,
and the WDK service base returns 404 for it; its two forms are in
[the site-search contract](site-search-contract.md).

| Method | Path | Purpose | Request | Response | PathFinder client |
|---|---|---|---|---|---|
| GET | `/users/current` | Resolve the requesting identity | - | `User` with `id`, `isGuest` | `strategy_api/helpers.py:resolve_wdk_user_id` and `services/wdk_identity.py:fetch_wdk_user` |
| POST | `/login` | Exchange email and password for an `Authorization` token | `{email, password, redirectUrl}` | `{success, message, redirectUrl}` plus `Set-Cookie: Authorization` | `auth_login.py:password_login` |
| GET | `/logout` | Invalidate and issue a fresh guest token | - | redirect plus new guest cookie | `transport/http/routers/veupathdb_auth.py:logout` |
| POST | `/users` | Register a new user | registration form | `{id}` | unused, and must stay so |
| GET, PUT, DELETE | `/users/{userId}` | Read, replace or delete a profile | profile JSON | profile JSON | unused |
| GET, PATCH | `/users/{userId}/preferences` | Read and patch global or project preferences | preference deltas | preferences | unused |
| GET | `/users/{userId}/strategies` | List the user's strategies | - | `StrategySummary[]` | `strategy_api/strategies.py:list_strategies` |
| POST | `/users/{userId}/strategies` | Create a strategy | `NewStrategySpec` | `{id}` | `strategy_api/strategies.py:create_strategy` |
| PATCH | `/users/{userId}/strategies` | Batch delete by id | `DeleteStrategySpec[]` | - | unused; PathFinder deletes one at a time |
| GET | `/users/{userId}/strategies/{strategyId}` | Full strategy | - | `StrategyDetails` with `stepTree` and `steps` | `strategy_api/strategies.py:get_strategy` |
| PATCH | `/users/{userId}/strategies/{strategyId}` | Rename, save, or overwrite | `StrategyProperties` subset | `{id}` | `strategy_api/strategies.py:update_strategy`, `set_saved` |
| DELETE | `/users/{userId}/strategies/{strategyId}` | Delete a strategy | - | - | `strategy_api/strategies.py:delete_strategy` |
| PUT | `/users/{userId}/strategies/{strategyId}/step-tree` | Replace the whole tree at once | `{stepTree}` | - | `strategy_api/strategies.py:update_strategy` |
| POST | `/users/{userId}/strategies/{strategyId}/duplicated-step-tree` | Copy a branch, returning a new tree of new step ids | `{}` | `{stepTree}` | `strategy_api/strategies.py:get_duplicated_step_tree` |
| GET | `/strategy-lists/public` | Public strategies across the site | - | `StrategySummary[]` | `strategy_api/strategies.py:list_public_strategies` |
| POST | `/users/{userId}/steps` | Create a step: leaf, combined, or transform | `NewStepSpec` with `searchName` and `searchConfig` | `{id}` | `strategy_api/steps.py:create_step`, `create_combined_step`, `create_transform_step` |
| GET | `/users/{userId}/steps/{stepId}` | One step, validated at the requested level | `?validationLevel=` | `Step` with `estimatedSize`, `validation` | `strategy_api/steps.py:find_step`, and `_analyses.py:get_step_view_filters` and `:update_step_view_filters`, which read the step to recover its current `searchConfig` |
| PATCH | `/users/{userId}/steps/{stepId}` | Metadata only: custom name, expansion | `PatchStepSpec` | - | `strategy_api/steps.py:update_step_properties` |
| DELETE | `/users/{userId}/steps/{stepId}` | Delete a step | - | - | `strategy_api/steps.py:delete_step` |
| PUT | `/users/{userId}/steps/{stepId}/search-config` | Replace parameters and filters | `SearchConfig` | - | `strategy_api/steps.py:update_step_search_config`, and `_analyses.py:update_step_view_filters`, which round-trips the whole config to change only the view filters |
| POST | `/users/{userId}/steps/{stepId}/reports/standard` | Run the step and page its records | `{reportConfig, viewFilters}` | `Answer` with `records` and `meta` | `strategy_api/base.py:_standard_report`, used by `reports.py:get_step_records` and `get_step_count` |
| POST | `/users/{userId}/steps/{stepId}/reports/{reportName}` | Run a named reporter, media type varies | `{reportConfig}` | reporter-defined | `_analyses.py:run_step_report`, reached through `strategy_api/reports.py:run_step_report` |
| GET | `/users/{userId}/steps/{stepId}/reports/{reportName}` | The same, driven from a query string | `?reportConfig=` | reporter-defined | unused |
| POST | `/users/{userId}/steps/{stepId}/columns/{column}/reports/{tool}` | Per-column reporter, for example `byValue` | `{reportConfig}` | `{histogram, statistics}` | `strategy_api/records.py:get_column_distribution` |
| GET | `/users/{userId}/steps/{stepId}/filter-summary/{filterName}` | Legacy filter summary | - | filter-defined | unused; `@Deprecated` upstream, superseded by the column reporter above |
| GET | `/users/{userId}/steps/{stepId}/analysis-types` | Analyses available for this step | - | analysis type list | `_analyses.py:list_analysis_types` |
| GET | `/users/{userId}/steps/{stepId}/analysis-types/{name}` | One analysis type and its parameters | - | `{searchData, validation}` | `_analyses.py:get_analysis_type` |
| POST | `/users/{userId}/steps/{stepId}/analysis-types/{name}` | Revise analysis parameters, or refresh dependents | analysis form JSON | parameter state | unused |
| GET | `/users/{userId}/steps/{stepId}/analyses` | Analysis instances on this step | - | instance list | `_analyses.py:list_step_analyses` |
| POST | `/users/{userId}/steps/{stepId}/analyses` | Create an analysis instance | `{displayName, analysisName, parameters}` | instance | `_analyses.py:create_step_analysis` |
| GET, PATCH, DELETE | `/users/{userId}/steps/{stepId}/analyses/{analysisId}` | Read, rename, remove an instance | - | instance | unused |
| POST | `/users/{userId}/steps/{stepId}/analyses/{analysisId}/result` | Start the analysis run | `{}` | - | `_analyses.py:run_analysis_instance` |
| GET | `/users/{userId}/steps/{stepId}/analyses/{analysisId}/result` | Fetch the finished result | - | analysis-defined, GO and pathway enrichment under `resultData` | `_analyses.py:get_analysis_result` |
| GET | `/users/{userId}/steps/{stepId}/analyses/{analysisId}/result/status` | Poll run status | - | `{status}` | `_analyses.py:get_analysis_status` |
| GET, PUT | `/users/{userId}/steps/{stepId}/analyses/{analysisId}/properties` | Free-form per-instance properties | opaque | opaque | unused |
| POST | `/users/{userId}/datasets` | Upload an id list as a dataset, for `ds_gene_ids` style params | `{sourceType, sourceContent}` | `{id}` | `strategy_api/datasets.py:create_dataset` |
| GET | `/users/{userId}/datasets/{id}` | Read a dataset back | - | dataset | unused |
| GET | `/users/{userId}/baskets` | Basket counts per record type | - | baskets | unused |
| PATCH | `/users/{userId}/baskets/{basketName}` | Add or remove records from one basket | membership actions | - | unused |
| GET, PATCH, POST, DELETE | `/users/{userId}/favorites` | Favorites CRUD | favorites | favorites | unused |
| GET | `/record-types` | All record types, optionally expanded | `?format=expanded` | `RecordType[]` | `_searches.py:get_record_types` |
| GET | `/record-types/{recordType}` | One record type with attributes and tables | `?format=expanded` | `RecordType` | `strategy_api/records.py:get_record_type_info` |
| POST | `/record-types/{recordType}/records` | One record by primary key | `{primaryKey, attributes, tables}` | `RecordInstance` | `strategy_api/records.py:get_single_record` |
| GET | `/record-types/{recordType}/searches` | Searches available on this site | - | `Search[]` | `_searches.py:get_searches` |
| GET | `/record-types/{recordType}/searches/{searchName}` | Search detail and parameter specs | `?expandParams=true` | `{searchData, validation}` | `_searches.py:get_search_details` |
| POST | `/record-types/{recordType}/searches/{searchName}` | Search detail evaluated against supplied parameter values | `{searchConfig}` | `{searchData, validation}` | `_searches.py:get_search_details_with_params` |
| POST | `/record-types/{recordType}/searches/{searchName}/refreshed-dependent-params` | Recompute dependent parameter vocabularies after one value changes | `{changedParam, contextParamValues}` | refreshed parameters | `_searches.py:get_refreshed_dependent_params` |
| POST | `/record-types/{recordType}/searches/{searchName}/reports/standard` | Run a search without creating a step | `{searchConfig, reportConfig}` | `Answer` | `_searches.py:run_search_report`, and `catalog_metadata.py:load_dataset_metadata` against `dataset/searches/AllDatasets` |
| POST | `/record-types/{recordType}/searches/{searchName}/reports/{reportName}` | The same through a named reporter | `{searchConfig, reportConfig}` | reporter-defined, and bound to no `@InSchema` or `@OutSchema` | `_searches.py:get_ai_expression_report`, against `gene/searches/single_record_question_GeneRecordClasses_GeneRecordClass/reports/aiExpression` ([WDK-ANS-009](../rules/searches-and-answers.md)) |
| POST | `/record-types/{recordType}/searches/{searchName}/{paramName}/ontology-term-summary` | Filter-parameter ontology term summary | parameter context | term summary | unused |
| POST | `/record-types/{recordType}/searches/{searchName}/{paramName}/summary-counts` | Filter-parameter counts | parameter context | counts | unused |
| GET | `/record-types/{recordType}/searches/{searchName}/columns` | Columns available to column tools | - | column list | unused |
| POST | `/temporary-results` | Stash a report request behind an id, for a browser download link | report request | `{id}` | `temporary_results.py:create_temporary_result` |
| GET | `/temporary-results/{id}` | Redeem that id | - | the stashed report | `unused` by the backend. `temporary_results.py:get_download_url` builds this URL and hands it to the browser, which is the only thing that fetches it. |
| GET | `/ontologies` | List the ontologies a site publishes | - | ontology names | unused |
| GET | `/ontologies/{name}` | One ontology as a term tree | - | `{tree}` of ontology nodes | `catalog_metadata.py:load_ontology_categories`, against `Categories`, which is how PathFinder derives each search's category path |
| POST | `/client-errors` | Report a client-side error to WDK | error payload | - | unused |

# Which of these WDK validates against a published schema

WDK publishes 78 JSON Schema files under `Service/doc/schema`, and they describe far less
of the table above than their existence suggests. A body is schema-validated only where the
JAX-RS method carries `@InSchema` or `@OutSchema`; 25 of WDK's 120 methods do, naming 24
distinct schemas. The rest of the tree is documentation at best. Measured at
`f0a04136b658617a07c66151a49dd0787688084f`.

Of the 36 endpoints in the table that carry a body:

| | count |
|---|---|
| annotated, and a live payload validated against the schema | 9 |
| annotated, and a live 200 violated the schema | 2 |
| annotated, validation observed but no conforming payload built | 1 |
| annotated, but the schema is unsatisfiable or not valid JSON | 2 |
| annotation deliberately disabled upstream | 2 |
| a schema exists in the RAML only, never validated at runtime | 5 |
| no schema at all | 15 |

Each endpoint is counted by its worst measured direction: the two violators are the
standard reporter at search level and at step level, whose request schema does hold and
whose response schema does not. The one with validation observed but unmeasured is
`POST /users/{userId}/datasets`, where a deliberately wrong body came back as a 400
carrying `JsonSchemaProvider`'s own report, which is direct evidence the provider runs.

Twelve endpoints bind fourteen schema names between them, and the fixture store gates the
three that a user-independent request can reach: `wdk.records.get`, `wdk.records.name.get`
and `wdk.answer.post-request`. The other nine endpoints are user-scoped, and eight of those
create a step, a strategy or a dataset, so a manifest entry for one would create an account
resource on every replay. All fourteen schemas are vendored anyway, so binding a new one
costs a fixture and nothing else. `python -m veupathdb.devtools.fixtures verify`
validates every recorded body against them offline at the pinned sha
([WDK-HTTP-004](../rules/auth-and-transport.md)).

The six endpoints whose schema does not hold, or cannot, are each a different failure mode,
and none of them is an accident of one file:

- **`POST .../reports/standard`** binds `wdk.answer.post-response` and a live 200 fails it
  with 5 draft-04 errors: `records[*].attributes` and `records[*].tables` arrive as objects
  where the schema says arrays, and its `meta` subschema requires a key `meta` inside
  `meta`. Both the search-level and step-level reporter were measured.
- **`GET /users/{userId}/strategies/{strategyId}`** binds
  `wdk.users.strategies.id.get-response`, whose two `allOf` branches are each
  `additionalProperties: false` and so forbid each other's keys. No document satisfies it.
- **`PATCH /users/{userId}/strategies/{strategyId}`** binds
  `wdk.users.strategies.id.patch-request`, which has not been valid JSON since 2019-03-22:
  it uses a bare object as a mapping key.
- **`GET /record-types/{recordType}/searches/{searchName}`** - the endpoint that carries
  every parameter spec - has its annotation commented out with `TODO: FIX!`.
- **`GET /users/current`** has its annotation commented out too.

Two more numbers worth keeping. 22 of the 78 files are referenced by neither the RAML nor
another schema, and 4 are not valid JSON, which is why the vendored tree is read with a
trailing-comma-tolerant parser.

The RAML under `Service/doc/raml` is a third, weaker source: it documents 95 endpoints, 27
of which reference any schema, and its paths are stale where they disagree with the Java.
It documents `/users/{user-id}/strategy` and `/strategy-list/public`; `StrategyService`
declares `strategies` and `StrategyListsService` declares `/strategy-lists/public`. The
table above follows the Java, so it is right and the RAML is wrong.

# What the shape of this table says

The surface PathFinder uses is narrow and deep: steps, strategies, searches, reports.
Almost everything unused is either a browser concern (favorites, baskets, preferences,
client error reporting) or a capability nobody has needed yet (ontology term summaries,
dataset readback, analysis properties).

Two absences are deliberate rather than incidental. `POST /users` registers a real
account, and PathFinder must never call it. `PATCH /users/{userId}/strategies` deletes in
batches, and PathFinder deletes singly so that a partial failure names the strategy it
failed on.

Two rows are the ones that carry the science. `POST .../steps/{stepId}/reports/standard`
is where a strategy becomes a gene list, and `POST .../searches/{searchName}/reports/standard`
is the same without persisting anything. Both can answer 2xx without answering the
question: see [WDK-HTTP-003](../rules/auth-and-transport.md).
