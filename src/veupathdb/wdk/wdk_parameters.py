"""Models for WDK parameter types, as a union discriminated on the type field."""

from typing import Annotated, Literal

from pydantic import BaseModel, Discriminator, Field, JsonValue, field_validator
from pydantic.alias_generators import to_camel

from veupathdb.domain.parameters.specs import accepts_empty
from veupathdb.domain.parameters.stated import Stated, stated_reading
from veupathdb.domain.parameters.values import ParamKind
from veupathdb.domain.parameters.wdk_vocab import (
    WDKDatasetParser,
    WDKFilterOntologyTerm,
    WDKVocabulary,
)

_ORGANISM_ENTRIES = "highlightReferenceOrganisms"


class WDKBaseParameter(
    BaseModel,
    frozen=True,
    extra="ignore",
    alias_generator=to_camel,
    populate_by_name=True,
):
    """Fields common to all WDK parameter types.

    Subtype fields also appear here, so a reader needs no type narrowing.
    Concrete subtypes shadow them where the meaning differs.
    """

    name: str
    type: ParamKind
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

    @property
    def is_organism(self) -> bool:
        """True when the model highlights reference organisms among the entries."""
        return _ORGANISM_ENTRIES in self.properties.get("organismProperties", [])

    @property
    def required(self) -> bool:
        return not accepts_empty(self)

    @property
    def site_set(self) -> bool:
        return not self.is_visible or self.is_read_only

    @property
    def bindable(self) -> bool:
        return not self.site_set

    def stated_schema(self) -> dict[str, JsonValue]:
        return stated_reading(self).adapter.json_schema()

    def read_stated(self, raw: JsonValue) -> Stated:
        return stated_reading(self).read(raw)

    def stated_example(self) -> JsonValue:
        return stated_reading(self).example

    @field_validator("max_selected_count", mode="before")
    @classmethod
    def _normalize_unlimited(cls, v: object) -> object:
        """WDK sends a negative count for unlimited. Normalize it to None."""
        if isinstance(v, int) and v < 0:
            return None
        return v


class WDKStringParam(WDKBaseParameter, frozen=True):
    """WDK string parameter."""

    type: Literal["string"] = "string"
    length: int = 0
    is_multi_line: bool = False
    is_number: bool = False


class WDKNumberParam(WDKBaseParameter, frozen=True):
    """WDK number parameter."""

    type: Literal["number"] = "number"
    min: float | None = None
    max: float | None = None
    increment: float | None = None


class WDKNumberRangeParam(WDKBaseParameter, frozen=True):
    """WDK number range parameter."""

    type: Literal["number-range"] = "number-range"
    min: float | None = None
    max: float | None = None
    increment: float | None = None


class WDKDateParam(WDKBaseParameter, frozen=True):
    """WDK date parameter."""

    type: Literal["date"] = "date"
    min_date: str | None = None
    max_date: str | None = None


class WDKDateRangeParam(WDKBaseParameter, frozen=True):
    """WDK date range parameter."""

    type: Literal["date-range"] = "date-range"
    min_date: str | None = None
    max_date: str | None = None


class WDKTimestampParam(WDKBaseParameter, frozen=True):
    """WDK timestamp parameter."""

    type: Literal["timestamp"] = "timestamp"


class WDKAnswerParam(WDKBaseParameter, frozen=True):
    """WDK step-input parameter."""

    type: Literal["input-step"] = "input-step"
    allow_empty_value: bool = True


class WDKDatasetParam(WDKBaseParameter, frozen=True):
    """WDK dataset parameter."""

    type: Literal["input-dataset"] = "input-dataset"
    default_id_list: str | None = None
    record_class_name: str | None = None
    parsers: list[WDKDatasetParser] = Field(default_factory=list)


class WDKEnumParam(WDKBaseParameter, frozen=True):
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


class WDKFilterParam(WDKBaseParameter, frozen=True):
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
