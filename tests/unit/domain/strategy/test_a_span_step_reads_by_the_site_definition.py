from __future__ import annotations

import pytest
from pydantic import ConfigDict, Field

from veupathdb.domain.strategy import ColocationParams
from veupathdb.errors import DataParsingError
from veupathdb.model import CamelModel
from veupathdb.testing.wdk_fixtures import load_recorded

_PLACEHOLDER = "none"


class _Param(CamelModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    initial_display_value: str | None = None
    vocabulary: list[tuple[str, str, str | None]] = Field(default_factory=list)


class _SearchData(CamelModel):
    model_config = ConfigDict(extra="ignore")

    parameters: list[_Param]


class _Search(CamelModel):
    model_config = ConfigDict(extra="ignore")

    search_data: _SearchData


def _enums() -> dict[str, _Param]:
    search = _Search.model_validate(
        load_recorded("search_genes_by_span_logic").json_body()
    )
    return {p.name: p for p in search.search_data.parameters if p.vocabulary}


def _terms() -> list[tuple[str, str]]:
    return [
        (name, term)
        for name, param in _enums().items()
        for term, _, _ in param.vocabulary
        if (name, term) != ("span_output", _PLACEHOLDER)
    ]


@pytest.mark.parametrize(("key", "term"), _terms())
def test_every_term_the_site_offers_reads_back(key: str, term: str) -> None:
    params = ColocationParams().to_wdk_params() | {key: term}
    assert ColocationParams.from_wdk_params(params).to_wdk_params()[key] == term


def test_wdk_step_010_the_output_placeholder_the_site_offers_is_refused() -> None:
    output = _enums()["span_output"]
    assert output.initial_display_value == _PLACEHOLDER
    assert [term for term, _, _ in output.vocabulary] == [_PLACEHOLDER, "a", "b"]
    params = ColocationParams().to_wdk_params() | {"span_output": _PLACEHOLDER}
    with pytest.raises(DataParsingError, match="span_output 'none' is not one of a, b"):
        ColocationParams.from_wdk_params(params)
