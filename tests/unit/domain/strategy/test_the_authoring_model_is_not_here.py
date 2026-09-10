"""The strategy package states WDK shapes. The authoring model lives with its caller.

A step tree with primary and secondary inputs is WDK's shape; a spec built out of
criteria, a chat session and an edit algebra over one are not.
"""

from __future__ import annotations

import ast
from pathlib import Path

from veupathdb.domain.parameters.unbound import UnboundParameter

_SOURCE_ROOT = Path(__file__).resolve().parents[4] / "src" / "veupathdb"
_STRATEGY = _SOURCE_ROOT / "domain" / "strategy"
_WDK = _SOURCE_ROOT / "wdk"
_PACKAGE = "veupathdb.domain.strategy"


_DEPARTED = frozenset(
    {
        "build_outcome.py",
        "combination_check.py",
        "constraints.py",
        "operational_spec.py",
        "operations",
        "session.py",
        "spec_diff.py",
        "types.py",
    }
)


def _module_level_definitions(path: Path) -> set[str]:
    return {
        node.name
        for node in ast.parse(path.read_text()).body
        if isinstance(node, ast.ClassDef | ast.FunctionDef)
    }


def _imported_names(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
        elif isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
    return names


def test_the_package_holds_the_wdk_shapes_and_nothing_else() -> None:
    """Every module here states a shape WDK itself states."""
    found = {path.relative_to(_STRATEGY).as_posix() for path in _STRATEGY.rglob("*.py")}

    assert found == {
        "__init__.py",
        "ast.py",
        "graph_model.py",
        "ops.py",
        "organism.py",
        "strategy_ast.py",
        "tree.py",
        "validation.py",
    }


def test_every_module_that_authors_a_strategy_is_named_and_absent() -> None:
    """A goal split into criteria, the requirements read out of prose, a chat
    session, the edit algebra over one, and what a turn did to a spec."""
    present = sorted(name for name in _DEPARTED if (_STRATEGY / name).exists())

    assert present == []


def test_the_build_lifecycle_of_a_step_is_not_here() -> None:
    """DRAFT, READY, BUILT and INVALID say whether a step reached WDK yet.
    That is a build lifecycle over the keyed map, and WDK states no such enum."""
    defined = _module_level_definitions(_STRATEGY / "graph_model.py")

    assert "StrategyStep" in defined
    assert sorted(defined & {"StepStatus", "step_status"}) == []


def test_the_parameter_that_awaits_a_value_lives_with_the_parameters() -> None:
    """The parameter name, the question and the vocabulary are a parameter's.
    The criterion that holds them belongs to the caller that authors a spec."""
    assert (_SOURCE_ROOT / "domain" / "parameters" / "unbound.py").is_file()
    assert set(UnboundParameter.model_fields) == {"param_name", "question", "options"}


def test_the_wdk_layer_names_two_wdk_shapes_and_nothing_else() -> None:
    """The operators the boolean search accepts, and the bundle a refusal carries."""
    reached = {
        name
        for path in _WDK.rglob("*.py")
        for name in _imported_names(path)
        if name.startswith(f"{_PACKAGE}.")
    }

    assert reached == {f"{_PACKAGE}.ops", f"{_PACKAGE}.validation"}
