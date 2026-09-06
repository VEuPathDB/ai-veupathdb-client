"""The machine-readable account of one nightly run."""

from __future__ import annotations

import datetime
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_SUMMARY_PATH = Path("wdk-live-summary.json")
SUMMARY_PATH_ENV = "WDK_LIVE_SUMMARY"


class Observation(BaseModel):
    """One reading from a running site.

    A reading with no ``expected`` is a measurement rather than a comparison,
    so it is recorded and never counted as drift.
    """

    model_config = ConfigDict(frozen=True)

    site: str
    check: str
    subject: str
    expected: str | None
    observed: str
    drifted: bool


class SiteTally(BaseModel):
    """What one site's observations came to."""

    observations: int = 0
    drifted: int = 0


class Outcomes(BaseModel):
    """How the checks in this package ended.

    Per-item hooks reach only the items under their own conftest, so the live
    suites elsewhere in the tree are counted by the run's exit code instead.
    """

    passed: int = 0
    failed: int = 0
    skipped: int = 0


class LiveLaneSummary(BaseModel):
    """The artifact the nightly job uploads."""

    started_at: str
    finished_at: str = ""
    outcomes: Outcomes = Field(default_factory=Outcomes)
    sites: dict[str, SiteTally] = Field(default_factory=dict)
    drift: list[Observation] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)


def summary_path() -> Path:
    """Where the artifact is written. The environment may name another place."""
    named = os.environ.get(SUMMARY_PATH_ENV)
    return Path(named) if named else DEFAULT_SUMMARY_PATH


class DriftLog:
    """Collects what the lane measured, so the run can be read after it ends."""

    def __init__(self) -> None:
        self._observations: list[Observation] = []
        self._started = datetime.datetime.now(tz=datetime.UTC).isoformat()
        self.outcomes = Outcomes()

    def record(
        self,
        *,
        site: str,
        check: str,
        subject: str,
        observed: object,
        expected: object | None = None,
    ) -> Observation:
        """Record one reading, and compare it when the caller pinned a value."""
        pinned = None if expected is None else str(expected)
        observation = Observation(
            site=site,
            check=check,
            subject=subject,
            expected=pinned,
            observed=str(observed),
            drifted=pinned is not None and pinned != str(observed),
        )
        self._observations.append(observation)
        return observation

    def summarize(self) -> LiveLaneSummary:
        sites: dict[str, SiteTally] = {}
        for observation in self._observations:
            tally = sites.setdefault(observation.site, SiteTally())
            sites[observation.site] = SiteTally(
                observations=tally.observations + 1,
                drifted=tally.drifted + int(observation.drifted),
            )
        return LiveLaneSummary(
            started_at=self._started,
            finished_at=datetime.datetime.now(tz=datetime.UTC).isoformat(),
            outcomes=self.outcomes,
            sites=sites,
            drift=[o for o in self._observations if o.drifted],
            observations=list(self._observations),
        )

    def write(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.summarize().model_dump_json(indent=2) + "\n")
        return path
