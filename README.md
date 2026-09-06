# veupathdb-py

A typed Python client for the VEuPathDB WDK and EDA services.

Wire models mirror the WDK REST API field for field (`searchName`, not
`search_name`); the 11 parameter type discriminants are a tagged union; step
trees keep primary and secondary inputs.

**VEuPathDB refuses guest and anonymous service calls.** Every user-scoped call
needs a registered VEuPathDB token, supplied through
`veupathdb.auth_context.veupathdb_auth_token_ctx` or through
`VEUPATHDB_AUTH_TOKEN` for the user-independent reads (record types, searches,
parameter metadata).

## Install

```
uv add veupathdb-py
```

## Quickstart

```python
import asyncio

from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.errors import VEuPathDBError, VEuPathDBErrorCode
from veupathdb.wdk.factory import get_strategy_api, get_wdk_client, list_sites
from veupathdb.wdk.wdk_models import NewStepSpec, WDKSearchConfig, WDKStepTree


def site_ids() -> list[str]:
    """Every site the bundled sites.yaml declares."""
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

## Where `sites.yaml` comes from

The package bundles `veupathdb/sites.yaml`: 12 sites, their base URLs and
project ids, plus `routing.portal_timeout` and `routing.component_timeout`.
`veupathdb.wdk.site_router.load_sites_config` reads it through
`importlib.resources`. To serve a different list, point
`VEUPATHDB_SITES_CONFIG` at your own YAML of the same shape
(`src/veupathdb/sites-plasmodb.yaml` is a one-site example), or install a
settings source with `veupathdb.settings.use_veupathdb_settings_source`.

EDA base URLs are derived, not configured: they are `<site origin>/eda`.

## The `VEuPathDBError` taxonomy

`VEuPathDBError` carries everything a problem+json response needs: a
`VEuPathDBErrorCode`, a title, an HTTP status, a detail and a list of field
errors. The eight codes are `DATA_PARSING_ERROR`, `EXTERNAL_SERVICE_ERROR`,
`INTERNAL_ERROR`, `SEARCH_NOT_FOUND`, `SITE_NOT_FOUND`, `VALIDATION_ERROR`,
`WDK_ERROR` and `WDK_LOGIN_REQUIRED`. A host maps the code to its own response
shape; the client never builds one.

## Metrics

`veupathdb.observer.set_observer` installs an `Observer`. The client calls it
for every WDK request, so a host adds latency and error metrics without the
client depending on a metrics library. The default is `NoObserver`.

## Logging

`veupathdb.logging.get_logger` returns a bound `structlog` logger and nothing
else. The library never calls `structlog.configure`: log configuration belongs
to the host, and `tests/unit/test_package_boundary.py` reads that as a fact.

## The verification lanes

```
uv run pytest tests/unit          # hermetic: respx doubles, recorded WDK and EDA bodies
WDK_TEST_EMAIL=... WDK_TEST_PASSWORD=... \
  uv run pytest tests/live -m live_wdk --override-ini addopts=''   # nightly
```

The hermetic lane opens no socket and needs no credential. The live lane skips
without `WDK_TEST_TOKEN`, or `WDK_TEST_EMAIL` and `WDK_TEST_PASSWORD`.

The recorded WDK and EDA bodies, their schema pins and the vendored schema
trees live inside the package, under
`src/veupathdb/testing/fixtures/{wdk,eda}/`, so the wheel carries them and an
installed copy reads them.
`veupathdb.testing.wdk_fixtures.FIXTURE_DIR` and
`veupathdb.testing.eda_fixtures.FIXTURE_DIR` resolve that directory through
`importlib.resources`, and every reader goes through them rather than spelling a
path of its own.

Recorded bodies and vendored schemas are refreshed, never hand-edited:

```
uv run python -m veupathdb.devtools.fixtures record     # needs VEUPATHDB_AUTH_TOKEN
uv run python -m veupathdb.devtools.fixtures vendor
uv run python -m veupathdb.devtools.fixtures verify
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
