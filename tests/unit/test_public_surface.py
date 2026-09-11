"""Every surface is the checked-in one, every name on it resolves, and a consumer
reads only names it publishes."""

from __future__ import annotations

import ast
import importlib
import inspect
import json
from pathlib import Path
from types import ModuleType

import pytest

PACKAGES = (
    "veupathdb",
    "veupathdb.devtools",
    "veupathdb.domain",
    "veupathdb.domain.parameters",
    "veupathdb.domain.strategy",
    "veupathdb.eda",
    "veupathdb.testing",
    "veupathdb.wdk",
)

# The modules a consumer reads by name. Each one stays off a package surface:
# two fixture stores declare the same names, the OTEL adapter imports a
# distribution only its extra installs, and the devtools import theirs.
MODULES = (
    "veupathdb.auth_context",
    "veupathdb.devtools.eda_schemas",
    "veupathdb.devtools.fixtures",
    "veupathdb.errors",
    "veupathdb.model",
    "veupathdb.observability.otel",
    "veupathdb.testing.eda_fixtures",
    "veupathdb.testing.wdk_fixtures",
)

SURFACES = PACKAGES + MODULES

PUBLISHED = Path(__file__).parent / "published_surface.json"
CONSUMER_IMPORTS = Path(__file__).parent / "consumer_imports.json"


def _module(name: str) -> ModuleType:
    return importlib.import_module(name)


def _declared_names(source: Path) -> set[str]:
    """The names one module states itself, so an imported name does not count."""
    names: set[str] = set()
    for node in ast.parse(source.read_text()).body:
        match node:
            case ast.FunctionDef() | ast.AsyncFunctionDef() | ast.ClassDef():
                names.add(node.name)
            case ast.TypeAlias(name=ast.Name(id=alias)):
                names.add(alias)
            case ast.AnnAssign(target=ast.Name(id=target)):
                names.add(target)
            case ast.Assign(targets=targets):
                names.update(
                    target.id for target in targets if isinstance(target, ast.Name)
                )
            case _:
                pass
    return names


def _names_the_package_declares(name: str) -> set[str]:
    root = Path(str(_module(name).__file__)).parent
    return {
        declared
        for source in root.rglob("*.py")
        if source.name != "__init__.py"
        for declared in _declared_names(source)
    }


@pytest.mark.parametrize("name", PACKAGES)
def test_the_package_declares_a_surface(name: str) -> None:
    exported = _module(name).__all__

    assert len(exported) > 0
    assert sorted(set(exported)) == sorted(exported)


def test_every_surface_is_listed() -> None:
    published = json.loads(PUBLISHED.read_text())

    assert sorted(published) == sorted(SURFACES)


@pytest.mark.parametrize("name", SURFACES)
def test_the_surface_is_the_checked_in_one(name: str) -> None:
    """A name leaves a surface only by editing the list beside this test."""
    published = json.loads(PUBLISHED.read_text())

    assert sorted(_module(name).__all__) == published[name]


@pytest.mark.parametrize("name", SURFACES)
def test_every_exported_name_resolves(name: str) -> None:
    module = _module(name)
    bound = vars(module)
    missing = [entry for entry in module.__all__ if entry not in bound]

    assert missing == []


@pytest.mark.parametrize("name", SURFACES)
def test_no_exported_name_is_private(name: str) -> None:
    private = [entry for entry in _module(name).__all__ if entry.startswith("_")]

    assert private == []


@pytest.mark.parametrize("name", PACKAGES)
def test_every_exported_name_is_declared_in_this_package(name: str) -> None:
    """A surface republishes this package's own names, never another library's."""
    declared = _names_the_package_declares(name)
    outside = [entry for entry in _module(name).__all__ if entry not in declared]

    assert outside == []


@pytest.mark.parametrize("name", SURFACES)
def test_no_exported_name_is_a_submodule(name: str) -> None:
    """A consumer reads a name from a package, never a file path inside it."""
    module = _module(name)
    modules = [
        entry for entry in module.__all__ if inspect.ismodule(vars(module)[entry])
    ]

    assert modules == []


def _consumer_surfaces() -> list[tuple[str, str]]:
    reads = json.loads(CONSUMER_IMPORTS.read_text())
    return [
        (consumer, surface)
        for consumer, surfaces in sorted(reads.items())
        for surface in sorted(surfaces)
    ]


@pytest.mark.parametrize(("consumer", "surface"), _consumer_surfaces())
def test_every_name_a_consumer_reads_is_published_where_it_reads_it(
    consumer: str, surface: str
) -> None:
    """The measured import of each in-house consumer, surface by surface."""
    reads = json.loads(CONSUMER_IMPORTS.read_text())[consumer][surface]
    published = set(json.loads(PUBLISHED.read_text())[surface])

    assert sorted(set(reads) - published) == []
