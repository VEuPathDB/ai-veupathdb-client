"""AST node types for strategy representation (untyped tree)."""

from uuid import uuid4

from pydantic import Field, JsonValue, model_validator
from pydantic_core import PydanticCustomError

from veupathdb.domain.parameters.values import ParamValue
from veupathdb.domain.strategy.ops import ColocationParams, CombineOp
from veupathdb.json_types import JSONObject
from veupathdb.model import CamelModel

# Sentinel search names for non-search nodes in the step graph.
COMBINE_SEARCH_NAME = "__combine__"


def generate_step_id() -> str:
    """Generate a unique step ID."""
    return f"step_{uuid4().hex[:8]}"


class StepFilter(CamelModel):
    """One element of a WDK filter value array on a step."""

    name: str
    value: JsonValue = None
    disabled: bool = False

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, data: JsonValue) -> dict[str, JsonValue]:
        if not isinstance(data, dict):
            code = "step_filter_type"
            msg = "StepFilter requires a dict"
            raise PydanticCustomError(code, msg)
        name = data.get("name")
        if not isinstance(name, str) or not name:
            msg = "StepFilter requires a non-empty 'name'"
            raise ValueError(msg)
        return dict(data)


class StepAnalysis(CamelModel):
    """Analysis configuration attached to a step."""

    analysis_type: str
    parameters: JSONObject = Field(default_factory=dict)
    custom_name: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, data: JsonValue) -> dict[str, JsonValue]:
        if not isinstance(data, dict):
            code = "step_analysis_type"
            msg = "StepAnalysis requires a dict"
            raise PydanticCustomError(code, msg)
        result: dict[str, JsonValue] = dict(data)
        # Raw input arrives in either camelCase or snake_case.
        at = result.get("analysisType") or result.get("analysis_type")
        if not isinstance(at, str) or not at:
            msg = "StepAnalysis requires 'analysisType'"
            raise ValueError(msg)
        if not isinstance(result.get("parameters"), dict):
            result["parameters"] = {}
        cn = result.get("customName") or result.get("custom_name")
        if cn is not None and not isinstance(cn, str):
            result.pop("customName", None)
            result.pop("custom_name", None)
        return result


class StepReport(CamelModel):
    """Report request attached to a step."""

    report_name: str = "standard"
    config: JSONObject = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, data: JsonValue) -> dict[str, JsonValue]:
        if not isinstance(data, dict):
            code = "step_report_type"
            msg = "StepReport requires a dict"
            raise PydanticCustomError(code, msg)
        result: dict[str, JsonValue] = dict(data)
        if not isinstance(result.get("config"), dict):
            result["config"] = {}
        return result


class StrategyStepNode(CamelModel):
    """Recursive strategy node.

    The kind follows the structure: two inputs is a combine, one input is a
    transform, and no input is a search.
    """

    @model_validator(mode="before")
    @classmethod
    def _default_combine_search_name(cls, data: JsonValue) -> JsonValue:
        """Give a combine node the sentinel search name when it has none."""
        if not isinstance(data, dict):
            return data
        has_search = "searchName" in data or "search_name" in data
        has_both_inputs = ("primaryInput" in data or "primary_input" in data) and (
            "secondaryInput" in data or "secondary_input" in data
        )
        if not has_search and has_both_inputs:
            data["searchName"] = COMBINE_SEARCH_NAME
        return data

    search_name: str
    parameters: dict[str, ParamValue] = Field(default_factory=dict)

    primary_input: StrategyStepNode | None = None
    secondary_input: StrategyStepNode | None = None
    operator: CombineOp | None = None
    colocation_params: ColocationParams | None = None
    display_name: str | None = None
    filters: list[StepFilter] = Field(default_factory=list)
    analyses: list[StepAnalysis] = Field(default_factory=list)
    reports: list[StepReport] = Field(default_factory=list)
    wdk_weight: int | None = None
    # A saved sub-strategy reference is valid on combine steps only. It marks
    # the input subtree as a collapsed reference to that saved strategy.
    expanded_strategy_id: int | None = None
    expanded_name: str | None = None
    id: str = Field(default_factory=generate_step_id)

    @model_validator(mode="after")
    def _validate_structure(self) -> StrategyStepNode:
        if self.secondary_input is not None and self.primary_input is None:
            msg = "secondaryInput requires primaryInput"
            raise ValueError(msg)
        if self.secondary_input is not None and not self.operator:
            msg = "operator is required when secondaryInput is present"
            raise ValueError(msg)
        if (
            self.primary_input is not None
            and self.secondary_input is not None
            and self.primary_input.id == self.secondary_input.id
        ):
            msg = (
                f"combine step cannot use the same step on both inputs "
                f"(stepId={self.primary_input.id!r}); use a single leaf "
                f"or combine with a different step"
            )
            raise ValueError(msg)
        if self.operator == CombineOp.COLOCATE and self.colocation_params is None:
            msg = "colocationParams is required when operator is COLOCATE"
            raise ValueError(msg)
        if self.operator != CombineOp.COLOCATE and self.colocation_params is not None:
            msg = "colocationParams is only allowed when operator is COLOCATE"
            raise ValueError(msg)
        is_combine = self.primary_input is not None and self.secondary_input is not None
        if self.expanded_strategy_id is not None and not is_combine:
            msg = (
                "expandedStrategyId is only valid on combine steps "
                "(WDK requires the saved strategy to feed an input slot)"
            )
            raise ValueError(msg)
        if self.expanded_strategy_id is not None and not (
            self.expanded_name and self.expanded_name.strip()
        ):
            msg = (
                "expandedName is required when expandedStrategyId is set "
                "(WDK uses it as the visible label of the collapsed input)"
            )
            raise ValueError(msg)
        return self

    @property
    def primary_input_id(self) -> str | None:
        """The id in the primary slot, or ``None`` when the slot is empty."""
        return self.primary_input.id if self.primary_input is not None else None

    @property
    def secondary_input_id(self) -> str | None:
        """The id in the secondary slot, or ``None`` when the slot is empty."""
        return self.secondary_input.id if self.secondary_input is not None else None

    def inputs(self) -> list[StrategyStepNode]:
        """The steps this step consumes, in slot order, empty slots omitted."""
        return [
            node
            for node in (self.primary_input, self.secondary_input)
            if node is not None
        ]

    def input_ids(self) -> list[str]:
        """The ids of the steps this step consumes, in slot order."""
        return [node.id for node in self.inputs()]

    def infer_kind(self) -> str:
        if self.primary_input is not None and self.secondary_input is not None:
            return "combine"
        if self.search_name == COMBINE_SEARCH_NAME:
            return "combine"
        if self.primary_input is not None:
            return "transform"
        return "search"

    @property
    def display_label(self) -> str:
        """User-facing label. The sentinel search name never reaches the
        user."""
        if self.display_name:
            return self.display_name
        if self.search_name == COMBINE_SEARCH_NAME:
            return "Combine"
        return self.search_name
