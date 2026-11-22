"""A long expression is read in time linear in its units."""

from __future__ import annotations

import gc
import time
from collections.abc import Callable

import pytest

from veupathdb.domain.parameters import (
    PhyleticExpression,
    PhyleticTree,
    check_expression,
)
from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk.phyletic_tree import ortho_taxonomy_of
from veupathdb.wdk.wdk_models import WDKAnswer

UNITS = 10_000
GROWTH = 3.0
RUNS = 5


def _recorded_tree() -> PhyleticTree:
    tree = ortho_taxonomy_of(
        WDKAnswer.model_validate(load_recorded("orthomcl_taxonomy").body)
    )
    assert tree is not None
    return tree


def _ladder(tree: PhyleticTree, units: int) -> str:
    del tree
    return " OR ".join(f"pfal={k} AND tgon>={k + 1}" for k in range(units // 2))


def _every_code(tree: PhyleticTree, units: int) -> str:
    codes = sorted(code for code in tree.codes() if tree.genomes_under([code]))
    return " OR ".join(
        f"{codes[i % len(codes)]}>={1 + i // len(codes)} AND "
        f"{codes[(i + 1) % len(codes)]}=0T"
        for i in range(units // 2)
    )


type Stage = Callable[[str, PhyleticExpression, PhyleticTree], object]


def _parse(text: str, _parsed: PhyleticExpression, _tree: PhyleticTree) -> object:
    return PhyleticExpression.parse(text)


def _check(_text: str, parsed: PhyleticExpression, tree: PhyleticTree) -> object:
    check_expression(parsed, tree)
    return None


def _describe(_text: str, parsed: PhyleticExpression, tree: PhyleticTree) -> str:
    return parsed.describe(tree)


def _growth(stage: Stage, build: Callable[[PhyleticTree, int], str]) -> float:
    tree = _recorded_tree()
    texts = (build(tree, UNITS), build(tree, 2 * UNITS))
    parsed = tuple(PhyleticExpression.parse(text) for text in texts)
    fastest = [float("inf"), float("inf")]
    gc.collect()
    gc.disable()
    try:
        for _ in range(RUNS):
            for size in (0, 1):
                started = time.process_time()
                stage(texts[size], parsed[size], tree)
                fastest[size] = min(fastest[size], time.process_time() - started)
    finally:
        gc.enable()
    return fastest[1] / fastest[0]


BUILDS = pytest.mark.parametrize(
    "build", [_ladder, _every_code], ids=["ladder", "every-code"]
)


@BUILDS
def test_the_doubled_expression_reads_every_unit(
    build: Callable[[PhyleticTree, int], str],
) -> None:
    tree = _recorded_tree()
    expression = PhyleticExpression.parse(build(tree, 2 * UNITS))

    assert len(expression.units()) == 2 * UNITS
    assert expression.describe(tree).count(" or ") == UNITS - 1


@BUILDS
@pytest.mark.parametrize(
    "stage", [_parse, _check, _describe], ids=["parse", "check", "describe"]
)
def test_twice_the_units_take_each_stage_under_three_times_as_long(
    stage: Stage, build: Callable[[PhyleticTree, int], str]
) -> None:
    assert _growth(stage, build) < GROWTH
