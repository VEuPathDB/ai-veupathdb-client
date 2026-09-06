"""One answer to "what state is this step in".

Status is DERIVED from the wiring, the WDK id and the validation bundle rather
than stored on the step: a stored copy would need updating at every push, param
edit and rewire, and a missed path leaves a step claiming to be built when it
is not.
"""

from __future__ import annotations

from veupathdb.domain.strategy.graph_model import (
    StepKind,
    StepStatus,
    StrategyStep,
    step_status,
)
from veupathdb.domain.strategy.ops import CombineOp
from veupathdb.domain.strategy.validation import StepValidation, StepValidationErrors

_INPUT_REFUSED = (
    "The step referenced by ID '440085983' is not runnable because: "
    '{"keyedErrors":{},"validationLevel":"RUNNABLE","validationStatus":"INVALID"}'
)


def _leaf(step_id: str = "a") -> StrategyStep:
    return StrategyStep(id=step_id, kind=StepKind.SEARCH, search_name="GenesByTaxon")


def _combine(step_id: str = "c") -> StrategyStep:
    return StrategyStep(
        id=step_id,
        kind=StepKind.COMBINE,
        primary_input_id="a",
        secondary_input_id="b",
        operator=CombineOp.INTERSECT,
    )


def _status(
    step: StrategyStep,
    *,
    wdk_step_id: int | None = 100,
    validation: StepValidation | None = None,
    has_open_params: bool = False,
) -> StepStatus:
    return step_status(
        step,
        wdk_step_id=wdk_step_id,
        validation=validation,
        has_open_params=has_open_params,
    )


def _runnable_refusal(key: str = "bq_left_op") -> StepValidation:
    return StepValidation(
        level="RUNNABLE",
        is_valid=False,
        errors=StepValidationErrors(by_key={key: [_INPUT_REFUSED]}),
    )


class TestReady:
    def test_a_complete_step_not_yet_pushed_is_ready(self) -> None:
        """Not a draft: pushing is how it stops being unbuilt, so calling it a
        draft would defer it forever."""
        assert _status(_leaf(), wdk_step_id=None) is StepStatus.READY

    def test_ready_is_pushable(self) -> None:
        assert StepStatus.READY.is_pushable is True


class TestDraft:
    def test_unfilled_required_params_make_a_draft(self) -> None:
        """The UI adds the step first and collects its parameters second."""
        assert _status(_leaf(), has_open_params=True) is StepStatus.DRAFT

    def test_a_combine_missing_an_input_is_a_draft(self) -> None:
        half_wired = _combine()
        half_wired.secondary_input_id = None

        assert _status(half_wired) is StepStatus.DRAFT

    def test_a_combine_without_an_operator_is_a_draft(self) -> None:
        no_op = _combine()
        no_op.operator = None

        assert _status(no_op) is StepStatus.DRAFT


class TestBuilt:
    def test_a_pushed_complete_step_is_built(self) -> None:
        assert _status(_leaf()) is StepStatus.BUILT

    def test_a_pushed_wired_combine_is_built(self) -> None:
        assert _status(_combine(), wdk_step_id=300) is StepStatus.BUILT

    def test_a_valid_validation_keeps_it_built(self) -> None:
        assert (
            _status(_leaf(), validation=StepValidation(level="SEMANTIC", is_valid=True))
            is StepStatus.BUILT
        )

    def test_wdk_valid_004_an_unchecked_bundle_is_not_a_refusal(self) -> None:
        # A structural write builds at NONE, which pairs isValid false with
        # nobody having looked.
        unchecked = StepValidation(level="NONE", is_valid=False)

        assert _status(_combine(), validation=unchecked) is StepStatus.BUILT


class TestInvalid:
    def test_wdk_rejecting_a_pushed_step_makes_it_invalid(self) -> None:
        assert (
            _status(
                _leaf(), validation=StepValidation(level="SEMANTIC", is_valid=False)
            )
            is StepStatus.INVALID
        )

    def test_a_never_pushed_step_is_not_invalid(self) -> None:
        """Nothing is in WDK to be invalid about."""
        assert (
            _status(
                _leaf(),
                wdk_step_id=None,
                validation=StepValidation(level="SEMANTIC", is_valid=False),
            )
            is StepStatus.READY
        )

    def test_wdk_valid_004_a_runnable_refusal_makes_the_consumer_invalid(self) -> None:
        assert _status(_combine(), validation=_runnable_refusal()) is StepStatus.INVALID


class TestPushability:
    def test_only_a_draft_is_unpushable(self) -> None:
        """The planner skips drafts by definition instead of inferring them."""
        assert {status.name: status.is_pushable for status in StepStatus} == {
            "DRAFT": False,
            "READY": True,
            "BUILT": True,
            "INVALID": True,
        }


class TestWdkValid004TheLevelCarriesTheClaim:
    """An input's invalidity reaches its consumer only at ``RUNNABLE``: below
    that level ``AnswerParam.validateValue`` never looks the input up."""

    def test_wdk_valid_004_a_semantic_pass_is_not_a_runnable_pass(self) -> None:
        semantic = StepValidation(level="SEMANTIC", is_valid=True)

        assert semantic.was_checked()
        assert not semantic.rejects()
        assert semantic.level != "RUNNABLE"

    def test_wdk_valid_004_a_refusal_is_keyed_under_the_answer_parameter(self) -> None:
        runnable = _runnable_refusal("bq_left_op_TranscriptRecordClasses")

        # A client reading `general` for structural problems finds nothing.
        assert runnable.errors is not None
        assert runnable.errors.general == []
        assert runnable.messages()[0].startswith("bq_left_op_")

    def test_wdk_valid_004_the_embedded_bundle_is_not_parsed(self) -> None:
        # The input's own bundle is pretty-printed into the message, under
        # different field names. Re-read the input step instead.
        runnable = _runnable_refusal()

        assert "validationStatus" in runnable.messages()[0]
        assert runnable.errors is not None
        assert list(runnable.errors.by_key) == ["bq_left_op"]
