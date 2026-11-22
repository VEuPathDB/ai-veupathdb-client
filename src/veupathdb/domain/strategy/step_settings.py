from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

from veupathdb.domain.parameters.value_equality import same_param_value
from veupathdb.domain.parameters.values import ParamValue, value_kind
from veupathdb.domain.strategy.ast import StepFilter, StrategyStepNode
from veupathdb.domain.strategy.graph_model import StrategyStep
from veupathdb.domain.strategy.ops import ColocationParams, CombineOp
from veupathdb.model import CamelModel


class StepSettings(CamelModel):
    model_config = ConfigDict(frozen=True)

    search_name: str | None = None
    parameters: dict[str, ParamValue] = Field(default_factory=dict)
    operator: CombineOp | None = None
    colocation_params: ColocationParams | None = None
    filters: list[StepFilter] = Field(default_factory=list)
    wdk_weight: int | None = None
    expanded_strategy_id: int | None = None
    expanded_name: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _a_combine_names_no_search(cls, data: object) -> Mapping[str, object]:
        match data:
            case Mapping() if data.get("operator") is None:
                return data
            case Mapping():
                return {
                    k: v
                    for k, v in data.items()
                    if k not in {"search_name", "searchName"}
                }
            case _:
                code = "step_settings_type"
                msg = "StepSettings reads a mapping; use settings_of for a step"
                raise PydanticCustomError(code, msg)

    def changed(self, other: StepSettings) -> list[str]:
        return self._fields_that_differ(
            other,
            parameters_differ=not _same_parameters(self.parameters, other.parameters),
            filters_differ=_by_name(self.filters) != _by_name(other.filters),
        )

    def filters_wdk_added(self, stated: StepSettings) -> list[StepFilter]:
        named = _by_name(stated.filters)
        return [f for name, f in _by_name(self.filters).items() if name not in named]

    def departures_from(
        self,
        before: StepSettings,
        after: StepSettings,
        *,
        wdk_added: Sequence[StepFilter],
    ) -> list[str]:
        held = _by_name(self.filters)
        defaults = _by_name(list(wdk_added))
        stated = _by_name(after.filters)
        removed = _by_name(before.filters).keys() - stated.keys()
        return self._fields_that_differ(
            after,
            parameters_differ=False,
            filters_differ=any(held.get(name) != f for name, f in stated.items())
            or any(held.get(name) != defaults.get(name) for name in removed),
        )

    def filters_to_put(
        self, before: StepSettings, after: StepSettings
    ) -> list[StepFilter]:
        stated = _by_name(after.filters)
        dropped = _by_name(before.filters).keys() - stated.keys()
        held = _by_name(self.filters)
        kept = [stated.get(name, f) for name, f in held.items() if name not in dropped]
        return kept + [f for name, f in stated.items() if name not in held]

    def _fields_that_differ(
        self, other: StepSettings, *, parameters_differ: bool, filters_differ: bool
    ) -> list[str]:
        judged = {"parameters": parameters_differ, "filters": filters_differ}
        mine, theirs = dict(self), dict(other)
        return [
            name
            for name in type(self).model_fields
            if (judged[name] if name in judged else mine[name] != theirs[name])
        ]


def _same_parameters(left: dict[str, ParamValue], right: dict[str, ParamValue]) -> bool:
    return left.keys() == right.keys() and all(
        same_param_value(
            name, value_kind(value) or value_kind(right[name]), value, right[name]
        )
        for name, value in left.items()
    )


def _by_name(filters: list[StepFilter]) -> dict[str, StepFilter]:
    first: dict[str, StepFilter] = {}
    for f in filters:
        first.setdefault(f.name, f)
    return first


_SETTINGS = frozenset(StepSettings.model_fields)


def settings_of(step: StrategyStep | StrategyStepNode) -> StepSettings:
    return StepSettings.model_validate(step.model_dump(include=set(_SETTINGS)))
