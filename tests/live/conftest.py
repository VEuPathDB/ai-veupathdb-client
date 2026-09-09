"""What the live lane shares: a probe, a drift log, and cleaned-up resources.

Anything a check creates on the account is deleted when the check ends. The
account is a researcher's own.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncGenerator, Awaitable, Callable, Generator

import pytest
from _pytest.reports import TestReport

from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.testing.summary import DriftLog, summary_path
from veupathdb.testing.wdk_credentials import (
    NO_CREDENTIALS_REASON,
    registered_wdk_token,
)
from veupathdb.wdk.factory import get_strategy_api, get_wdk_client
from veupathdb.wdk.probe import WDKProbe
from veupathdb.wdk.wdk_models import (
    NewStepSpec,
    WDKSearchConfig,
    WDKStepTree,
)

VERIFICATION_SITES = ("plasmodb", "toxodb")

Probe = Callable[..., Awaitable[WDKProbe]]


# The report hook takes no fixtures, so the running log is published here.
_RUNNING_LOG: dict[str, DriftLog] = {}


@pytest.fixture(scope="session")
def drift_log() -> Generator[DriftLog]:
    """Collects the lane's measurements and writes the run's artifact."""
    log = DriftLog()
    _RUNNING_LOG["log"] = log
    yield log
    log.write(summary_path())
    _RUNNING_LOG.pop("log", None)


@pytest.fixture(scope="session", autouse=True)
def _open_the_log(drift_log: DriftLog) -> None:
    """Opens the log for every run, so an all-skip run still writes an artifact."""
    del drift_log


def pytest_runtest_logreport(report: TestReport) -> None:
    """Count how the lane's tests ended, for the artifact.

    Every ``live_wdk`` test counts, including the suites outside this package.
    """
    log = _RUNNING_LOG.get("log")
    if log is None or "live_wdk" not in report.keywords:
        return
    if report.when != "call" and not (report.when == "setup" and report.skipped):
        return
    if report.skipped:
        log.outcomes = log.outcomes.model_copy(
            update={"skipped": log.outcomes.skipped + 1}
        )
    elif report.passed:
        log.outcomes = log.outcomes.model_copy(
            update={"passed": log.outcomes.passed + 1}
        )
    else:
        log.outcomes = log.outcomes.model_copy(
            update={"failed": log.outcomes.failed + 1}
        )


@pytest.fixture
async def require_wdk_creds() -> str:
    """The registered WDK token, or a skip naming the credentials to set."""
    token = await registered_wdk_token()
    if token is None:
        pytest.skip(NO_CREDENTIALS_REASON)
    return token


@pytest.fixture
def wdk_identity(require_wdk_creds: str) -> Generator[str]:
    """Act on WDK as the registered account for the length of one check."""
    reset = veupathdb_auth_token_ctx.set(require_wdk_creds)
    yield require_wdk_creds
    veupathdb_auth_token_ctx.reset(reset)


@pytest.fixture
def probe(wdk_identity: str) -> Probe:
    """Ask a site a question and report what it answered, failures included."""
    del wdk_identity

    async def ask(
        site: str,
        method: str,
        path: str,
        params: dict[str, str] | None = None,
        json: object = None,
    ) -> WDKProbe:
        return await get_wdk_client(site).probe(method, path, params=params, json=json)

    return ask


@pytest.fixture
async def owned_strategy(
    wdk_identity: str,
) -> AsyncGenerator[Callable[[str], Awaitable[tuple[int, int]]]]:
    """Create a strategy on the account, and delete everything it made.

    Returns a factory answering ``(strategy_id, leaf_step_id)``.
    """
    del wdk_identity
    strategies: list[tuple[str, int]] = []
    steps: list[tuple[str, int]] = []

    async def create(site: str) -> tuple[int, int]:
        api = get_strategy_api(site)
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
        steps.append((site, step.id))
        strategy = await api.create_strategy(
            WDKStepTree(stepId=step.id), name="veupathdb-py-live-lane", is_internal=True
        )
        strategies.append((site, strategy.id))
        return strategy.id, step.id

    try:
        yield create
    finally:
        # A step inside a strategy cannot be deleted, so the strategy goes first.
        for site, strategy_id in reversed(strategies):
            with contextlib.suppress(Exception):
                await get_strategy_api(site).delete_strategy(strategy_id)
        for site, step_id in reversed(steps):
            with contextlib.suppress(Exception):
                await get_strategy_api(site).delete_step(step_id)
