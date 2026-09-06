"""WDK asks for a re-run on six statuses, so all six are re-run.

`requiresRerun` is the flag the platform branches on. Two of the six describe a
timeout or a shutdown, which say nothing about the data and which a second
attempt can clear.
"""

from __future__ import annotations

import pytest

from veupathdb.errors import VEuPathDBError
from veupathdb.wdk.client import VEuPathDBClient
from veupathdb.wdk.strategy_api.api import StrategyAPI


class _Statuses:
    """Answers a scripted status sequence and counts the re-runs."""

    def __init__(self, sequence: list[str]) -> None:
        self._sequence = list(sequence)
        self.reruns = 0

    async def status(self, uid: str, step_id: int, analysis_id: int) -> str:
        del uid, step_id, analysis_id
        return self._sequence.pop(0) if self._sequence else "COMPLETE"

    async def rerun(self, uid: str, step_id: int, analysis_id: int) -> None:
        del uid, step_id, analysis_id
        self.reruns += 1


def _api(
    monkeypatch: pytest.MonkeyPatch, sequence: list[str]
) -> tuple[StrategyAPI, _Statuses]:
    api = StrategyAPI(VEuPathDBClient("https://example.invalid/service"), "1")
    script = _Statuses(sequence)
    monkeypatch.setattr(api.client, "get_analysis_status", script.status)
    monkeypatch.setattr(api.client, "run_analysis_instance", script.rerun)
    return api, script


async def _poll(api: StrategyAPI, *, max_retries: int = 3) -> None:
    await api._poll_analysis(
        "1", 9, 4, poll_interval=0.0, max_wait=30.0, max_retries=max_retries
    )


class TestEveryRerunStatusIsRerun:
    @pytest.mark.asyncio
    async def test_expired_is_rerun(self, monkeypatch: pytest.MonkeyPatch) -> None:
        api, script = _api(monkeypatch, ["EXPIRED", "COMPLETE"])

        await _poll(api)

        assert script.reruns == 1

    @pytest.mark.asyncio
    async def test_interrupted_is_rerun(self, monkeypatch: pytest.MonkeyPatch) -> None:
        api, script = _api(monkeypatch, ["INTERRUPTED", "COMPLETE"])

        await _poll(api)

        assert script.reruns == 1

    @pytest.mark.asyncio
    async def test_error_is_still_rerun(self, monkeypatch: pytest.MonkeyPatch) -> None:
        api, script = _api(monkeypatch, ["ERROR", "COMPLETE"])

        await _poll(api)

        assert script.reruns == 1

    @pytest.mark.asyncio
    async def test_a_completed_analysis_is_not_rerun(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api, script = _api(monkeypatch, ["COMPLETE"])

        await _poll(api)

        assert script.reruns == 0


class TestTheGiveUpMessageMatchesTheStatus:
    @pytest.mark.asyncio
    async def test_a_timeout_does_not_blame_the_gene_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api, _ = _api(monkeypatch, ["EXPIRED"] * 6)

        with pytest.raises(VEuPathDBError) as caught:
            await _poll(api, max_retries=2)

        assert "gene set" not in str(caught.value)

    @pytest.mark.asyncio
    async def test_a_timeout_names_the_status(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api, _ = _api(monkeypatch, ["EXPIRED"] * 6)

        with pytest.raises(VEuPathDBError) as caught:
            await _poll(api, max_retries=2)

        assert "EXPIRED" in str(caught.value)

    @pytest.mark.asyncio
    async def test_a_data_failure_still_explains_the_gene_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api, _ = _api(monkeypatch, ["ERROR"] * 6)

        with pytest.raises(VEuPathDBError) as caught:
            await _poll(api, max_retries=2)

        assert "gene set" in str(caught.value)

    @pytest.mark.asyncio
    async def test_it_gives_up_rather_than_running_forever(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api, script = _api(monkeypatch, ["INTERRUPTED"] * 20)

        with pytest.raises(VEuPathDBError):
            await _poll(api, max_retries=2)

        assert script.reruns <= 2
