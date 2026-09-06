"""Every body PathFinder sends, against the WDK schema its endpoint annotates.

WDK validates a request body where the JAX-RS method carries ``@InSchema``, so
for those seven names the published schema is the contract and a body that
breaks it is a 400 on the wire. Each body below is built by the model the
client sends and dumped with the call in ``strategy_api`` that sends it.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ConfigDict, Field

from veupathdb.devtools.fixtures import ENFORCED_SCHEMAS, verify_body
from veupathdb.domain.strategy.ops import CombineOp
from veupathdb.json_types import JSONObject
from veupathdb.testing.wdk_fixtures import fixture_request, load_recorded
from veupathdb.wdk.wdk_models import (
    CombinedStepSpec,
    NewStepSpec,
    PatchStepSpec,
    WDKDatasetBasketContent,
    WDKDatasetConfig,
    WDKDatasetConfigBasket,
    WDKDatasetConfigFile,
    WDKDatasetConfigIdList,
    WDKDatasetConfigStrategy,
    WDKDatasetConfigUrl,
    WDKDatasetFileContent,
    WDKDatasetIdListContent,
    WDKDatasetStrategyContent,
    WDKDatasetUrlContent,
    WDKDisplayPreferences,
    WDKFilterValue,
    WDKSearchConfig,
    WDKSearchResponse,
    WDKStepTree,
)

_SEARCH = "GenesByMolecularWeight"
_GENES = ("PF3D7_0103200", "PF3D7_0901900")
_LOCUS_TAG_SEARCH = "GeneByLocusTag"
_LOCUS_TAG_PARAM = "ds_gene_ids"


class _RecordedAnswerRequest(BaseModel):
    """The request body the molecular-weight answer fixture recorded."""

    model_config = ConfigDict(extra="ignore")

    search_config: WDKSearchConfig = Field(alias="searchConfig")
    report_config: JSONObject = Field(alias="reportConfig")


def _recorded_answer_request() -> _RecordedAnswerRequest:
    return _RecordedAnswerRequest.model_validate(
        fixture_request("answer_report_by_molecular_weight").body
    )


def _boolean_search() -> tuple[str, tuple[str, str, str]]:
    """The boolean search and its three operand parameters, as WDK publishes them."""
    recorded = WDKSearchResponse.model_validate(
        load_recorded("search_boolean_transcript").json_body()
    )
    names = recorded.search_data.param_names
    left = next(name for name in names if name.startswith("bq_left_op"))
    right = next(name for name in names if name.startswith("bq_right_op"))
    operator = next(name for name in names if name.startswith("bq_operator"))
    return recorded.search_data.url_segment, (left, right, operator)


def _new_step_body(spec: NewStepSpec) -> JSONObject:
    """``StepsMixin.create_step`` and ``create_transform_step``."""
    payload: JSONObject = {
        "searchName": spec.search_name,
        "searchConfig": spec.search_config.model_dump(
            by_alias=True, exclude_defaults=True
        ),
    }
    if spec.custom_name:
        payload["customName"] = spec.custom_name
    return payload


def _combined_step_body(spec: CombinedStepSpec) -> JSONObject:
    """``StepsMixin.create_combined_step``."""
    boolean_search, (left, right, operator) = _boolean_search()
    search_config: JSONObject = {
        "parameters": {
            left: "",
            right: "",
            operator: spec.boolean_operator.value,
        },
    }
    if spec.wdk_weight is not None:
        search_config["wdkWeight"] = spec.wdk_weight
    payload: JSONObject = {
        "searchName": boolean_search,
        "searchConfig": search_config,
    }
    if spec.custom_name:
        payload["customName"] = spec.custom_name
    return payload


def _search_config_write(
    config: WDKSearchConfig, filters: list[WDKFilterValue]
) -> JSONObject:
    """``StepsMixin.update_step_search_config``."""
    payload: JSONObject = config.model_dump(by_alias=True, exclude_defaults=True)
    payload["filters"] = [f.model_dump(by_alias=True) for f in filters]
    return payload


def _filter_write(config: WDKSearchConfig, filters: list[WDKFilterValue]) -> JSONObject:
    """``AnalysisEndpoints.update_step_filters``, which writes the whole config back."""
    payload: JSONObject = config.model_dump(by_alias=True, exclude_none=True)
    payload.pop("viewFilters", None)
    payload["filters"] = [f.model_dump(by_alias=True) for f in filters]
    return payload


def _mw_config() -> WDKSearchConfig:
    return _recorded_answer_request().search_config


def test_a_new_step_body_passes_the_schema_wdk_binds() -> None:
    spec = NewStepSpec(
        search_name=_SEARCH,
        search_config=_mw_config(),
        custom_name="50-50.1 kDa",
    )

    assert verify_body("wdk.users.steps.post-request", _new_step_body(spec)) == ()


def test_a_new_step_body_without_a_custom_name_passes() -> None:
    spec = NewStepSpec(search_name=_SEARCH, search_config=_mw_config())

    assert verify_body("wdk.users.steps.post-request", _new_step_body(spec)) == ()


def test_a_weighted_new_step_body_passes() -> None:
    config = WDKSearchConfig(parameters=_mw_config().parameters, wdk_weight=10)
    spec = NewStepSpec(search_name=_SEARCH, search_config=config)

    assert verify_body("wdk.users.steps.post-request", _new_step_body(spec)) == ()


def test_a_combined_step_body_passes_the_schema_wdk_binds() -> None:
    spec = CombinedStepSpec(
        primary_step_id=1,
        secondary_step_id=2,
        boolean_operator=CombineOp.INTERSECT,
        custom_name="kinases and secreted",
        wdk_weight=0,
    )

    assert verify_body("wdk.users.steps.post-request", _combined_step_body(spec)) == ()


@pytest.mark.parametrize(
    "spec",
    [
        PatchStepSpec(custom_name="kinases"),
        PatchStepSpec(expanded=True, expanded_name="nested"),
        PatchStepSpec(
            display_preferences=WDKDisplayPreferences(
                column_selection=["primary_key"],
                sort_columns=[{"name": "primary_key", "direction": "ASC"}],
            )
        ),
    ],
)
def test_a_step_properties_patch_passes_the_schema_wdk_binds(
    spec: PatchStepSpec,
) -> None:
    body = spec.model_dump(by_alias=True, exclude_none=True, mode="json")

    assert verify_body("wdk.users.steps.id.patch-request", body) == ()


def test_a_search_config_write_passes_the_schema_wdk_binds() -> None:
    filters = [WDKFilterValue(name="matched_transcript_filter_array", value=None)]

    body = _search_config_write(_mw_config(), filters)

    assert verify_body("wdk.answer.answer-spec-request", body) == ()


def test_a_filter_write_passes_the_schema_wdk_binds() -> None:
    filters = [
        WDKFilterValue(
            name="matched_transcript_filter_array",
            value={"values": ["Y"]},
            disabled=True,
        )
    ]

    body = _filter_write(_mw_config(), filters)

    assert verify_body("wdk.answer.answer-spec-request", body) == ()


def test_a_search_report_body_passes_the_schema_wdk_binds() -> None:
    recorded = _recorded_answer_request()

    body: JSONObject = {
        "searchConfig": recorded.search_config.model_dump(
            by_alias=True, exclude_defaults=True
        ),
        "reportConfig": recorded.report_config,
    }

    assert verify_body("wdk.answer.post-request", body) == ()


def test_a_report_body_with_no_report_config_passes() -> None:
    body: JSONObject = {
        "searchConfig": _mw_config().model_dump(by_alias=True, exclude_defaults=True),
        "reportConfig": {},
    }

    assert verify_body("wdk.answer.post-request", body) == ()


def _strategy_body(tree: WDKStepTree, *, description: str | None) -> JSONObject:
    """``StrategiesMixin.create_strategy``."""
    payload: JSONObject = {
        "name": "Small kinases",
        "isPublic": False,
        "isSaved": False,
        "stepTree": tree.model_dump(by_alias=True, exclude_none=True, mode="json"),
    }
    if description:
        payload["description"] = description
    return payload


def _tree() -> WDKStepTree:
    return WDKStepTree(
        step_id=3,
        primary_input=WDKStepTree(step_id=1),
        secondary_input=WDKStepTree(step_id=2),
    )


@pytest.mark.parametrize("description", [None, "two searches intersected"])
def test_a_new_strategy_body_passes_the_schema_wdk_binds(
    description: str | None,
) -> None:
    body = _strategy_body(_tree(), description=description)

    assert verify_body("wdk.users.strategies.post-request", body) == ()


def test_a_step_tree_write_passes_the_schema_wdk_binds() -> None:
    """``StrategiesMixin.update_strategy`` writes the tree under its own key."""
    body: JSONObject = {
        "stepTree": _tree().model_dump(by_alias=True, exclude_none=True, mode="json")
    }

    assert verify_body("wdk.users.strategies.id.put-request", body) == ()


@pytest.mark.parametrize(
    "config",
    [
        WDKDatasetConfigIdList(
            source_type="idList",
            source_content=WDKDatasetIdListContent(ids=list(_GENES)),
        ),
        WDKDatasetConfigBasket(
            source_type="basket",
            source_content=WDKDatasetBasketContent(basket_name="transcript"),
        ),
        WDKDatasetConfigStrategy(
            source_type="strategy",
            source_content=WDKDatasetStrategyContent(strategy_id=330423363),
        ),
        WDKDatasetConfigFile(
            source_type="file",
            source_content=WDKDatasetFileContent(
                temporary_file_id="f1",
                parser="list",
                search_name=_LOCUS_TAG_SEARCH,
                parameter_name=_LOCUS_TAG_PARAM,
            ),
        ),
        WDKDatasetConfigUrl(
            source_type="url",
            source_content=WDKDatasetUrlContent(
                url="https://plasmodb.org/genes.txt",
                parser="list",
                search_name=_LOCUS_TAG_SEARCH,
                parameter_name=_LOCUS_TAG_PARAM,
            ),
        ),
    ],
)
def test_every_dataset_source_passes_the_schema_wdk_binds(
    config: WDKDatasetConfig,
) -> None:
    """``DatasetsMixin.create_dataset``."""
    body: JSONObject = config.model_dump(by_alias=True)

    assert verify_body("wdk.users.datasets.post-request", body) == ()


def test_a_search_config_that_keeps_its_defaults_is_refused() -> None:
    """Both config writers strip the two keys a search config may not carry."""
    body = _mw_config().model_dump(by_alias=True)

    assert verify_body("wdk.answer.answer-spec-request", body) == (
        "<root>: Additional properties are not allowed ('viewFilters' was unexpected)",
        "columnFilters: None is not of type 'object'",
    )


def test_a_display_preference_with_no_columns_is_refused() -> None:
    """An empty column selection is not a body WDK accepts."""
    spec = PatchStepSpec(display_preferences=WDKDisplayPreferences(column_selection=[]))
    body = spec.model_dump(by_alias=True, exclude_none=True, mode="json")

    assert verify_body("wdk.users.steps.id.patch-request", body) == (
        "displayPreferences/columnSelection: [] should be non-empty",
    )


def test_every_request_schema_wdk_enforces_is_covered_here() -> None:
    requests = {name for name in ENFORCED_SCHEMAS if name.endswith("-request")}

    assert requests == {
        "wdk.answer.answer-spec-request",
        "wdk.answer.post-request",
        "wdk.users.datasets.post-request",
        "wdk.users.steps.id.patch-request",
        "wdk.users.steps.post-request",
        "wdk.users.strategies.id.put-request",
        "wdk.users.strategies.post-request",
    }
