# veupathdb-py

A typed Python client for the VEuPathDB WDK and EDA services.

Wire models mirror the WDK REST API field for field (`searchName`, not
`search_name`); the 11 parameter type discriminants are a tagged union; step
trees keep primary and secondary inputs.

**VEuPathDB refuses guest and anonymous service calls.** Every user-scoped call
needs a registered VEuPathDB token. A user-independent read resolves it through
`veupathdb.auth_context.resolve_veupathdb_auth_token`: the contextvar
`veupathdb_auth_token_ctx` first, then the client's own `auth_token=`, then
`VEUPATHDB_AUTH_TOKEN`. The deployment's token never reaches a researcher's own
data. A WDK path under `/users/` is refused unless the contextvar carries the
token; every VDI call and every EDA path under `/users/` is refused unless the
contextvar or the client's own `auth_token=` carries it. So the deployment's
service account reads record types, searches, parameter metadata and EDA
studies, and never a WDK account, a user dataset or an EDA analysis.

## The published surface

Each published package declares what a consumer may read, and
`tests/unit/published_surface.json` holds every list:

`veupathdb`, `veupathdb.auth_context`, `veupathdb.devtools`,
`veupathdb.devtools.eda_schemas`, `veupathdb.devtools.fixtures`,
`veupathdb.domain`, `veupathdb.domain.parameters`, `veupathdb.domain.strategy`,
`veupathdb.eda`, `veupathdb.errors`, `veupathdb.model`,
`veupathdb.observability.otel`, `veupathdb.testing`,
`veupathdb.testing.eda_fixtures`, `veupathdb.testing.wdk_fixtures`,
`veupathdb.wdk`.

A name reached through anything else is this package's own business and may
change in any release. `tests/unit/test_public_surface.py` fails when a
published name stops resolving, so a rename that breaks a consumer fails here
before it is released.

## Install

```
uv add veupathdb-py
```

## Quickstart

```python
import asyncio

from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.errors import VEuPathDBError, VEuPathDBErrorCode
from veupathdb.wdk import (
    NewStepSpec,
    WDKSearchConfig,
    WDKStepTree,
    get_strategy_api,
    get_wdk_client,
    list_sites,
)


def site_ids() -> list[str]:
    """Every site the site list in force declares."""
    return [site.id for site in list_sites()]


async def kinase_step(token: str) -> int:
    """Run one search on PlasmoDB and read the step it produced."""
    veupathdb_auth_token_ctx.set(token)
    searches = await get_wdk_client("plasmodb").get_searches("transcript")
    assert any(search.url_segment == "GenesByMolecularWeight" for search in searches)

    api = get_strategy_api("plasmodb")
    step = await api.create_step(
        NewStepSpec(
            searchName="GenesByMolecularWeight",
            searchConfig=WDKSearchConfig(
                parameters={
                    "organism": '["Plasmodium falciparum 3D7"]',
                    "min_molecular_weight": "10000",
                    "max_molecular_weight": "20000",
                }
            ),
        ),
        record_type="transcript",
    )
    strategy = await api.create_strategy(WDKStepTree(stepId=step.id), name="demo")
    try:
        return (await api.find_step(step.id)).estimated_size or 0
    except VEuPathDBError as refusal:
        assert refusal.code is not VEuPathDBErrorCode.WDK_LOGIN_REQUIRED
        raise
    finally:
        await api.delete_strategy(strategy.id)


if __name__ == "__main__":
    print(site_ids())
    asyncio.run(kinase_step("<a registered VEuPathDB token>"))
```

## A deployment names its site list

The package ships no default site list. A deployment points
`VEUPATHDB_SITES_CONFIG` at a YAML file that names its sites, their base URLs
and project ids, plus `routing.portal_timeout` and `routing.component_timeout`,
or installs a settings source that names one with
`veupathdb.use_veupathdb_settings_source`. A process with neither fails at its
first site read with `veupathdb.wdk.SitesConfigNotSetError`, which names the
setting.

`docs/sites/production.yaml` lists the production sites, for a deployment that
serves production to copy. It is not in the wheel. The wheel carries one list,
the QA sites (`qa.<site>.org/<project>.qa/service`), at
`veupathdb.testing.QA_SITES_FILE`: the list every test and every recorder in
this repository reads.

A settings source may be installed at any point in the process. Installing one
drops the site router, the cached sites config and every cached per-site
client, so the next call builds them from the source in force.
`veupathdb.wdk.reset_site_router` does the same on its own. Neither closes a
client already handed out: call `close_all_clients` and `close_all_eda_clients`
first to release their sockets.

EDA base URLs are derived, not configured: they are `<site origin>/eda`.

## The `VEuPathDBError` taxonomy

`VEuPathDBError` carries everything a problem+json response needs: a code, a
title, an HTTP status, a detail and a list of field errors. The client's own
refusals are `VEuPathDBError[VEuPathDBErrorCode]`, and the eight codes are
`DATA_PARSING_ERROR`, `EXTERNAL_SERVICE_ERROR`, `INTERNAL_ERROR`,
`SEARCH_NOT_FOUND`, `SITE_NOT_FOUND`, `VALIDATION_ERROR`, `WDK_ERROR` and
`WDK_LOGIN_REQUIRED`. The client never builds a response.

The base is generic in its code enum, so a host that has its own `StrEnum` of
codes puts its whole error hierarchy under the same base and keeps `code`
typed as its own enum. `code` is read-only:

```
from enum import StrEnum

from veupathdb.errors import VEuPathDBError


class AppErrorCode(StrEnum):
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"


class AppError(VEuPathDBError[AppErrorCode]):
    """Every refusal this application raises."""


def status_of(refusal: VEuPathDBError[StrEnum]) -> int:
    """One handler for the host's refusals and the client's."""
    return refusal.status
```

## Helper strategies

WDK carries no metadata on a strategy, so a strategy this client creates for a
step count or a control test is tagged by a reserved prefix on its name:
`create_strategy(..., is_internal=True)` applies it, and
`is_internal_wdk_strategy_name` / `strip_internal_wdk_strategy_name` read it
back. The name reaches a real VEuPathDB account, so the prefix is the
deployment's own: `veupathdb_internal_strategy_name_prefix`, environment
variable `VEUPATHDB_INTERNAL_STRATEGY_NAME_PREFIX`, default `__internal__:`.

A deployment that has already written internal strategies MUST set this field to
the prefix it has always written, in the same change that takes this release.
Otherwise it writes and matches `__internal__:` from that moment, and every
helper strategy already in a researcher's VEuPathDB account under the old value
is permanently unmatched: no run recognises it, and no run removes it.

## Metrics

`veupathdb.set_observer` installs an `Observer`. The client calls it
for every WDK request, so a host adds latency and error metrics without the
client depending on a metrics library. The default is `NoObserver`.

An OpenTelemetry sink ships with the `otel` extra, which takes the API and never
the SDK:

```
uv add "veupathdb-py[otel]"
```

```
from veupathdb import set_observer
from veupathdb.observability.otel import OpenTelemetryObserver

set_observer(OpenTelemetryObserver())
```

It feeds `veupathdb.wdk.requests`, `veupathdb.wdk.request_retries`,
`veupathdb.wdk.request_duration`, `veupathdb.wdk.search_wait` and the three
`veupathdb.site_search.*` counterparts, and records nothing until the host
configures a `MeterProvider`.

## Search load

A request that makes WDK run a search waits in three lines, and none refuses it:
the line of its turn on its site, the host's gate, and one of the site's
`veupathdb_concurrent_searches_per_site` slots. A host wraps a researcher's turn
in `veupathdb.wdk.search_turn()`, so one turn sends one search to a site at a
time, and installs a gate with `use_search_gate`. The gate is called with a
`SearchRequest` (site, kind, the searches the request runs);
`runs_an_expensive_search` reads it against `HIGH_SPEED_SNP_SEARCHES`.
`budget_seconds` on `post` and `run_search_report` bounds a request from the
moment it is sent, so time in line never counts against it.

```
from contextlib import asynccontextmanager

from veupathdb.wdk import SearchRequest, use_search_gate


@asynccontextmanager
async def one_line(request: SearchRequest):
    yield


use_search_gate(one_line)
```

## Who the request is

`veupathdb.wdk.fetch_current_user(site_id)` reads
`GET /users/current` under the token in `veupathdb_auth_token_ctx` and answers a
typed `WDKUserInfo`, or `None` when there is no token and when WDK cannot answer.
`resolve_registered_email(token, site_id)` names the account behind a token and
answers `None` for a guest.

## Logging

`veupathdb.get_logger` returns a bound `structlog` logger and nothing
else. The library never calls `structlog.configure`: log configuration belongs
to the host, and `tests/unit/test_package_boundary.py` reads that as a fact.

## The verification lanes

```
uv run pytest tests/unit          # hermetic: respx doubles, recorded WDK and EDA bodies
WDK_TEST_EMAIL=... WDK_TEST_PASSWORD=... \
  uv run pytest tests/live -m live_wdk --override-ini addopts=''   # nightly
```

The hermetic lane opens no socket and needs no credential. The live lane skips
without `WDK_TEST_TOKEN`, or `WDK_TEST_EMAIL` and `WDK_TEST_PASSWORD`. Both
lanes read the QA site list, whatever the environment names: `tests/conftest.py`
puts `veupathdb.testing.QA_SITES_FILE` in force for every test. No test reaches
a production or beta site, and `node scripts/check-test-sites.mjs` fails on a
production or beta host anywhere in this repository outside `docs/`.

The recorded WDK and EDA bodies, their schema pins and the vendored schema
trees live inside the package, under
`src/veupathdb/testing/fixtures/{wdk,eda}/`, so the wheel carries them and an
installed copy reads them.
`veupathdb.testing.wdk_fixtures.FIXTURE_DIR` and
`veupathdb.testing.eda_fixtures.FIXTURE_DIR` resolve that directory through
`importlib.resources`, and every reader goes through them rather than spelling a
path of its own. `veupathdb.testing.eda_fixtures.recorded_distribution(name)` reads
one recorded `/distribution` body as an `EdaDistributionResponse`.

Recorded bodies and vendored schemas are refreshed, never hand-edited. Every
recorder (`fixtures record`, `eda_capture record`, `vdi_capture record`) puts
the QA site list in force before it sends a request, and `capture_wdk` keeps
only exchanges with a QA host, so no recorder reaches a production or beta site
and none takes a flag that would. The bodies recorded on production sites are
out of the package, under `fixtures-production-backup-2026-10-09/`, which no
test and no build reads. Until the QA sites are recorded, the store holds the
vendored schemas only: `verify` names each missing body, and every test that
reads one is skipped with `veupathdb.testing.NEEDS_QA_RECORDING` as its reason while
`veupathdb.testing.needs_qa_recording(...)` finds its recording absent. A recording
written to the store lifts the skip with no change to the test.

The two schema readers ride the `devtools` extra, so an installed copy runs the
six commands after `pip install "veupathdb-py[devtools]"`:

```
uv run python -m veupathdb.devtools.fixtures record     # needs VEUPATHDB_AUTH_TOKEN
uv run python -m veupathdb.devtools.fixtures vendor
uv run python -m veupathdb.devtools.fixtures verify
uv run python -m veupathdb.devtools.eda_capture record   # analyses need WDK_TEST_*
uv run python -m veupathdb.devtools.eda_schemas vendor
uv run python -m veupathdb.devtools.eda_schemas verify
```

That the wheel really holds them is a third lane:

```
uv run pytest tests/packaging -m wheel --override-ini addopts=''
```

## Coverage

The client's own suite covers what needs only the client. Tests that also need
a host application (a database, an agent, an HTTP API) live in that host's
repository and consume this package like any dependency, so this suite is
thinner than the code's real coverage.
