"""What changed between the spec a turn started with and the spec it produced.

An edit turn's reply claimed criteria were preserved from prose. The claim is a
comparison, so it is computed here and nowhere else.
"""

from __future__ import annotations

from veupathdb.domain.parameters.values import (
    MultiPickValue,
    NumberValue,
    ParamValue,
)
from veupathdb.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from veupathdb.domain.strategy.ops import CombineOp
from veupathdb.domain.strategy.spec_diff import SpecDiff, diff_specs


def _criterion(cid: str, **params: ParamValue) -> Criterion:
    return Criterion(
        id=cid,
        text=f"criterion {cid}",
        search_name=f"By{cid}",
        resolved_params=dict(params),
    )


def _spec(*criteria: Criterion) -> OperationalSpec:
    return OperationalSpec(
        goal="find kinases",
        criteria=list(criteria),
        structure=SpecStructure(
            root=StructureNode(
                kind="combine",
                operator=CombineOp.INTERSECT,
                inputs=[
                    StructureNode(kind="leaf", criterion_id=c.id) for c in criteria
                ],
            )
        ),
    )


def _three() -> OperationalSpec:
    return _spec(
        _criterion("text"),
        _criterion("go", organism=MultiPickValue(values=["Plasmodium"])),
        _criterion("expr", min_expression_percentile=NumberValue(value=80)),
    )


def _disposition(result: SpecDiff, criterion_id: str) -> str:
    return next(c.disposition for c in result.changes if c.criterion_id == criterion_id)


class TestTheDiffNamesWhatHappened:
    def test_identical_specs_are_all_kept(self) -> None:
        result = diff_specs(_three(), _three())

        assert [c.disposition for c in result.changes] == ["kept", "kept", "kept"]
        assert result.structure_changed is False

    def test_diff_reports_a_dropped_criterion(self) -> None:
        after = _spec(_criterion("text"), _criterion("go"))

        result = diff_specs(_three(), after)

        assert _disposition(result, "expr") == "dropped"

    def test_diff_reports_a_changed_param(self) -> None:
        before = _three()
        after = _spec(
            _criterion("text"),
            _criterion("go", organism=MultiPickValue(values=["Plasmodium"])),
            _criterion("expr", min_expression_percentile=NumberValue(value=90)),
        )

        result = diff_specs(before, after)

        change = next(c for c in result.changes if c.criterion_id == "expr")
        assert change.disposition == "changed"
        assert change.changed_params == {"min_expression_percentile": "90"}

    def test_diff_reports_an_added_criterion(self) -> None:
        after = _spec(
            _criterion("text"),
            _criterion("go", organism=MultiPickValue(values=["Plasmodium"])),
            _criterion("expr", min_expression_percentile=NumberValue(value=80)),
            _criterion("tm"),
        )

        result = diff_specs(_three(), after)

        assert _disposition(result, "tm") == "added"

    def test_a_changed_search_is_a_change_with_no_changed_params(self) -> None:
        before = _spec(_criterion("text"))
        after_criterion = _criterion("text")
        after_criterion.search_name = "GenesByTextSomethingElse"

        result = diff_specs(before, _spec(after_criterion))

        change = result.changes[0]
        assert change.disposition == "changed"
        assert change.changed_params == {}

    def test_a_removed_param_is_a_change(self) -> None:
        before = _spec(_criterion("go", organism=MultiPickValue(values=["Pf3D7"])))

        result = diff_specs(before, _spec(_criterion("go")))

        assert result.changes[0].disposition == "changed"

    def test_a_narrowed_organism_is_a_change(self) -> None:
        before = _spec(_criterion("go", organism=MultiPickValue(values=["Plasmodium"])))
        after = _spec(
            _criterion(
                "go", organism=MultiPickValue(values=["Plasmodium falciparum 3D7"])
            )
        )

        result = diff_specs(before, after)

        change = result.changes[0]
        assert change.disposition == "changed"
        assert change.changed_params == {
            "organism": '["Plasmodium falciparum 3D7"]',
        }


class TestTheStructure:
    def test_an_identical_structure_is_unchanged(self) -> None:
        assert diff_specs(_three(), _three()).structure_changed is False

    def test_a_different_operator_changes_the_structure(self) -> None:
        after = _three()
        assert after.structure is not None
        after.structure.root.operator = CombineOp.UNION

        assert diff_specs(_three(), after).structure_changed is True

    def test_a_missing_structure_on_one_side_changes_it(self) -> None:
        after = _three()
        after.structure = None

        assert diff_specs(_three(), after).structure_changed is True


class TestTheCounts:
    def test_a_structure_change_is_one_touch(self) -> None:
        """A rewire changes the result set, so the turn touched the strategy."""
        after = _three()
        assert after.structure is not None
        after.structure.root.operator = CombineOp.UNION

        assert diff_specs(_three(), after).touched_count() == 1

    def test_an_untouched_spec_counts_no_touch(self) -> None:
        assert diff_specs(_three(), _three()).touched_count() == 0

    def test_a_rewired_structure_is_named_in_the_render(self) -> None:
        after = _three()
        assert after.structure is not None
        after.structure.root.operator = CombineOp.UNION

        assert diff_specs(_three(), after).render() == (
            "kept 3, changed 0, added 0, dropped 0, structure rewired"
        )

    def test_an_unrewired_render_says_nothing_about_the_structure(self) -> None:
        assert diff_specs(_three(), _three()).render() == (
            "kept 3, changed 0, added 0, dropped 0"
        )

    def test_the_counts_summarize_the_dispositions(self) -> None:
        after = _spec(
            _criterion("text"),
            _criterion("go", organism=MultiPickValue(values=["Pvivax"])),
            _criterion("tm"),
        )

        result = diff_specs(_three(), after)

        assert result.kept_count == 1
        assert result.changed_count == 1
        assert result.dropped_count == 1
        assert result.added_count == 1
