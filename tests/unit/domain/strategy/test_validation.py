"""A validity claim needs its level; absence of a claim is not a verdict.

``getValidationBundleJson`` writes ``level`` and ``isValid`` unconditionally
and adds ``errors`` only when the claim is negative.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from veupathdb.domain.strategy.validation import StepValidation, StepValidationErrors
from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk.wdk_models import WDKStep


class TestAVerdictNeedsALevel:
    def test_invalid_at_a_real_level_is_a_rejection(self) -> None:
        validation = StepValidation(level="SEMANTIC", isValid=False)

        assert validation.rejects()

    def test_invalid_at_level_none_is_not_a_rejection(self) -> None:
        # Nobody checked. Treating this as broken invents a defect.
        validation = StepValidation(level="NONE", isValid=False)

        assert not validation.rejects()

    def test_valid_at_a_real_level_is_not_a_rejection(self) -> None:
        assert not StepValidation(level="SEMANTIC", isValid=True).rejects()


class TestWhetherAnyoneChecked:
    def test_level_none_means_unchecked(self) -> None:
        assert not StepValidation(level="NONE", isValid=True).was_checked()

    def test_a_real_level_means_checked(self) -> None:
        assert StepValidation(level="RUNNABLE", isValid=True).was_checked()

    def test_the_default_is_unchecked(self) -> None:
        # The default must not read as a passing verdict.
        assert not StepValidation(level="NONE", is_valid=False).was_checked()


class TestTheMessages:
    def test_per_parameter_errors_are_reported(self) -> None:
        validation = StepValidation(
            level="SEMANTIC",
            isValid=False,
            errors=StepValidationErrors(byKey={"organism": ["Cannot be empty."]}),
        )

        assert validation.messages() == ["organism: Cannot be empty."]

    def test_general_errors_are_reported(self) -> None:
        validation = StepValidation(
            level="SEMANTIC",
            isValid=False,
            errors=StepValidationErrors(general=["Search is unavailable."]),
        )

        assert validation.messages() == ["Search is unavailable."]

    def test_no_errors_yields_no_messages(self) -> None:
        assert StepValidation(level="SEMANTIC", isValid=True).messages() == []


class TestWdkValid001TheBundleIsLevelAndIsValid:
    def test_wdk_valid_001_a_bundle_states_both_of_its_required_keys(self) -> None:
        bundle = StepValidation.model_validate(
            {"level": "SEMANTIC", "isValid": False, "errors": {"general": ["no"]}}
        )

        assert bundle.level == "SEMANTIC"
        assert bundle.is_valid is False

    def test_wdk_valid_001_a_bundle_without_is_valid_is_refused(self) -> None:
        # A renamed or missing key must not read as a positive claim.
        with pytest.raises(PydanticValidationError):
            StepValidation.model_validate({"level": "SEMANTIC"})

    def test_wdk_valid_001_a_bundle_without_a_level_is_refused(self) -> None:
        with pytest.raises(PydanticValidationError):
            StepValidation.model_validate({"isValid": True})

    def test_wdk_valid_001_errors_are_absent_on_a_positive_claim(self) -> None:
        bundle = StepValidation.model_validate({"level": "RUNNABLE", "isValid": True})

        assert bundle.errors is None
        assert bundle.messages() == []

    def test_wdk_valid_001_errors_split_general_from_by_key(self) -> None:
        recorded = load_recorded("refresh_with_a_value_outside_the_vocabulary")
        bundle = StepValidation.model_validate(recorded.json_body())

        assert bundle.is_valid is False
        assert bundle.errors is not None
        assert bundle.errors.by_key == {}
        assert bundle.errors.general == [
            "The passed changed param value 'Nope' is invalid."
        ]

    def test_wdk_valid_001_a_step_carrying_no_bundle_makes_no_claim(self) -> None:
        # Two defaults used to compose an absence of evidence into "valid".
        step = WDKStep.model_validate(
            {"id": 9, "searchName": "GenesByMolecularWeight", "searchConfig": {}}
        )

        assert step.validation is None
