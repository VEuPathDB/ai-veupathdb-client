"""The WDK and EDA bundle names WDK, EDA and this package, and no consumer."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

BUNDLE = Path(__file__).resolve().parents[2] / "docs" / "knowledge"
TREES = ("wdk", "eda")

# The application is named by its citation prefix or not at all. A sentence that
# needs the product name is a sentence about its mapping, which lives in its own
# repository.
CONSUMER_NAME = "pathfinder"
# A path another repository holds is written as a citation. These prefixes open
# the trees of the checkouts beside this one.
FOREIGN_PATHS = ("apps/api/", "apps/web/", "veupathdb-mcp/", "assistant-core/")
# A citation: a repository prefix, a colon, a space and a path, in a code span.
# The prefixes are listed, so a sentence that starts with a word and a colon is
# not read as one.
CITATION = re.compile(
    r"`{1,2}(?:pathfinder|veupathdb-py|veupathdb-mcp|assistant-platform):\s+[^`\s]+"
)


def _pages() -> list[Path]:
    pages = [page for tree in TREES for page in (BUNDLE / tree).rglob("*.md")]
    assert pages, f"{BUNDLE} holds no WDK or EDA page"
    return pages


def _outside_citations(page: Path) -> str:
    """The page with every citation removed, lowercased."""
    return CITATION.sub(" ", page.read_text()).lower()


@pytest.mark.parametrize("page", _pages(), ids=lambda p: p.name)
def test_no_page_names_the_consuming_application(page: Path) -> None:
    assert CONSUMER_NAME not in _outside_citations(page)


@pytest.mark.parametrize("page", _pages(), ids=lambda p: p.name)
def test_no_page_carries_a_bare_path_into_another_repository(page: Path) -> None:
    """A path this checkout does not hold carries the repository prefix."""
    text = _outside_citations(page)
    bare = [prefix for prefix in FOREIGN_PATHS if prefix in text]

    assert bare == []


def test_the_citation_prefix_is_how_the_application_is_named() -> None:
    """The lowercase prefix stays: it addresses a page, it does not state a subject."""
    citing = [page.name for page in _pages() if "`pathfinder: " in page.read_text()]

    assert citing != []
