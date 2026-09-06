"""The pure structural check behind a stated combination.

A requirement names criteria by their words, because the ids are renumbered on
the step ids a build mints. The check reads the tree the criteria meet in.
"""

from __future__ import annotations

from veupathdb.domain.strategy.combination_check import (
    combination_terms_overlap,
    combination_violation,
    first_combination_violation,
    match_terms,
    meeting_operator,
    required_operator,
)
from veupathdb.domain.strategy.constraints import (
    CombinationRequest,
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from veupathdb.domain.strategy.operational_spec import (
    Criterion,
    SpecStructure,
    StructureNode,
)
from veupathdb.domain.strategy.ops import CombineOp

_MASS_SPEC = Criterion(
    id="c_ms",
    text="trophozoite mass spectrometry evidence",
    search_name="GenesByMassSpec",
)
_DERISI = Criterion(
    id="c_derisi",
    text="DeRisi timecourse expression",
    search_name="GenesByRNASeqEvidence",
)
_KINASE = Criterion(
    id="c_kinase",
    text="kinases by molecular function",
    search_name="GenesByGoTerm",
)
_CRITERIA = [_KINASE, _MASS_SPEC, _DERISI]


def _leaf(criterion_id: str) -> StructureNode:
    return StructureNode(kind="leaf", criterion_id=criterion_id)


def _combine(operator: CombineOp, *inputs: StructureNode) -> StructureNode:
    return StructureNode(kind="combine", operator=operator, inputs=list(inputs))


def _matched(terms: list[str], criteria: list[Criterion]) -> dict[str, str]:
    """The term-to-criterion map, empty when the match abstains."""
    return match_terms(terms, criteria) or {}


def _meeting(structure: SpecStructure, criterion_ids: list[str]) -> str:
    """The operator the criteria meet at, empty when they never meet."""
    operator = meeting_operator(structure, criterion_ids)
    return "" if operator is None else operator.value


def _violation(
    request: CombinationRequest,
    criterion_ids: list[str],
    structure: SpecStructure,
) -> str:
    """Why the structure breaks the request, empty when it honors it."""
    return combination_violation(request, criterion_ids, structure) or ""


class TestMatchTerms:
    def test_each_term_takes_the_criterion_that_shares_its_words(self) -> None:
        matched = match_terms(
            ["mass spectrometry evidence", "DeRisi expression"], _CRITERIA
        )

        assert matched == {
            "mass spectrometry evidence": "c_ms",
            "DeRisi expression": "c_derisi",
        }

    def test_the_search_name_counts_as_words_of_the_criterion(self) -> None:
        matched = match_terms(["mass spec", "DeRisi"], _CRITERIA)

        assert matched == {"mass spec": "c_ms", "DeRisi": "c_derisi"}

    def test_a_term_that_names_nothing_abstains(self) -> None:
        assert _matched(["proteomics", "DeRisi expression"], _CRITERIA) == {}

    def test_a_term_two_criteria_share_equally_abstains(self) -> None:
        criteria = [
            Criterion(id="c1", text="mass spectrometry evidence in trophozoites"),
            Criterion(id="c2", text="mass spectrometry evidence in schizonts"),
            _DERISI,
        ]

        assert _matched(["mass spectrometry", "DeRisi"], criteria) == {}

    def test_two_terms_that_name_one_criterion_abstain(self) -> None:
        assert _matched(["mass spectrometry", "mass spec"], _CRITERIA) == {}

    def test_a_term_of_only_filler_words_abstains(self) -> None:
        assert _matched(["the genes", "DeRisi expression"], _CRITERIA) == {}


class TestMeetingOperator:
    def test_two_leaves_under_one_combine_meet_at_its_operator(self) -> None:
        structure = SpecStructure(
            root=_combine(CombineOp.UNION, _leaf("c_ms"), _leaf("c_derisi"))
        )

        assert meeting_operator(structure, ["c_ms", "c_derisi"]) is CombineOp.UNION

    def test_a_nested_branch_is_the_meeting_node_not_the_root(self) -> None:
        structure = SpecStructure(
            root=_combine(
                CombineOp.INTERSECT,
                _leaf("c_kinase"),
                _combine(CombineOp.UNION, _leaf("c_ms"), _leaf("c_derisi")),
            )
        )

        assert meeting_operator(structure, ["c_ms", "c_derisi"]) is CombineOp.UNION
        assert meeting_operator(structure, ["c_kinase", "c_ms"]) is CombineOp.INTERSECT

    def test_a_transform_between_the_leaves_and_the_combine_is_transparent(
        self,
    ) -> None:
        structure = SpecStructure(
            root=_combine(
                CombineOp.UNION,
                StructureNode(
                    kind="transform", criterion_id="c_ortho", inputs=[_leaf("c_ms")]
                ),
                _leaf("c_derisi"),
            )
        )

        assert meeting_operator(structure, ["c_ms", "c_derisi"]) is CombineOp.UNION

    def test_a_transform_above_the_meeting_combine_is_transparent(self) -> None:
        structure = SpecStructure(
            root=StructureNode(
                kind="transform",
                criterion_id="c_ortho",
                inputs=[_combine(CombineOp.UNION, _leaf("c_ms"), _leaf("c_derisi"))],
            )
        )

        assert meeting_operator(structure, ["c_ms", "c_derisi"]) is CombineOp.UNION

    def test_three_criteria_meet_at_the_combine_that_holds_them_all(self) -> None:
        structure = SpecStructure(
            root=_combine(
                CombineOp.INTERSECT,
                _combine(CombineOp.UNION, _leaf("c_ms"), _leaf("c_derisi")),
                _leaf("c_kinase"),
            )
        )

        assert (
            meeting_operator(structure, ["c_ms", "c_derisi", "c_kinase"])
            is CombineOp.INTERSECT
        )

    def test_an_absent_criterion_has_no_meeting_node(self) -> None:
        structure = SpecStructure(
            root=_combine(CombineOp.UNION, _leaf("c_ms"), _leaf("c_kinase"))
        )

        assert _meeting(structure, ["c_ms", "c_derisi"]) == ""

    def test_a_single_input_combine_passes_the_meeting_node_through(self) -> None:
        """A combine of one input builds to its input, so it decides nothing."""
        structure = SpecStructure(
            root=StructureNode(
                kind="combine",
                inputs=[_combine(CombineOp.UNION, _leaf("c_ms"), _leaf("c_derisi"))],
            )
        )

        assert meeting_operator(structure, ["c_ms", "c_derisi"]) is CombineOp.UNION


class TestCombinationViolation:
    def test_an_or_over_a_union_branch_is_no_violation(self) -> None:
        request = CombinationRequest(operator="OR", terms=["ms", "derisi"])
        structure = SpecStructure(
            root=_combine(CombineOp.UNION, _leaf("c_ms"), _leaf("c_derisi"))
        )

        assert _violation(request, ["c_ms", "c_derisi"], structure) == ""

    def test_an_or_the_tree_intersects_names_both_operators(self) -> None:
        request = CombinationRequest(
            operator="OR", terms=["mass spectrometry evidence", "DeRisi expression"]
        )
        structure = SpecStructure(
            root=_combine(CombineOp.INTERSECT, _leaf("c_ms"), _leaf("c_derisi"))
        )

        violation = combination_violation(request, ["c_ms", "c_derisi"], structure)

        assert violation is not None
        assert "mass spectrometry evidence OR DeRisi expression" in violation
        assert "UNION" in violation
        assert "INTERSECT" in violation

    def test_an_and_over_an_intersect_is_no_violation(self) -> None:
        request = CombinationRequest(operator="AND", terms=["ms", "derisi"])
        structure = SpecStructure(
            root=_combine(CombineOp.INTERSECT, _leaf("c_ms"), _leaf("c_derisi"))
        )

        assert _violation(request, ["c_ms", "c_derisi"], structure) == ""

    def test_criteria_that_never_meet_are_a_violation(self) -> None:
        request = CombinationRequest(operator="OR", terms=["ms", "derisi"])
        structure = SpecStructure(root=_leaf("c_ms"))

        violation = combination_violation(request, ["c_ms", "c_derisi"], structure)

        assert violation is not None
        assert "UNION" in violation

    def test_required_operator_maps_the_word_to_the_wdk_operator(self) -> None:
        assert required_operator("OR") is CombineOp.UNION
        assert required_operator("AND") is CombineOp.INTERSECT


def _requirement(value: str) -> Constraint:
    return Constraint(
        kind=ConstraintKind.COMBINATION,
        requested_value=value,
        label="how the evidence combines",
        source=ConstraintSource.USER_EXPLICIT,
    )


def _breach_message(
    requirements: list[Constraint],
    criteria: list[Criterion],
    structure: SpecStructure,
) -> str:
    """The first breach's message, empty when no requirement is breached."""
    breach = first_combination_violation(requirements, criteria, structure)
    return "" if breach is None else breach.message


class TestFirstCombinationViolation:
    def test_the_breach_carries_the_operator_the_request_needs(self) -> None:
        structure = SpecStructure(
            root=_combine(CombineOp.INTERSECT, _leaf("c_ms"), _leaf("c_derisi"))
        )

        breach = first_combination_violation(
            [_requirement("mass spectrometry evidence OR DeRisi expression")],
            _CRITERIA,
            structure,
        )

        assert breach is not None
        assert breach.required is CombineOp.UNION
        assert "INTERSECT" in breach.message

    def test_a_honored_requirement_is_no_breach(self) -> None:
        structure = SpecStructure(
            root=_combine(CombineOp.UNION, _leaf("c_ms"), _leaf("c_derisi"))
        )

        assert (
            _breach_message(
                [_requirement("mass spectrometry evidence OR DeRisi expression")],
                _CRITERIA,
                structure,
            )
            == ""
        )

    def test_a_mixed_operator_requirement_abstains(self) -> None:
        structure = SpecStructure(
            root=_combine(CombineOp.INTERSECT, _leaf("c_ms"), _leaf("c_derisi"))
        )

        assert (
            _breach_message(
                [_requirement("mass spectrometry OR DeRisi AND kinases")],
                _CRITERIA,
                structure,
            )
            == ""
        )

    def test_a_requirement_naming_no_criterion_abstains(self) -> None:
        structure = SpecStructure(
            root=_combine(CombineOp.INTERSECT, _leaf("c_ms"), _leaf("c_derisi"))
        )

        assert (
            _breach_message(
                [_requirement("proteomics OR microscopy")], _CRITERIA, structure
            )
            == ""
        )

    def test_a_requirement_of_another_kind_is_not_read(self) -> None:
        structure = SpecStructure(
            root=_combine(CombineOp.INTERSECT, _leaf("c_ms"), _leaf("c_derisi"))
        )
        other = Constraint(
            kind=ConstraintKind.OTHER,
            requested_value="mass spectrometry evidence OR DeRisi expression",
            label="note",
            source=ConstraintSource.USER_EXPLICIT,
        )

        assert _breach_message([other], _CRITERIA, structure) == ""


class TestDuplicateLeaves:
    """A duplicated leaf cannot stand in for a criterion that meets elsewhere."""

    def test_a_union_of_one_criterion_with_itself_is_not_the_meeting_node(
        self,
    ) -> None:
        tree = SpecStructure(
            root=_combine(
                CombineOp.INTERSECT,
                _combine(CombineOp.UNION, _leaf("c_ms"), _leaf("c_ms")),
                _leaf("c_derisi"),
            ),
        )
        assert meeting_operator(tree, ["c_ms", "c_derisi"]) is CombineOp.INTERSECT


class TestTermsOverlap:
    def test_two_statements_over_the_same_criteria_overlap(self) -> None:
        assert combination_terms_overlap(
            "mass spectrometry OR DeRisi expression",
            "mass spectrometry AND DeRisi expression",
        )

    def test_statements_over_different_criteria_do_not_overlap(self) -> None:
        assert not combination_terms_overlap(
            "mass spectrometry OR DeRisi expression",
            "kinase annotation AND phyletic profile",
        )

    def test_an_unparseable_statement_overlaps_nothing(self) -> None:
        assert not combination_terms_overlap(
            "mass spectrometry alongside DeRisi",
            "mass spectrometry OR DeRisi expression",
        )
