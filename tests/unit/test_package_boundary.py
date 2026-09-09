"""The boundary is an installation fact; this suite is the belt.

The package declares no dependency on ``pathfinder``, ``assistant-core`` or a
database driver, so those imports cannot resolve in this environment. The walk
below fails on the import statement instead, and names the module that added it.
"""

from __future__ import annotations

import ast
import importlib
import pkgutil
import sys
from pathlib import Path
from types import ModuleType

import pytest

import veupathdb

CLIENT = veupathdb.__name__

FORBIDDEN_ROOTS = {
    "pathfinder",
    "assistant_core",
    "veupathdb_mcp",
    "sqlalchemy",
    "asyncpg",
    "pgvector",
    "pydantic_ai",
    "langgraph",
    "fastapi",
    "fastmcp",
    "prometheus_client",
    "opentelemetry",
}

# The wire models are declarations, so they reach the model library and nothing else.
WIRE_MODEL_MODULES = {f"{CLIENT}.wdk.wdk_models", f"{CLIENT}.eda.models"}
ALLOWED_WIRE_MODEL_IMPORTS = {"pydantic"}

# One module per optional extra may name the distribution that extra installs.
OPTIONAL_EXTRA_MODULES = {f"{CLIENT}.observability.otel": {"opentelemetry"}}


def _client_modules() -> list[ModuleType]:
    return [
        veupathdb,
        *(
            importlib.import_module(info.name)
            for info in pkgutil.walk_packages(
                veupathdb.__path__,
                prefix=f"{CLIENT}.",
            )
        ),
    ]


def _imported_names(module: ModuleType) -> set[str]:
    path = module.__file__
    assert path is not None
    names: set[str] = set()
    for node in ast.walk(ast.parse(Path(path).read_text())):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
        elif isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
    return names


def _distributions(names: set[str]) -> set[str]:
    roots = {name.split(".")[0] for name in names}
    return {root for root in roots if root not in sys.stdlib_module_names} - {CLIENT}


@pytest.mark.parametrize("module", _client_modules(), ids=lambda m: m.__name__)
def test_no_module_reaches_a_host_or_a_database(module: ModuleType) -> None:
    allowed = OPTIONAL_EXTRA_MODULES.get(module.__name__, set())
    reached = _distributions(_imported_names(module)) & FORBIDDEN_ROOTS

    assert reached == reached & allowed


def test_an_optional_distribution_is_named_by_its_own_module_and_no_other() -> None:
    """The base install carries no OTEL, so only the adapter may import it."""
    reached = {
        module.__name__
        for module in _client_modules()
        if "opentelemetry" in _distributions(_imported_names(module))
    }

    assert reached == {f"{CLIENT}.observability.otel"}


def test_the_domain_opens_no_connection() -> None:
    reached = {
        module.__name__
        for module in _client_modules()
        if module.__name__.startswith(f"{CLIENT}.domain")
        and "httpx" in _distributions(_imported_names(module))
    }

    assert reached == set()


# Only these two subpackages open a connection, so a domain module that names
# neither cannot reach httpx through another client module.
CLIENT_SUBPACKAGES_WITH_IO = {f"{CLIENT}.wdk", f"{CLIENT}.eda"}


def test_the_domain_names_no_client_module_that_opens_a_connection() -> None:
    reached = {
        (module.__name__, name)
        for module in _client_modules()
        if module.__name__.startswith(f"{CLIENT}.domain")
        for name in _imported_names(module)
        if name.startswith(tuple(f"{root}." for root in CLIENT_SUBPACKAGES_WITH_IO))
        or name in CLIENT_SUBPACKAGES_WITH_IO
    }
    assert reached == set()


def test_the_wire_models_reach_only_the_model_library() -> None:
    reached = {
        name
        for module in _client_modules()
        if module.__name__ in WIRE_MODEL_MODULES
        for name in _distributions(_imported_names(module))
    }

    assert reached == ALLOWED_WIRE_MODEL_IMPORTS


def test_no_module_configures_the_hosts_logging() -> None:
    offenders = [
        module.__name__
        for module in _client_modules()
        if "structlog.configure" in Path(str(module.__file__)).read_text()
    ]

    assert offenders == []
