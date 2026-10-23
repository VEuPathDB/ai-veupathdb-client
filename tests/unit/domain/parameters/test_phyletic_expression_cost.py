"""A long expression is read in time linear in its units."""

from __future__ import annotations

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
RUNS = 3


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


def _read_seconds(text: str, tree: PhyleticTree) -> float:
    fastest = float("inf")
    for _ in range(RUNS):
        started = time.perf_counter()
        expression = PhyleticExpression.parse(text)
        check_expression(expression, tree)
        expression.describe(tree)
        fastest = min(fastest, time.perf_counter() - started)
    return fastest


@pytest.mark.parametrize("build", [_ladder, _every_code], ids=["ladder", "every-code"])
def test_twice_the_units_take_under_three_times_as_long(
    build: Callable[[PhyleticTree, int], str],
) -> None:
    """Linear reading doubles its time with its units; a quadratic one quadruples it."""
    tree = _recorded_tree()
    single = build(tree, UNITS)
    double = build(tree, 2 * UNITS)

    expression = PhyleticExpression.parse(double)
    ratio = _read_seconds(double, tree) / _read_seconds(single, tree)

    assert len(expression.units()) == 2 * UNITS
    assert expression.describe(tree).count(" or ") == UNITS - 1
    assert ratio < GROWTH
