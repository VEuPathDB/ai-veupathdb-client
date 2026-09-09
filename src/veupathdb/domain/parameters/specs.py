"""Domain parameter specifications: pure types, no I/O."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from veupathdb.domain.parameters.value_codec import as_param_kind, from_decoded
from veupathdb.domain.parameters.values import ParamValue
from veupathdb.domain.parameters.wdk_vocab import WDKVocabulary


@dataclass(frozen=True)
class ParamSpecNormalized:
    """Canonical representation of a WDK parameter spec."""

    name: str
    param_type: str
    allow_empty_value: bool = False
    min_selected_count: int | None = None
    max_selected_count: int | None = None
    vocabulary: WDKVocabulary | None = None
    count_only_leaves: bool = False
    is_number: bool = False
    min: float | None = None
    max: float | None = None
    min_date: str | None = None
    max_date: str | None = None
    increment: float | None = None
    max_length: int | None = None
    display_type: str = ""
    is_visible: bool = True
    group: str = ""
    dependent_params: tuple[str, ...] = ()
    help: str | None = None
    initial_display_value: str | None = None


def find_input_step_param(specs: dict[str, ParamSpecNormalized]) -> str | None:
    for spec in specs.values():
        if spec.param_type == "input-step":
            return spec.name
    return None


def topological_fill_order(specs: dict[str, ParamSpecNormalized]) -> list[str]:
    """Sort param names so that a parent comes before the params it controls.

    A cycle falls back to lexical order.
    """
    depends_on: dict[str, list[str]] = {}
    controls: dict[str, list[str]] = {name: [] for name in specs}
    for name, spec in specs.items():
        for dep in spec.dependent_params:
            controls.setdefault(name, []).append(dep)
            depends_on.setdefault(dep, []).append(name)
    in_degree = {name: len(depends_on.get(name, [])) for name in specs}
    queue = [n for n in specs if in_degree[n] == 0]
    fill: list[str] = []
    while queue:
        node = queue.pop(0)
        fill.append(node)
        for child in controls.get(node, []):
            if child in in_degree:
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)
    fill.extend(n for n in specs if n not in fill)
    return fill


def _is_hidden_required_fill(spec: ParamSpecNormalized) -> bool:
    """Whether this parameter is one the client supplies on the caller's behalf."""
    return (
        not spec.is_visible
        and not spec.allow_empty_value
        and spec.initial_display_value is not None
    )


def filled_hidden_defaults(
    param_specs: dict[str, ParamSpecNormalized],
    parameters: Mapping[str, ParamValue],
) -> list[str]:
    """The hidden parameters a fill would supply, so the caller can report them.

    A filled default is otherwise indistinguishable from a value someone chose,
    and a default carries no promise of returning rows.
    """
    return sorted(
        name
        for name, spec in param_specs.items()
        if name not in parameters and _is_hidden_required_fill(spec)
    )


def fill_hidden_required_defaults(
    param_specs: dict[str, ParamSpecNormalized],
    parameters: Mapping[str, ParamValue],
) -> dict[str, ParamValue]:
    """Fill hidden required params from their fixed ``initial_display_value``.

    WDK rejects a search without these params, but the model cannot set them.
    Visible required params are never auto-filled.
    """
    filled: dict[str, ParamValue] = dict(parameters)
    for name, spec in param_specs.items():
        if name not in filled and _is_hidden_required_fill(spec):
            filled[name] = from_decoded(
                as_param_kind(spec.param_type), spec.initial_display_value
            )
    return filled
