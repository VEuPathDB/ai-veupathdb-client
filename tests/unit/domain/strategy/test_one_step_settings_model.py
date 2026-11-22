from __future__ import annotations

import pytest
from pydantic import ValidationError

from veupathdb.domain.parameters import (
    HeldValue,
    MultiPickValue,
    ParamValue,
    StringValue,
)
from veupathdb.domain.strategy import (
    ColocationParams,
    CombineOp,
    StepFilter,
    StepSettings,
    StrategyStepNode,
    flatten_tree,
    rebuild_tree,
    settings_of,
)
from veupathdb.errors import DataParsingError

_KINASE: dict[str, ParamValue] = {"text_expression": StringValue(value="kinase")}
_FILTER = StepFilter(name="f", value=1)


def _leaf() -> StrategyStepNode:
    return StrategyStepNode(
        id="a",
        search_name="GenesByTextSearch",
        parameters=_KINASE,
        wdk_weight=10,
        filters=[_FILTER],
        display_name="A",
    )


def test_a_node_gives_its_settings_without_its_name() -> None:
    assert settings_of(_leaf()) == StepSettings(
        search_name="GenesByTextSearch",
        parameters=_KINASE,
        wdk_weight=10,
        filters=[_FILTER],
    )


def test_a_keyed_step_gives_the_same_settings_as_its_node() -> None:
    assert settings_of(flatten_tree(_leaf())["a"]) == settings_of(_leaf())


def test_a_combine_has_no_search_name_and_keeps_its_operator() -> None:
    other = StrategyStepNode(id="b", search_name="GenesByTextSearch")
    combine = StrategyStepNode.model_validate(
        {
            "id": "c",
            "primaryInput": _leaf(),
            "secondaryInput": other,
            "operator": CombineOp.UNION,
        }
    )
    expected = StepSettings(operator=CombineOp.UNION)
    assert settings_of(combine) == expected
    assert settings_of(flatten_tree(combine)["c"]) == expected


def test_changed_names_the_differing_fields_in_declaration_order() -> None:
    held = StepSettings(wdk_weight=5, filters=[StepFilter(name="f")])
    assert StepSettings(wdk_weight=10).changed(held) == ["filters", "wdk_weight"]


def test_the_settings_are_the_eight_fields_wdk_behaviour_depends_on() -> None:
    assert set(StepSettings.model_fields) == {
        "search_name",
        "parameters",
        "operator",
        "colocation_params",
        "filters",
        "wdk_weight",
        "expanded_strategy_id",
        "expanded_name",
    }


_DEFAULT_LEAF_FILTER = StepFilter(
    name="matched_transcript_filter_array", value={"values": ["Y"]}
)
_PLAN_FILTER = StepFilter(name="gene_boolean_filter_array", value={"values": ["YN"]})


def test_held_settings_depart_only_from_the_filters_the_plan_sets() -> None:
    held = StepSettings(wdk_weight=10, filters=[_DEFAULT_LEAF_FILTER, _PLAN_FILTER])
    stated = StepSettings(wdk_weight=10, filters=[_PLAN_FILTER])
    assert held.departures_from(stated, stated, wdk_added=[]) == []


def test_a_plan_filter_wdk_does_not_hold_is_a_departure() -> None:
    held = StepSettings(wdk_weight=3, filters=[_DEFAULT_LEAF_FILTER])
    stated = StepSettings(wdk_weight=10, filters=[_PLAN_FILTER])
    assert held.departures_from(StepSettings(), stated, wdk_added=[]) == [
        "filters",
        "wdk_weight",
    ]


def test_a_plan_filter_held_with_another_value_is_a_departure() -> None:
    held = StepSettings(filters=[_DEFAULT_LEAF_FILTER])
    stated = StepSettings(
        filters=[StepFilter(name=_DEFAULT_LEAF_FILTER.name, value={"values": ["N"]})]
    )
    assert held.departures_from(stated, stated, wdk_added=[]) == ["filters"]


_OVERRIDE = StepFilter(name=_DEFAULT_LEAF_FILTER.name, value={"values": ["N"]})


def test_the_filters_wdk_added_are_those_the_plan_did_not_set() -> None:
    held = StepSettings(filters=[_DEFAULT_LEAF_FILTER, _PLAN_FILTER])
    stated = StepSettings(filters=[_PLAN_FILTER])
    assert held.filters_wdk_added(stated) == [_DEFAULT_LEAF_FILTER]


def test_a_filter_the_plan_removed_and_wdk_still_holds_is_a_departure() -> None:
    held = StepSettings(filters=[_DEFAULT_LEAF_FILTER, _PLAN_FILTER])
    before = StepSettings(filters=[_PLAN_FILTER])
    departures = held.departures_from(
        before, StepSettings(), wdk_added=[_DEFAULT_LEAF_FILTER]
    )
    assert departures == ["filters"]


def test_a_removed_filter_wdk_added_no_default_for_is_expected_absent() -> None:
    held = StepSettings(filters=[_DEFAULT_LEAF_FILTER])
    before = StepSettings(filters=[_PLAN_FILTER])
    departures = held.departures_from(
        before, StepSettings(), wdk_added=[_DEFAULT_LEAF_FILTER]
    )
    assert departures == []


def test_a_removed_override_wdk_answers_with_its_default_is_no_departure() -> None:
    held = StepSettings(filters=[_DEFAULT_LEAF_FILTER])
    before = StepSettings(filters=[_OVERRIDE])
    departures = held.departures_from(
        before, StepSettings(), wdk_added=[_DEFAULT_LEAF_FILTER]
    )
    assert departures == []


def test_a_removed_filter_equal_to_the_default_is_no_departure() -> None:
    held = StepSettings(filters=[_DEFAULT_LEAF_FILTER])
    before = StepSettings(filters=[_DEFAULT_LEAF_FILTER])
    departures = held.departures_from(
        before, StepSettings(), wdk_added=[_DEFAULT_LEAF_FILTER]
    )
    assert departures == []


def test_a_removed_override_still_held_departs_from_the_default() -> None:
    held = StepSettings(filters=[_OVERRIDE])
    before = StepSettings(filters=[_OVERRIDE])
    departures = held.departures_from(
        before, StepSettings(), wdk_added=[_DEFAULT_LEAF_FILTER]
    )
    assert departures == ["filters"]


def test_a_removed_override_held_with_a_third_value_is_a_departure() -> None:
    third = StepFilter(name=_DEFAULT_LEAF_FILTER.name, value={"values": ["Y", "N"]})
    held = StepSettings(filters=[third])
    departures = held.departures_from(
        StepSettings(filters=[_OVERRIDE]),
        StepSettings(),
        wdk_added=[_DEFAULT_LEAF_FILTER],
    )
    assert departures == ["filters"]


def test_a_removed_filter_whose_default_wdk_does_not_hold_is_a_departure() -> None:
    departures = StepSettings().departures_from(
        StepSettings(filters=[_OVERRIDE]),
        StepSettings(),
        wdk_added=[_DEFAULT_LEAF_FILTER],
    )
    assert departures == ["filters"]


def test_settings_are_read_from_a_mapping_and_not_from_attributes() -> None:
    with pytest.raises(ValidationError, match="StepSettings reads a mapping"):
        StepSettings.model_validate(_leaf(), from_attributes=True)


def test_a_put_carries_one_filter_per_name() -> None:
    first = StepFilter(name="a", value=1)
    held = StepSettings(filters=[first, StepFilter(name="a", value=2), _PLAN_FILTER])
    stated = StepFilter(name="a", value=3)
    assert held.filters_to_put(StepSettings(), StepSettings()) == [first, _PLAN_FILTER]
    assert held.filters_to_put(StepSettings(), StepSettings(filters=[stated])) == [
        stated,
        _PLAN_FILTER,
    ]


def test_a_removed_filter_with_no_recorded_default_is_expected_absent() -> None:
    held = StepSettings(filters=[_OVERRIDE])
    departures = held.departures_from(
        StepSettings(filters=[_OVERRIDE]), StepSettings(), wdk_added=[]
    )
    assert departures == ["filters"]


def test_the_read_back_leaves_the_parameters_to_validation() -> None:
    held = StepSettings(parameters={"text_expression": StringValue(value="Kinase")})
    stated = StepSettings(parameters=_KINASE)
    assert held.departures_from(stated, stated, wdk_added=[]) == []


def test_a_combine_wdk_names_departs_from_nothing_a_local_one_states() -> None:
    other = StrategyStepNode(id="b", search_name="GenesByTextSearch")
    read = StrategyStepNode(
        id="c",
        search_name="boolean_question_GeneRecordClasses_GeneRecordClass",
        primary_input=_leaf(),
        secondary_input=other,
        operator=CombineOp.UNION,
    )
    local = StrategyStepNode.model_validate(
        {
            "id": "c",
            "primaryInput": _leaf(),
            "secondaryInput": other,
            "operator": "UNION",
        }
    )
    held = settings_of(read)
    stated = settings_of(local)
    assert held.search_name is None
    assert settings_of(flatten_tree(read)["c"]) == held
    assert held.departures_from(stated, stated, wdk_added=[]) == []


def test_changed_reads_filters_by_name_and_not_by_order() -> None:
    first = StepSettings(filters=[_DEFAULT_LEAF_FILTER, _PLAN_FILTER])
    second = StepSettings(filters=[_PLAN_FILTER, _DEFAULT_LEAF_FILTER])
    assert first.changed(second) == []


def test_a_put_keeps_the_wdk_defaults_and_applies_the_plan_changes() -> None:
    held = StepSettings(filters=[_DEFAULT_LEAF_FILTER, _PLAN_FILTER])
    added = StepFilter(name="organism_filter", value={"values": ["Pf"]})
    before = StepSettings(filters=[_PLAN_FILTER])
    after = StepSettings(filters=[added])
    assert held.filters_to_put(before, after) == [_DEFAULT_LEAF_FILTER, added]


def test_a_put_replaces_a_held_filter_the_plan_sets_in_place() -> None:
    held = StepSettings(filters=[_DEFAULT_LEAF_FILTER, _PLAN_FILTER])
    changed = StepFilter(name=_DEFAULT_LEAF_FILTER.name, value={"values": ["N"]})
    after = StepSettings(filters=[changed, _PLAN_FILTER])
    assert held.filters_to_put(StepSettings(filters=[_PLAN_FILTER]), after) == [
        changed,
        _PLAN_FILTER,
    ]


def test_removing_the_only_plan_filter_leaves_the_wdk_default() -> None:
    held = StepSettings(filters=[_DEFAULT_LEAF_FILTER, _PLAN_FILTER])
    before = StepSettings(filters=[_PLAN_FILTER])
    assert held.filters_to_put(before, StepSettings()) == [_DEFAULT_LEAF_FILTER]


@pytest.mark.parametrize(
    "params",
    [
        ColocationParams(),
        ColocationParams(
            operation="contains", strand="same strand", begin_offset_a=500
        ),
        ColocationParams(output="b", region_b="upstream"),
    ],
)
def test_colocation_reads_back_from_its_wdk_parameters(
    params: ColocationParams,
) -> None:
    assert ColocationParams.from_wdk_params(params.to_wdk_params()) == params


def test_a_reordered_multi_pick_is_the_same_parameters() -> None:
    first = StepSettings(parameters={"o": MultiPickValue(values=["a", "b"])})
    second = StepSettings(parameters={"o": MultiPickValue(values=["b", "a"])})
    assert first.changed(second) == []
    assert first.changed(StepSettings(parameters={})) == ["parameters"]


def test_a_missing_span_parameter_is_a_parse_error_naming_it() -> None:
    params = ColocationParams().to_wdk_params()
    del params["span_strand"]
    with pytest.raises(DataParsingError, match="span_strand"):
        ColocationParams.from_wdk_params(params)


def test_an_unknown_span_value_is_a_parse_error_naming_it() -> None:
    params = ColocationParams().to_wdk_params() | {"span_operation": "touches"}
    with pytest.raises(DataParsingError, match="touches"):
        ColocationParams.from_wdk_params(params)


def test_a_plan_that_names_a_filter_twice_states_the_first() -> None:
    first = StepFilter(name="a", value=3)
    twice = StepSettings(filters=[first, StepFilter(name="a", value=4)])
    held = StepSettings(filters=[first])
    assert StepSettings().filters_to_put(StepSettings(), twice) == [first]
    assert twice.changed(held) == []
    assert held.departures_from(twice, twice, wdk_added=[]) == []
    assert held.filters_wdk_added(twice) == []


@pytest.mark.parametrize(
    ("key", "value"), [("span_output", "none"), ("span_begin_offset_a", "far")]
)
def test_a_span_value_the_model_refuses_is_a_parse_error_naming_it(
    key: str, value: str
) -> None:
    params = ColocationParams().to_wdk_params() | {key: value}
    with pytest.raises(DataParsingError, match=key):
        ColocationParams.from_wdk_params(params)


def test_an_expression_restated_in_another_writing_is_the_same_parameters() -> None:
    grouped = StepSettings(
        parameters={"phyletic_expression": StringValue(value="(pfal>=1T AND pviv>=1T)")}
    )
    written = StepSettings(
        parameters={"phyletic_expression": StringValue(value="pfal>=1T AND pviv>=1T")}
    )
    assert grouped.changed(written) == []


def test_a_held_value_is_read_in_the_kind_the_other_side_states() -> None:
    held = StepSettings(parameters={"o": HeldValue(wire='["b","a"]')})
    typed = StepSettings(parameters={"o": MultiPickValue(values=["a", "b"])})
    assert held.changed(typed) == []
    assert typed.changed(held) == []


def test_a_filter_held_with_another_value_than_the_plan_states_is_wdk_added() -> None:
    held = StepSettings(filters=[_DEFAULT_LEAF_FILTER, _PLAN_FILTER])
    stated = StepSettings(filters=[_OVERRIDE, _PLAN_FILTER])
    assert held.filters_wdk_added(stated) == [_DEFAULT_LEAF_FILTER]


@pytest.mark.parametrize("weight", [0, None])
def test_no_weight_reads_as_none(weight: int | None) -> None:
    assert StepSettings(wdk_weight=weight).wdk_weight is None


def test_what_wdk_added_rides_the_step_and_is_no_setting() -> None:
    added = [_DEFAULT_LEAF_FILTER]
    node = _leaf().model_copy(update={"filters_wdk_added": added})
    step = flatten_tree(node)["a"]
    assert (
        step.filters_wdk_added,
        rebuild_tree("a", {"a": step}).filters_wdk_added,
    ) == (
        added,
        added,
    )
    assert "filters_wdk_added" not in StepSettings.model_fields
    assert settings_of(node) == settings_of(
        node.model_copy(update={"filters_wdk_added": None})
    )
