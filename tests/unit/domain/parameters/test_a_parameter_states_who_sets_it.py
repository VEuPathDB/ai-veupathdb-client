from __future__ import annotations

import pytest

from veupathdb.domain.parameters.specs import (
    ParamSpecNormalized,
    fill_site_set_defaults,
    filled_site_set_defaults,
)
from veupathdb.domain.parameters.values import StringValue
from veupathdb.wdk.wdk_parameters import WDKBaseParameter


def _wire(**fields: object) -> WDKBaseParameter:
    return WDKBaseParameter.model_validate({"name": "p", "type": "string", **fields})


def test_a_hidden_parameter_is_set_by_the_site() -> None:
    wire = _wire(isVisible=False)
    spec = ParamSpecNormalized(name="p", param_type="string", is_visible=False)

    assert (wire.site_set, wire.bindable) == (True, False)
    assert (spec.site_set, spec.bindable) == (True, False)


def test_a_read_only_parameter_is_set_by_the_site() -> None:
    wire = _wire(isVisible=True, isReadOnly=True)
    spec = ParamSpecNormalized(name="p", param_type="string", is_read_only=True)

    assert (wire.site_set, wire.bindable) == (True, False)
    assert (spec.site_set, spec.bindable) == (True, False)


def test_a_visible_editable_parameter_is_bindable() -> None:
    wire = _wire(isVisible=True, isReadOnly=False)
    spec = ParamSpecNormalized(name="p", param_type="string")

    assert (wire.site_set, wire.bindable) == (False, True)
    assert (spec.site_set, spec.bindable) == (False, True)


@pytest.mark.parametrize(
    ("allow_empty", "min_selected", "required"),
    [(False, 0, True), (False, 1, True), (True, 0, False), (True, 1, False)],
)
def test_required_is_whether_the_empty_value_is_refused(
    allow_empty: bool, min_selected: int, required: bool
) -> None:
    wire = _wire(allowEmptyValue=allow_empty, minSelectedCount=min_selected)
    spec = ParamSpecNormalized(
        name="p",
        param_type="multi-pick-vocabulary",
        allow_empty_value=allow_empty,
        min_selected_count=min_selected,
    )

    assert wire.required is required
    assert spec.required is required


def test_a_visible_read_only_required_parameter_is_filled() -> None:
    specs = {
        "fixed": ParamSpecNormalized(
            name="fixed",
            param_type="string",
            is_read_only=True,
            initial_display_value="gene",
        )
    }

    assert filled_site_set_defaults(specs, {}) == ["fixed"]
    assert fill_site_set_defaults(specs, {}) == {"fixed": StringValue(value="gene")}
