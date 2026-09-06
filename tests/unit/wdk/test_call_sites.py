"""Properties of the source tree that no import contract can see.

Who may open a connection to a WDK host, what a user path may say, and which
names may never be written into code are all call sites, so all are read off
the syntax tree.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from veupathdb.testing.wdk_fixtures import load_recorded

_SOURCE_ROOT = Path(__file__).resolve().parents[3] / "src" / "veupathdb"
_INTEGRATION = "wdk"
_SITE_SOURCES = ("get_site", "SiteInfo", "service_url")
_CURRENT_ALIAS = "/users/current"
# The two calls whose whole job is resolving the concrete id.
_RESOLVERS = ("wdk/strategy_api/helpers.py",)


@dataclass(frozen=True)
class _CallSite:
    module: str
    line: int
    detail: str


@cache
def _modules() -> tuple[tuple[str, str], ...]:
    return tuple(
        (path.relative_to(_SOURCE_ROOT).as_posix(), path.read_text())
        for path in _SOURCE_ROOT.rglob("*.py")
        if "tests/" not in path.relative_to(_SOURCE_ROOT).as_posix()
    )


def _modules_containing(needle: str, *, under: str = "") -> list[str]:
    return [
        module
        for module, source in _modules()
        if module.startswith(under) and needle in source
    ]


def _is_httpx_client(node: ast.Call) -> bool:
    func = node.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr in {"AsyncClient", "Client"}
        and isinstance(func.value, ast.Name)
        and func.value.id == "httpx"
    )


def _site_backed_clients(module: str, source: str) -> list[_CallSite]:
    """Every httpx client whose base url is resolved from the site router."""
    found: list[_CallSite] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call) or not _is_httpx_client(node):
            continue
        for keyword in node.keywords:
            if keyword.arg != "base_url":
                continue
            expression = ast.unparse(keyword.value)
            if any(source_name in expression for source_name in _SITE_SOURCES):
                found.append(_CallSite(module, node.lineno, expression))
    return found


def _docstrings(tree: ast.AST) -> set[int]:
    """The id of every string node that is a docstring rather than a value."""
    holders = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    found: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, holders) or not node.body:
            continue
        first = node.body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
            found.add(id(first.value))
    return found


def _current_alias_literals(module: str, source: str) -> list[_CallSite]:
    """Every string value naming the ``current`` alias, docstrings excluded."""
    tree = ast.parse(source)
    prose = _docstrings(tree)
    return [
        _CallSite(module, node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and _CURRENT_ALIAS in node.value
        and id(node) not in prose
    ]


class TestWdkMap005OnlyTheIntegrationOpensAWdkConnection:
    def test_wdk_map_005_no_module_outside_the_integration_builds_a_site_client(
        self,
    ) -> None:
        offenders = [
            site
            for module, source in _modules()
            if not module.startswith(_INTEGRATION)
            for site in _site_backed_clients(module, source)
        ]

        assert offenders == []

    def test_wdk_map_005_the_check_sees_a_site_backed_client(self) -> None:
        # The property is the base url's origin, not a hostname literal.
        source = (
            "import httpx\n"
            "from veupathdb.wdk.factory import get_site\n"
            "client = httpx.AsyncClient(base_url=get_site(site_id).service_url)\n"
        )

        assert len(_site_backed_clients("transport/http/routers/x.py", source)) == 1

    def test_wdk_map_005_an_unrelated_client_is_not_reported(self) -> None:
        source = "import httpx\nclient = httpx.AsyncClient(base_url=settings.api_url)\n"

        assert _site_backed_clients("services/research/x.py", source) == []


def test_wdk_http_001_only_the_resolvers_name_the_current_alias() -> None:
    offenders = [
        site
        for module, source in _modules()
        if module not in _RESOLVERS
        for site in _current_alias_literals(module, source)
    ]

    assert offenders == []


def test_wdk_valid_007_no_level_is_ever_sent_to_wdk() -> None:
    """A level that is legal in the model can be fatal on the way out."""
    assert _modules_containing("validationLevel") == []


def test_wdk_ans_006_nothing_but_the_model_reads_scopes() -> None:
    """A client picking a reporter to CALL must not filter on scopes."""
    assert _modules_containing(".scopes") == []


def test_wdk_search_003_no_search_list_is_written_into_the_code() -> None:
    # A list hardcoded from one site is wrong for the next by a third.
    assert _modules_containing("GenesByMolecularWeight", under=_INTEGRATION) == []


def test_the_fixture_store_records_where_every_body_came_from() -> None:
    recorded = load_recorded("search_boolean_transcript")

    assert recorded.provenance.site == "plasmodb"
    assert recorded.provenance.url.startswith("https://plasmodb.org/")
    assert recorded.provenance.recorded_at
