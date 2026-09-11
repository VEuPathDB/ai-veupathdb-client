# Knowledge log

## 2026-09-11 - The signing-key reset is published

`forget_signing_keys` is on `veupathdb.wdk`. A consumer's test suite that fakes a WDK
login drops the OAuth signing-key cache through the surface, so no consumer reads the
module that holds it. `veupathdb-py` is 0.1.0a10.

## 2026-09-11 - One token resolution, a declared surface, and every rule proven here

WDK, EDA and VDI resolve the request's token through one function,
`veupathdb.auth_context.resolve_veupathdb_auth_token`: the contextvar, then the client's
own `auth_token`, then settings. `EdaClient` and `VdiClient` take an `auth_token`
keyword, so a deployment that exports one environment variable reads an EDA study as it
reads a WDK search list. One WDK rule still stands above the order: a path under
`/users/` is refused unless the contextvar carries the token.

Sixteen surfaces are published, each declaring `__all__`, all of them checked in at
`tests/unit/published_surface.json`. `tests/unit/consumer_imports.json` records the
names the two in-house consumers read under the surface each one reads them from, and
the gate fails when a name stops being published on that surface.
`veupathdb.wdk._failures` stays private and `veupathdb.wdk` publishes the three names
its readers need.

The two schema readers are a `devtools` extra. The wheel already shipped
`veupathdb.devtools`, and now an installed copy can import it.

Installing a settings source drops the router, the cached sites config and every
per-site client cache built from the previous one. `reset_site_router` publishes the
same reset, and this package's own conftest uses it instead of reaching into a private
signing-key cache.

The login refusal states the condition rather than a feature list, and names no entity
this package does not model. Three docstrings state what their symbol is rather than
which layer called it, and `tests/unit/test_package_boundary.py` fails on a caller's
vocabulary in a docstring.

Every rule status names a test this repository runs. The 36 that named another
repository are now 29 hermetic cases under `tests/unit/rules/`, two live cases, and
five `PARTIAL` - four hermetic and one live - where the named case holds the half that
can be held. The run reports
78 rules: 73 enforced, 5 partial, 0 unenforced.

The WDK and EDA trees state WDK and EDA, with the client as the actor. The application's
mapping, its authority ranking and its two verification sites left for
`pathfinder: docs/knowledge/wdk/pathfinder/`; `tests/unit/test_bundle_subject.py` fails on
the application's name anywhere under `wdk/` or `eda/`. One paragraph was deleted rather
than moved: it described `StepValidation` defaults the tree has not had since the field
became `StepValidation | None`.

- The two visible phyletic species lists are `PHYLETIC_LIST_PARAMS` on
  `veupathdb.domain.parameters`. The five names of a phyletic search are the two
  structural maps, these two lists and the derived pattern, and the suite asserts that
  partition. At its next tag `veupathdb-mcp` deletes its own `PHYLETIC_LIST_PARAMS` from
  `catalog/param_formatting.py`, drops it from its published surface and reads this one
  at its three call sites; `pathfinder` moves one import line.

- `build_wdk_step_tree` and `MissingWDKStepIdError` join `walk_wdk_step_tree` in
  `veupathdb.wdk.step_tree`, and `resolve_record_type` is `veupathdb.wdk.record_types`.
  Both are `veupathdb.wdk` and not `veupathdb.domain.strategy`, because each one names a
  WDK wire model and no module of the domain package names a module of `veupathdb.wdk`.
  `veupathdb.wdk` now names four modules of the strategy package, and all four state WDK
  shapes. At its next tag `veupathdb-mcp` deletes `wdk/step_tree.py` and
  `wdk/record_types.py`, imports the three names from here and drops them from its
  surface; `pathfinder` moves one import line in `services/strategies/sync.py`.

- Nine shapes a consumer constructs are published: `InputStepValue`, `PhyleticNode`,
  `WDKVocabNodeData` and `collect_leaf_terms` on `veupathdb.domain.parameters`, and
  `AiExpressionReport`, `SiteSearchResponse`, `SiteSearchStreamRecord`, `WDKFilterParam`
  and `WDKReporter` on `veupathdb.wdk`. Eight of them are the inner shape of a name that
  was already published, and none of them is a test double.
  `tests/unit/consumer_imports.json` measures the tool server's suite beside its `src`,
  so a rename of a shape that suite builds fails here. At its next tag `veupathdb-mcp`
  rewrites fifteen imports onto the package surface.

## 2026-09-10 - The authoring model leaves, and an unbound parameter is a parameter

`session`, `operations/`, `spec_diff`, `combination_check`, `build_outcome`,
`operational_spec`, `constraints`, `SyncStateProtocol` and `PersistedStrategyGraph`
left `domain/strategy/` for the consuming application. What is left states WDK's own
shapes: the step tree, the keyed step map, the traversal over both, the combine
operators, the validation bundle and the organism scope rule.

`StepStatus` and `step_status` left with them. Four states saying whether a step has
reached WDK yet are a build lifecycle over the keyed map, and WDK states no such
enum. `StrategyStep` and `is_computable` stay, so the lifecycle reads them across the
seam and `veupathdb-mcp`, which names neither status symbol, is untouched.

WDK-VALID-004 anchored that lifecycle. It now anchors `StepValidation.rejects` and
the tests beside it: the half of the rule a client owns is the claim it reads back,
and that claim is the validation bundle.

`OpenSlot` split on the line its readers already draw. The parameter name, the
question and the vocabulary are `UnboundParameter` in
`veupathdb.domain.parameters.unbound`, which is what the MCP server's parameter
binding builds and reads. The criterion a slot is attached to is the spec's, so it
left with the spec. There is no forwarding module at the old path: `veupathdb-mcp`
names the new one at its next release.

The `WireParams` alias moved into `veupathdb.wdk.value_decoding`, so `veupathdb.wdk`
names two modules of this package and both are WDK shapes.

WDK-STRAT-006 anchors the step node's `secondary_input` and the tree tests beside it.
The rule is about the shape a client can express, and the shape is what stayed.

The consuming application's card said the cut costs 47 edges out of `veupathdb.wdk`.
That count was measured before the split. Measured here the edge set was four lines
into three modules, all of them WDK shapes.

## 2026-09-09 - The refusal base takes the host's code enum, the strategy prefix leaves, and an absent experiment count reads None

`VEuPathDBError` is generic in its code enum, so a host application puts its own
error hierarchy under this base instead of maintaining a parallel one. The client's
own refusals name `VEuPathDBErrorCode`; a handler that takes any refusal names the
bound.

The reserved prefix that marks a helper strategy is now a settings field with a
neutral default. It named one product and was written into the user's real VEuPathDB
account. A deployment that already wrote helper strategies states its historical
prefix in the same change that takes this release, or those strategies stay in the
account unmatched.

`env_ignore_empty=True` is stated in the settings docstring and asserted in the
suite, because a blank environment variable resolving to the field default is the
behaviour that keeps a validator unnecessary.

An `aiExpression` entry that answers `present` carries the summary and
`basedOnIncompleteData` and no experiment counts; the site writes `numExperiments`,
`numExperimentsComplete` and the `experimentStatus` map only on the branches that answer
no summary. The two counts are `int | None` now, so a reader tells an absent count from a
count of zero. A consumer that compares them handles `None` as "the site stated nothing".
`basedOnIncompleteData` is modelled beside them as `bool | None`, so a consumer can caveat
a summary the site generated over part of the experiment set. WDK-ANS-009 states the
measured `present` shape. The recorded aiExpression bodies now hold a `present` entry and
an `experiments_incomplete` one, and their fixture names say which is which.

Each experiment line of that summary also names its experiment and its assay, so
`AiExperimentSummary` reads `experiment_name` and `assay_type` beside the six keys it
already read. Those keys are snake_case on the wire, so the model states them as they
arrive. A tool that quotes a summary line can now say which experiment it came from
instead of quoting a dataset id.

## 2026-09-08 - The small client moves arrive, and the app prose leaves

`GET /users/current` and its typed profile, the two EDA validation predicates, the
OpenTelemetry observer adapter, the WDK capture transport and the orphaned-step delete
moved in from the consuming application. `veupathdb_oauth_url` moved in from the MCP
server's settings, because the function that reads it is this client's.

Four sections that spoke about the consuming application left: the three EDA
"what this means" sections and the step-analysis usage note. What names a module in
another repository is now written as a citation - `pathfinder:` or `veupathdb-mcp:` -
and every path that still spelled the pre-split `integrations/veupathdb/` tree names
this package instead. WDK-AUTH-004 is enforced here now that `password_logout` has a
test in this suite.

## 2026-09-08 - ruff format owns the bundle's Python blocks

`ruff format` formats Python code blocks inside markdown from ruff 0.16, so
`uv run ruff format --check .` now covers every file in this bundle as well as
`src` and `tests`. A Python block here is formatted code, not free text.

## 2026-09-05 - The bundle arrives with the client

The WDK model, REST and rule bundles and the whole EDA bundle moved here from
PathFinder's `docs/knowledge/`, with every anchor and every named test repointed at
this tree. A rule whose enforcement lives in the consuming application is `UNENFORCED`
here, with a `reason` naming the consumer's test: 37 of the 78 rules are in that state,
and the count is the honest measure of what this repository's own suite holds.

PathFinder keeps the eight `WDK-MAP` rules, because a mapping rule is an invariant of
the application rather than a fact about WDK.
