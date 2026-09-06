from __future__ import annotations

from veupathdb.domain.strategy.build_outcome import (
    BuildOutcome,
    NodeResult,
    node_status,
)


def test_node_status_classifier() -> None:
    assert node_status(count=437, failed=False) == "ok"
    assert node_status(count=0, failed=False) == "zero"
    assert node_status(count=None, failed=True) == "failed"
    assert node_status(count=None, failed=False) == "ok"


def test_node_result_serializes_camelcase() -> None:
    nr = NodeResult(
        node_id="s1",
        search_name="GenesWithSignalPeptide",
        wdk_step_id=123,
        count=437,
        status="ok",
    )
    dumped = nr.model_dump(by_alias=True)
    assert dumped["searchName"] == "GenesWithSignalPeptide"
    assert dumped["wdkStepId"] == 123
    assert dumped["status"] == "ok"


def test_build_outcome_carries_node_results() -> None:
    outcome = BuildOutcome(
        node_results=[NodeResult(node_id="s1", search_name="S", count=5, status="ok")]
    )
    assert outcome.node_results[0].count == 5
