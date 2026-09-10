"""The parameter a search still needs, and the ask that binds it."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from veupathdb.domain.parameters.unbound import UnboundParameter


def test_a_parameter_with_no_vocabulary_states_the_name_and_the_question() -> None:
    unbound = UnboundParameter(param_name="organism", question="Which organism?")

    assert (unbound.param_name, unbound.question, unbound.options) == (
        "organism",
        "Which organism?",
        [],
    )


def test_the_vocabulary_the_user_picks_from_travels_with_the_parameter() -> None:
    unbound = UnboundParameter(
        param_name="ref_sample",
        question="Choose the sample group for Reference samples",
        options=["Sample type=ring", "Sample type=schizont"],
    )

    assert unbound.options == ["Sample type=ring", "Sample type=schizont"]


def test_the_wire_form_names_the_parameter_in_camel_case() -> None:
    unbound = UnboundParameter(param_name="min_peptides", question="How many?")

    assert unbound.model_dump(by_alias=True) == {
        "paramName": "min_peptides",
        "question": "How many?",
        "options": [],
    }


def test_a_parameter_name_is_required() -> None:
    with pytest.raises(ValidationError):
        UnboundParameter(question="Which one?")
