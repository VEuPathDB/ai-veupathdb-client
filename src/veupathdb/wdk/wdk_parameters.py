"""Models for WDK parameter types, as a union discriminated on the type field."""

from typing import Annotated, Literal

from pydantic import Discriminator, Field, field_validator

from veupathdb.domain.parameters.wdk_vocab import (
    WDKDatasetParser,
    WDKFilterOntologyTerm,
    WDKVocabulary,
)
from veupathdb.wdk.wdk_base import WDKModel


class WDKBaseParameter(WDKModel):
    """Fields common to all WDK parameter types.

    Subtype fields also appear here, so a reader needs no type narrowing.
    Concrete subtypes shadow them where the meaning differs.
    """

    name: str
    display_name: str = ""
    help: str | None = None
    is_visible: bool = True
    group: str = ""
    is_read_only: bool = False
    allow_empty_value: bool = False
    visible_help: str | None = None
    visible_help_position: str | None = None
    dependent_params: list[str] = Field(default_factory=list)
    initial_display_value: str | None = None
    properties: dict[str, list[str]] = Field(default_factory=dict)

    vocabulary: WDKVocabulary | None = None
    count_only_leaves: bool = False
    display_type: str = ""
    min_selected_count: int = 0
    max_selected_count: int | None = None
    min: float | None = None
    max: float | None = None
    min_date: str | None = None
    max_date: str | None = None
    increment: float | None = None
    length: int = 0
    is_number: bool = False

    # Filter-only fields.
    ontology: list[WDKFilterOntologyTerm] = Field(default_factory=list)
    values: dict[str, list[str]] | None = None
    filter_data_type_display_name: str | None = None

    # Dataset-only fields.
    default_id_list: str | None = None
    record_class_name: str | None = None
    parsers: list[WDKDatasetParser] = Field(default_factory=list)

    @field_validator("max_selected_count", mode="before")
    @classmethod
    def _normalize_unlimited(cls, v: object) -> object:
        """WDK sends a negative count for unlimited. Normalize it to None."""
        if isinstance(v, int) and v < 0:
            return None
        return v


class WDKStringParam(WDKBaseParameter):
    """WDK string parameter."""

    type: Literal["string"] = "string"
    length: int = 0
    is_multi_line: bool = False
    is_number: bool = False


class WDKNumberParam(WDKBaseParameter):
    """WDK number parameter."""

    type: Literal["number"] = "number"
    min: float | None = None
    max: float | None = None
    increment: float | None = None


class WDKNumberRangeParam(WDKBaseParameter):
    """WDK number range parameter."""

    type: Literal["number-range"] = "number-range"
    min: float | None = None
    max: float | None = None
    increment: float | None = None


class WDKDateParam(WDKBaseParameter):
    """WDK date parameter."""

    type: Literal["date"] = "date"
    min_date: str | None = None
    max_date: str | None = None


class WDKDateRangeParam(WDKBaseParameter):
    """WDK date range parameter."""

    type: Literal["date-range"] = "date-range"
    min_date: str | None = None
    max_date: str | None = None


class WDKTimestampParam(WDKBaseParameter):
    """WDK timestamp parameter."""

    type: Literal["timestamp"] = "timestamp"


class WDKAnswerParam(WDKBaseParameter):
    """WDK step-input parameter."""

    type: Literal["input-step"] = "input-step"


class WDKDatasetParam(WDKBaseParameter):
    """WDK dataset parameter."""

    type: Literal["input-dataset"] = "input-dataset"
    default_id_list: str | None = None
    record_class_name: str | None = None
    parsers: list[WDKDatasetParser] = Field(default_factory=list)


class WDKEnumParam(WDKBaseParameter):
    """WDK enum parameter, single-pick or multi-pick.

    The display type is a second discriminator. It sets the vocabulary shape.
    """

    type: Literal["single-pick-vocabulary", "multi-pick-vocabulary"]
    display_type: str = ""
    max_selected_count: int | None = None
    min_selected_count: int = 0
    vocabulary: WDKVocabulary | None = None
    count_only_leaves: bool = False
    depth_expanded: int = 0


class WDKFilterParam(WDKBaseParameter):
    """WDK filter parameter."""

    type: Literal["filter"] = "filter"
    min_selected_count: int = 0
    ontology: list[WDKFilterOntologyTerm] = Field(default_factory=list)
    values: dict[str, list[str]] | None = None
    filter_data_type_display_name: str | None = None
    hide_empty_ontology_nodes: bool = False
    sort_leaves_before_branches: bool = False
    count_predicts_answer_count: bool = False


WDKParameter = Annotated[
    WDKStringParam
    | WDKNumberParam
    | WDKNumberRangeParam
    | WDKDateParam
    | WDKDateRangeParam
    | WDKTimestampParam
    | WDKEnumParam
    | WDKFilterParam
    | WDKDatasetParam
    | WDKAnswerParam,
    Discriminator("type"),
]
"""Discriminated union of all WDK parameter types."""
