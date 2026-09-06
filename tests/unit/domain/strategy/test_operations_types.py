import pytest
from pydantic import TypeAdapter, ValidationError

from veupathdb.domain.parameters.values import StringValue
from veupathdb.domain.strategy.operations import (
    AddCombineOp,
    AddLeafOp,
    AddTransformOp,
    DeleteResolution,
    DeleteStepOp,
    GraphOperation,
    ReplaceSubtreeOp,
    UpdateCombineOperatorOp,
    UpdateStepMetaOp,
    UpdateStepParamsOp,
)

_ADAPTER: TypeAdapter[GraphOperation] = TypeAdapter(GraphOperation)


def _step_payload(step_id: str = "a") -> dict[str, str]:
    return {"id": step_id, "searchName": "geneById"}


class TestDiscriminatorParsing:
    def test_add_leaf_new_root(self) -> None:
        op = _ADAPTER.validate_python(
            {
                "kind": "addLeaf",
                "step": _step_payload(),
                "attach": {"mode": "new-root"},
            }
        )
        assert isinstance(op, AddLeafOp)
        assert op.attach.mode == "new-root"

    def test_add_leaf_into_slot(self) -> None:
        op = _ADAPTER.validate_python(
            {
                "kind": "addLeaf",
                "step": _step_payload(),
                "attach": {"mode": "into-slot", "targetStepId": "x", "slot": "primary"},
            }
        )
        assert isinstance(op, AddLeafOp)
        assert op.attach.mode == "into-slot"

    def test_add_combine(self) -> None:
        op = _ADAPTER.validate_python(
            {
                "kind": "addCombine",
                "step": {
                    "id": "c",
                    "searchName": "__combine__",
                    "operator": "INTERSECT",
                },
                "leftId": "a",
                "rightId": "b",
            }
        )
        assert isinstance(op, AddCombineOp)
        assert op.left_id == "a"
        assert op.right_id == "b"

    def test_add_transform(self) -> None:
        op = _ADAPTER.validate_python(
            {
                "kind": "addTransform",
                "step": _step_payload("t"),
                "inputId": "a",
                "mode": "before-consumer",
            }
        )
        assert isinstance(op, AddTransformOp)
        assert op.mode == "before-consumer"

    def test_delete_step_collapse_combine(self) -> None:
        op = _ADAPTER.validate_python(
            {"kind": "deleteStep", "stepId": "a", "resolution": "collapse-combine"}
        )
        assert isinstance(op, DeleteStepOp)
        assert op.resolution == DeleteResolution.COLLAPSE_COMBINE

    def test_delete_step_promote_primary(self) -> None:
        op = _ADAPTER.validate_python(
            {"kind": "deleteStep", "stepId": "c", "resolution": "promote-primary"}
        )
        assert isinstance(op, DeleteStepOp)
        assert op.resolution == DeleteResolution.PROMOTE_PRIMARY

    def test_delete_step_rejects_unknown_resolution(self) -> None:
        with pytest.raises(ValidationError):
            _ADAPTER.validate_python(
                {"kind": "deleteStep", "stepId": "a", "resolution": "vaporize"}
            )

    def test_delete_step_accepts_every_resolution_the_delete_dialog_offers(
        self,
    ) -> None:
        """Every resolution the delete dialog can build must round-trip.

        ``computeDeleteChoices`` on the frontend is the only producer; its
        counterpart test asserts it never emits a value outside this set.
        """
        for resolution in (
            "collapse-combine",
            "delete-subtree",
            "promote-primary",
            "delete-strategy",
        ):
            op = _ADAPTER.validate_python(
                {"kind": "deleteStep", "stepId": "a", "resolution": resolution}
            )
            assert isinstance(op, DeleteStepOp)
            assert op.resolution == resolution

    def test_replace_subtree(self) -> None:
        op = _ADAPTER.validate_python(
            {
                "kind": "replaceSubtree",
                "stepId": "old",
                "subtree": _step_payload("new"),
            }
        )
        assert isinstance(op, ReplaceSubtreeOp)
        assert op.subtree.id == "new"

    def test_update_step_params(self) -> None:
        op = _ADAPTER.validate_python(
            {
                "kind": "updateStepParams",
                "stepId": "a",
                "parameters": {"foo": {"type": "string", "value": "bar"}},
            }
        )
        assert isinstance(op, UpdateStepParamsOp)
        assert op.parameters == {"foo": StringValue(value="bar")}

    def test_update_combine_operator(self) -> None:
        op = _ADAPTER.validate_python(
            {
                "kind": "updateCombineOperator",
                "stepId": "c",
                "operator": "UNION",
                "colocationParams": None,
            }
        )
        assert isinstance(op, UpdateCombineOperatorOp)
        assert op.operator.value == "UNION"

    def test_update_step_meta(self) -> None:
        op = _ADAPTER.validate_python(
            {"kind": "updateStepMeta", "stepId": "a", "displayName": "renamed"}
        )
        assert isinstance(op, UpdateStepMetaOp)
        assert op.display_name == "renamed"
