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
    is_read_only: bool = False
    group: str = ""
    dependent_params: tuple[str, ...] = ()
    help: str | None = None
    initial_display_value: str | None = None

    @property
    def required(self) -> bool:
        return not self.allow_empty_value or (
            self.min_selected_count is not None and self.min_selected_count >= 1
        )

    @property
    def site_set(self) -> bool:
        return not self.is_visible or self.is_read_only

    @property
    def bindable(self) -> bool:
        return not self.site_set


def find_input_step_param(specs: dict[str, ParamSpecNormalized]) -> str | None:
    for spec in specs.values():
        if spec.param_type == "input-step":
            return spec.name
    return None


def _is_site_set_required_fill(spec: ParamSpecNormalized) -> bool:
    return spec.site_set and spec.required and spec.initial_display_value is not None


def filled_site_set_defaults(
    param_specs: dict[str, ParamSpecNormalized],
    parameters: Mapping[str, ParamValue],
) -> list[str]:
    """The site-set parameters a fill would supply, so the caller can report them.

    A filled default is otherwise indistinguishable from a value someone chose,
    and a default carries no promise of returning rows.
    """
    return sorted(
        name
        for name, spec in param_specs.items()
        if name not in parameters and _is_site_set_required_fill(spec)
    )


def fill_site_set_defaults(
    param_specs: dict[str, ParamSpecNormalized],
    parameters: Mapping[str, ParamValue],
) -> dict[str, ParamValue]:
    """Fill site-set required params from their fixed ``initial_display_value``.

    WDK rejects a search without these params, but the caller cannot set them.
    Bindable required params are never auto-filled.
    """
    filled: dict[str, ParamValue] = dict(parameters)
    for name, spec in param_specs.items():
        if name not in filled and _is_site_set_required_fill(spec):
            filled[name] = from_decoded(
                as_param_kind(spec.param_type), spec.initial_display_value
            )
    return filled
