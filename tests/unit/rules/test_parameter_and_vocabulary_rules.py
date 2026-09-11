"""The parameter and vocabulary rules, over the recorded search documents."""

from __future__ import annotations

from typing import Any

import pytest

from veupathdb.domain.parameters.specs import (
    ParamSpecNormalized,
    fill_hidden_required_defaults,
    topological_fill_order,
)
from veupathdb.domain.parameters.value_codec import to_wire
from veupathdb.domain.parameters.wdk_vocab import (
    FAKE_ALL_SENTINEL,
    WDKTreeBoxVocabNode,
    flatten_vocab,
)
from veupathdb.json_types import JSONObject
from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk.client import VEuPathDBClient


def _recorded_parameters(name: str) -> dict[str, JSONObject]:
    body = load_recorded(name).json_body()
    assert isinstance(body, dict)
    search = body["searchData"]
    assert isinstance(search, dict)
    listed = search["parameters"]
    assert isinstance(listed, list)
    return {str(param["name"]): param for param in listed if isinstance(param, dict)}


class _Echo:
    """Answers one recorded body and keeps what it was sent."""

    def __init__(self, body: Any) -> None:
        self._body = body
        self.sent: list[dict[str, Any]] = []

    async def __call__(
        self, path: str, json: dict[str, Any] | None = None, **_: object
    ) -> Any:
        del path
        self.sent.append(json or {})
        return self._body


def test_wdk_param_007_a_numeric_bound_is_a_string_parameter_flagged_is_number() -> (
    None
):
    """The molecular-weight bounds arrive as `string`, not as a number type."""
    parameters = _recorded_parameters("search_genes_by_molecular_weight")
    bound = parameters["min_molecular_weight"]

    assert bound["type"] == "string"
    assert bound["isNumber"] is True


async def test_wdk_param_008_the_revise_endpoint_answer_is_what_wdk_substituted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The client returns WDK's echoed values, never the context it sent."""
    body = load_recorded("search_genes_by_location").json_body()
    client = VEuPathDBClient("https://example.invalid/service")
    echo = _Echo(body)
    monkeypatch.setattr(client, "post", echo)

    response = await client.get_search_details_with_params(
        "transcript", "GenesByLocation", {"organismSinglePick": "a value WDK replaces"}
    )

    parameters = response.search_data.parameters or []
    sent = echo.sent[0]["contextParamValues"]["organismSinglePick"]
    assert sent == "a value WDK replaces"
    assert [param.name for param in parameters] == list(
        _recorded_parameters("search_genes_by_location")
    )


def test_wdk_param_011_a_hidden_required_parameter_is_filled_from_its_default() -> None:
    """`isVisible: false` hides the parameter; WDK still requires a value."""
    recorded = _recorded_parameters("search_with_a_hidden_required_parameter")
    hidden = recorded["eda_dataset_id"]
    spec = ParamSpecNormalized(
        name="eda_dataset_id",
        param_type=str(hidden["type"]),
        is_visible=bool(hidden["isVisible"]),
        allow_empty_value=bool(hidden["allowEmptyValue"]),
        initial_display_value=str(hidden["initialDisplayValue"]),
    )

    filled = fill_hidden_required_defaults({spec.name: spec}, {})

    assert hidden["isVisible"] is False
    assert to_wire(filled["eda_dataset_id"]) == hidden["initialDisplayValue"]


def test_wdk_vocab_001_the_synthetic_root_is_not_a_selectable_term() -> None:
    """A tree whose root is `@@fake@@` offers its children and not the root."""
    tree = WDKTreeBoxVocabNode.model_validate(
        {
            "data": {"term": FAKE_ALL_SENTINEL, "display": "All"},
            "children": [
                {"data": {"term": "pfal", "display": "P. falciparum"}, "children": []}
            ],
        }
    )

    assert [option.value for option in flatten_vocab(tree)] == ["pfal"]


def test_wdk_vocab_003_the_order_of_dependent_params_carries_nothing() -> None:
    """A parent fills before its dependents, whatever order the list arrived in."""
    recorded = _recorded_parameters("search_genes_by_location")
    parent = recorded["organismSinglePick"]
    dependents = list(parent["dependentParams"] or [])

    def specs(order: list[str]) -> dict[str, ParamSpecNormalized]:
        return {
            "organismSinglePick": ParamSpecNormalized(
                name="organismSinglePick",
                param_type="single-pick-vocabulary",
                dependent_params=tuple(order),
            ),
            "chromosomeOptional": ParamSpecNormalized(
                name="chromosomeOptional", param_type="single-pick-vocabulary"
            ),
        }

    assert dependents == ["chromosomeOptional"]
    assert topological_fill_order(specs(dependents)) == topological_fill_order(
        specs(list(reversed(dependents)))
    )


async def test_wdk_vocab_004_a_dependent_value_travels_with_the_parent_it_was_read_under(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WDK accepts a dependent value under any parent, so the context is always sent."""
    client = VEuPathDBClient("https://example.invalid/service")
    echo = _Echo([])
    monkeypatch.setattr(client, "post", echo)

    await client.get_refreshed_dependent_params(
        "transcript",
        "GenesByLocation",
        "organismSinglePick",
        {"organismSinglePick": "P. falciparum", "chromosomeOptional": "Pf3D7_01_v3"},
    )

    sent = echo.sent[0]
    assert sent["changedParam"] == {
        "name": "organismSinglePick",
        "value": "P. falciparum",
    }
    assert sent["contextParamValues"]["chromosomeOptional"] == "Pf3D7_01_v3"


async def test_wdk_vocab_005_an_empty_array_names_no_stale_dependent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`200 []` is nothing to refresh, not every dependent cleared."""
    client = VEuPathDBClient("https://example.invalid/service")
    monkeypatch.setattr(client, "post", _Echo([]))

    refreshed = await client.get_refreshed_dependent_params(
        "transcript", "GenesByLocation", "organismSinglePick", {}
    )

    assert refreshed == []
