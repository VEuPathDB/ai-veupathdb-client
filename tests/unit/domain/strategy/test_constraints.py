"""What a constraint claims, when it blocks, and how two statements merge."""

from __future__ import annotations

from veupathdb.domain.strategy.constraints import (
    CombinationRequest,
    Constraint,
    ConstraintKind,
    ConstraintSource,
    ConstraintStatus,
    GroundedConstraint,
    combination_requirements_from,
    is_blocking,
    merge_constraints,
    provisional_constraints,
)


def _data_type(
    value: str,
    source: ConstraintSource = ConstraintSource.ASSUMED,
    *,
    hard: bool = True,
) -> Constraint:
    return Constraint(
        kind=ConstraintKind.DATA_TYPE,
        requested_value=value,
        source=source,
        label="data type",
        hard=hard,
    )


def _combination(value: str) -> Constraint:
    return Constraint(
        kind=ConstraintKind.COMBINATION,
        requested_value=value,
        label="how the evidence combines",
        source=ConstraintSource.USER_EXPLICIT,
    )


def test_constraint_defaults_to_assumed() -> None:
    constraint = Constraint(
        kind=ConstraintKind.DATA_TYPE, requested_value="RNA-Seq", label="data type"
    )

    assert constraint.source is ConstraintSource.ASSUMED


def test_blocking_only_for_user_explicit_unmet() -> None:
    explicit = _data_type("RNA-Seq", ConstraintSource.USER_EXPLICIT)
    assumed = explicit.model_copy(update={"source": ConstraintSource.ASSUMED})

    verdicts = [
        is_blocking(
            GroundedConstraint(
                constraint=explicit, status=ConstraintStatus.UNGROUNDABLE, note="x"
            )
        ),
        is_blocking(
            GroundedConstraint(
                constraint=explicit,
                status=ConstraintStatus.SUBSTITUTED,
                realized_value="microarray",
                note="x",
            )
        ),
        is_blocking(
            GroundedConstraint(
                constraint=explicit,
                status=ConstraintStatus.GROUNDED,
                realized_value="RNA-Seq",
            )
        ),
        is_blocking(
            GroundedConstraint(
                constraint=assumed, status=ConstraintStatus.UNGROUNDABLE, note="x"
            )
        ),
    ]

    assert verdicts == [True, True, False, False]


def test_soft_user_explicit_constraint_does_not_block() -> None:
    soft = _data_type(
        "RNA-Seq preferred, microarray fallback ok",
        ConstraintSource.USER_EXPLICIT,
        hard=False,
    )
    substituted = GroundedConstraint(
        constraint=soft,
        status=ConstraintStatus.SUBSTITUTED,
        realized_value="microarray",
    )

    assert is_blocking(substituted) is False


def test_provisional_constraints_are_pending_and_non_blocking() -> None:
    [grounded] = provisional_constraints(
        [_data_type("RNA-Seq", ConstraintSource.USER_EXPLICIT)]
    )

    assert grounded.status is ConstraintStatus.PROVISIONAL
    assert grounded.realized_value is None
    assert is_blocking(grounded) is False


class TestMergingRequirements:
    def test_merge_explicit_overrides_assumed_per_kind_and_forces_user_explicit(
        self,
    ) -> None:
        provisional = [
            _data_type("RNA-Seq or microarray"),
            Constraint(
                kind=ConstraintKind.ORGANISM,
                requested_value="Aedes aegypti",
                label="organism",
                source=ConstraintSource.ASSUMED,
            ),
        ]

        merged = merge_constraints(provisional, [_data_type("RNA-Seq only")])

        by_kind = {c.kind: c for c in merged}
        assert by_kind[ConstraintKind.DATA_TYPE].requested_value == "RNA-Seq only"
        assert (
            by_kind[ConstraintKind.DATA_TYPE].source is ConstraintSource.USER_EXPLICIT
        )
        assert by_kind[ConstraintKind.ORGANISM].source is ConstraintSource.ASSUMED

    def test_two_combination_requirements_both_survive_the_merge(self) -> None:
        """A combination names its own criteria, so a second one is a new
        dimension."""
        merged = merge_constraints(
            [],
            [
                _combination("mass spec OR DeRisi expression"),
                _combination("kinase domain AND phosphatase domain"),
            ],
        )

        assert [c.requested_value for c in merged] == [
            "mass spec OR DeRisi expression",
            "kinase domain AND phosphatase domain",
        ]

    def test_the_same_combination_stated_twice_is_one_requirement(self) -> None:
        merged = merge_constraints(
            [_combination("mass spec OR DeRisi expression")],
            [_combination("mass spec OR DeRisi expression")],
        )

        assert len(merged) == 1
        assert merged[0].source is ConstraintSource.USER_EXPLICIT

    def test_another_kind_still_collapses_per_dimension(self) -> None:
        merged = merge_constraints(
            [_data_type("microarray")], [_data_type("RNA-Seq only")]
        )

        assert [c.requested_value for c in merged] == ["RNA-Seq only"]

    def test_only_the_combination_requirements_are_read_for_the_gate(self) -> None:
        requirements = [
            Constraint(
                kind=ConstraintKind.ORGANISM,
                requested_value="Plasmodium falciparum",
                label="organism",
            ),
            _combination("mass spec OR DeRisi expression"),
        ]

        assert [
            c.requested_value for c in combination_requirements_from(requirements)
        ] == ["mass spec OR DeRisi expression"]


def _parsed(expression: str) -> list[str]:
    """The operator and terms the expression states, empty when unparseable."""
    request = CombinationRequest.parse(expression)
    return [] if request is None else [request.operator, *request.terms]


class TestCombinationRequest:
    def test_an_or_expression_reads_its_terms(self) -> None:
        assert _parsed("mass spectrometry evidence OR DeRisi expression") == [
            "OR",
            "mass spectrometry evidence",
            "DeRisi expression",
        ]

    def test_an_and_expression_reads_its_terms(self) -> None:
        assert _parsed("kinase domain AND mass spectrometry") == [
            "AND",
            "kinase domain",
            "mass spectrometry",
        ]

    def test_three_terms_are_one_operator_over_three(self) -> None:
        assert _parsed("GO terms OR InterPro domains OR EC numbers") == [
            "OR",
            "GO terms",
            "InterPro domains",
            "EC numbers",
        ]

    def test_mixed_operators_are_unparseable(self) -> None:
        assert _parsed("a OR b AND c") == []

    def test_a_lowercase_word_is_not_an_operator(self) -> None:
        assert _parsed("mass spectrometry or DeRisi") == []

    def test_a_single_term_is_no_combination(self) -> None:
        assert _parsed("OR them") == []

    def test_an_empty_term_is_unparseable(self) -> None:
        assert _parsed("mass spectrometry OR ") == []

    def test_the_expression_reads_back_as_the_user_stated_it(self) -> None:
        request = CombinationRequest.parse("mass spec OR DeRisi")

        assert request is not None
        assert request.expression == "mass spec OR DeRisi"
