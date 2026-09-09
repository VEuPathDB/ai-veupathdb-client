"""Pydantic models for WDK REST API responses.

Python field names are snake_case; the camelCase keys in WDK JSON come from
the alias generator.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import ConfigDict, Discriminator, Field, JsonValue, field_validator
from pydantic.alias_generators import to_camel

from veupathdb.domain.parameters.values import ParamValue
from veupathdb.domain.strategy.ops import BooleanOperator
from veupathdb.domain.strategy.validation import StepValidation
from veupathdb.domain.wdk_values import (
    WDKHistogramBin,
    WDKHistogramStatistics,
    WDKRecordIdPart,
    WDKSortDirection,
)
from veupathdb.json_types import JSONObject
from veupathdb.model import CamelModel
from veupathdb.wdk.value_decoding import encode_params
from veupathdb.wdk.wdk_base import WDKModel
from veupathdb.wdk.wdk_parameters import WDKParameter


def encode_wdk_params(params: dict[str, ParamValue] | None) -> dict[str, str]:
    if params is None:
        return {}
    return encode_params(params)


class WDKFilterValue(WDKModel):
    """A single filter entry in SearchConfig."""

    name: str
    value: JsonValue = None
    disabled: bool = False


class WDKSearchConfig(WDKModel):
    """Search configuration: parameters, filters, and weight.

    Parameter values are never None.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="ignore",
        frozen=True,
        coerce_numbers_to_str=True,
    )

    parameters: dict[str, str] = Field(default_factory=dict)
    filters: list[WDKFilterValue] = Field(default_factory=list)
    view_filters: list[WDKFilterValue] = Field(default_factory=list)
    column_filters: JSONObject | None = None
    wdk_weight: int = 0


class WDKStepTree(WDKModel):
    """Recursive step tree structure."""

    step_id: int
    primary_input: WDKStepTree | None = None
    secondary_input: WDKStepTree | None = None


class WDKDisplayPreferences(WDKModel):
    """Step display preferences (column selection, sorting)."""

    column_selection: list[str] | None = None
    sort_columns: list[JSONObject] | None = None


def _size_or_none(value: object) -> object:
    """A negative size is the absence of a count. Zero is a real result."""
    if isinstance(value, int) and value < 0:
        return None
    return value


class WDKStep(WDKModel):
    """A WDK step (search execution unit)."""

    id: int
    search_name: str
    search_config: WDKSearchConfig
    record_class_name: str | None = None
    validation: StepValidation | None = None
    estimated_size: int | None = None
    strategy_id: int | None = None

    _no_negative_size = field_validator("estimated_size", mode="before")(_size_or_none)
    display_name: str = ""
    short_display_name: str = ""
    custom_name: str | None = None
    base_custom_name: str | None = None
    expanded: bool = False
    expanded_name: str | None = None
    is_filtered: bool = False
    description: str = ""
    owner_id: int = 0
    has_complete_step_analyses: bool = False
    display_preferences: WDKDisplayPreferences = Field(
        default_factory=WDKDisplayPreferences,
    )
    created_time: str = ""
    last_run_time: str = ""


class WDKStrategySummary(WDKModel):
    """Strategy summary (from list endpoint)."""

    strategy_id: int
    name: str
    root_step_id: int
    record_class_name: str | None = None
    signature: str = ""
    is_saved: bool = False
    is_valid: bool = True
    is_public: bool = False
    is_deleted: bool = False
    is_example: bool = False
    estimated_size: int | None = None
    description: str = ""
    author: str = ""
    organization: str = ""
    created_time: str = ""
    last_modified: str = ""
    last_viewed: str = ""
    release_version: str = ""
    name_of_first_step: str = ""
    leaf_and_transform_step_count: int = 0
    validation: StepValidation | None = None


class WDKStrategyDetails(WDKStrategySummary):
    """Full strategy details (from detail endpoint)."""

    step_tree: WDKStepTree
    steps: dict[str, WDKStep] = Field(default_factory=dict)


class WDKIdentifier(WDKModel):
    """Generic WDK ``{"id": <int>}`` response from resource-creating POSTs."""

    id: int


class WDKSortSpec(WDKModel):
    """Sorting specification (matches monorepo AttributeSortingSpec)."""

    attribute_name: str
    direction: WDKSortDirection = "ASC"


class WDKReporter(WDKModel):
    """WDK report format definition (matches wdk-client Reporter)."""

    name: str
    type: str = ""
    display_name: str = ""
    description: str = ""
    is_in_report: bool = False
    scopes: list[str] = Field(default_factory=list)


class WDKAttributeField(WDKModel):
    """WDK attribute field metadata, from expanded record-type responses."""

    name: str
    display_name: str = ""
    help: str | None = None
    type: str | None = None
    is_sortable: bool = False
    is_removable: bool = False
    is_displayable: bool = True
    is_in_report: bool = False
    truncate_to: int = 0
    formats: list[WDKReporter] = Field(default_factory=list)
    properties: dict[str, list[str]] = Field(default_factory=dict)


class WDKParameterGroup(WDKModel):
    """Parameter group metadata."""

    name: str
    display_name: str = ""
    description: str = ""
    is_visible: bool = True
    display_type: str = ""
    parameters: list[str] = Field(default_factory=list)


class WDKSearch(WDKModel):
    """WDK search/question definition."""

    url_segment: str
    full_name: str = ""
    display_name: str = ""
    short_display_name: str = ""
    description: str = ""
    summary: str = ""
    output_record_class_name: str = ""
    is_analyzable: bool = False
    is_cacheable: bool = True
    param_names: list[str] = Field(default_factory=list)
    groups: list[WDKParameterGroup] = Field(default_factory=list)
    parameters: list[WDKParameter] | None = None
    default_attributes: list[str] = Field(default_factory=list)
    default_sorting: list[WDKSortSpec] = Field(default_factory=list)
    filters: list[JSONObject] = Field(default_factory=list)
    properties: dict[str, list[str]] = Field(default_factory=dict)
    allowed_primary_input_record_class_names: list[str] | None = None
    allowed_secondary_input_record_class_names: list[str] | None = None
    new_build: str = ""
    revise_build: str = ""
    query_name: str = ""
    no_summary_on_single_record: bool = False
    dynamic_attributes: list[WDKAttributeField] = Field(default_factory=list)
    default_summary_view: str = "_default"
    summary_view_plugins: list[JSONObject] = Field(default_factory=list)
    icon_name: str | None = None
    help: str | None = None
    search_visible_help: str | None = None


class WDKSearchResponse(WDKModel):
    """Envelope for single-search detail endpoint."""

    search_data: WDKSearch
    validation: StepValidation


class WDKRecordType(WDKModel):
    """WDK record type metadata.

    A deployment returns attribute metadata as ``attributes`` or as
    ``attributesMap``.
    """

    url_segment: str
    full_name: str = ""
    display_name: str = ""
    display_name_plural: str = ""
    short_display_name: str = ""
    description: str = ""
    record_id_attribute_name: str = ""
    primary_key_column_refs: list[str] = Field(default_factory=list)
    use_basket: bool = False
    has_all_records_query: bool = False
    properties: dict[str, list[str]] = Field(default_factory=dict)
    searches: list[WDKSearch] | None = None
    icon_name: str | None = None
    attributes: list[WDKAttributeField] | None = None
    attributes_map: dict[str, WDKAttributeField] | None = None


class WDKAnswerMeta(WDKModel):
    """Answer metadata. Only the view pair reflects the view filters."""

    total_count: int | None = None
    response_count: int = 0
    display_total_count: int | None = None
    view_total_count: int | None = None
    display_view_total_count: int | None = None
    record_class_name: str = ""
    attributes: list[str] = Field(default_factory=list)
    tables: list[str] = Field(default_factory=list)

    def records_returned(self) -> int:
        """The count describing the records this answer carries.

        Raises when WDK published none; zero would state a result nobody measured.
        """
        for count in (
            self.display_view_total_count,
            self.view_total_count,
            self.display_total_count,
            self.total_count,
        ):
            if count is not None:
                return count
        msg = "WDK answer carries no result count"
        raise ValueError(msg)


class WDKLinkAttribute(WDKModel):
    """A link attribute value: the text a reader sees, and where it points."""

    url: str = ""
    display_text: str = ""


class WDKRecordInstance(WDKModel):
    """A single record from a WDK answer/report.

    ``record_class_name`` is the full name here; ``WDKAnswerMeta`` carries the
    url segment under the same key.
    """

    display_name: str = ""
    id: list[WDKRecordIdPart] = Field(default_factory=list)
    record_class_name: str = ""
    attributes: dict[str, JsonValue] = Field(default_factory=dict)
    tables: dict[str, JsonValue] = Field(default_factory=dict)
    table_errors: list[str] = Field(default_factory=list)

    def attribute_text(self, name: str) -> str | None:
        """The comparable text of one attribute.

        A link attribute arrives as an object, so a direct comparison against a
        string never matches.
        """
        match self.attributes.get(name):
            case None:
                return None
            case {**fields}:
                return WDKLinkAttribute.model_validate(fields).display_text or None
            case value:
                return str(value)


class WDKAnswer(WDKModel):
    """WDK answer/report response."""

    meta: WDKAnswerMeta
    records: list[WDKRecordInstance] = Field(default_factory=list)


class WDKStepAnalysisType(WDKModel):
    """Step analysis type definition (from ``GET .../step-analyses/types``)."""

    name: str
    display_name: str
    short_description: str = ""
    description: str = ""
    release_version: str = ""
    custom_thumbnail: str | None = None
    param_names: list[str] = Field(default_factory=list)
    groups: list[WDKParameterGroup] = Field(default_factory=list)
    parameters: list[WDKParameter] | None = None


class WDKStepAnalysisTypeResponse(WDKModel):
    """Envelope for the single analysis-type detail endpoint."""

    search_data: WDKStepAnalysisType
    validation: StepValidation


WDKAnalysisStatus = Literal[
    "CREATED",
    "STEP_REVISED",
    "INVALID",
    "PENDING",
    "RUNNING",
    "COMPLETE",
    "INTERRUPTED",
    "ERROR",
    "EXPIRED",
    "OUT_OF_DATE",
    "UNKNOWN",
]


class WDKStepAnalysisSummary(WDKModel):
    """One entry of the step-analyses list.

    The listing endpoint emits an id and a display name, which is a smaller
    shape than the instance the create and detail endpoints return.
    """

    analysis_id: int
    display_name: str = ""


class WDKStepAnalysisConfig(WDKModel):
    """Step analysis instance configuration."""

    analysis_id: int
    step_id: int
    analysis_name: str
    display_name: str = ""
    short_description: str | None = None
    description: str | None = None
    user_notes: str | None = None
    status: WDKAnalysisStatus = "CREATED"
    parameters: dict[str, str] = Field(default_factory=dict)
    validation: StepValidation | None = None


class WDKAnalysisStatusResponse(WDKModel):
    """Response from GET .../analyses/{id}/result/status."""

    status: WDKAnalysisStatus


class WDKColumnDistribution(WDKModel):
    """Response from POST .../columns/{col}/reports/byValue."""

    histogram: list[WDKHistogramBin] = Field(default_factory=list)
    statistics: WDKHistogramStatistics = Field(default_factory=WDKHistogramStatistics)


class WDKTemporaryResult(WDKModel):
    """Response from POST /temporary-results."""

    id: str


class WDKUserProperties(WDKModel):
    """The profile fields nested under ``properties`` of a user record."""

    first_name: str | None = None
    last_name: str | None = None


class WDKUserInfo(WDKModel):
    """WDK user profile (from ``GET /users/current``)."""

    id: int
    email: str | None = None
    is_guest: bool = True
    properties: WDKUserProperties = Field(default_factory=WDKUserProperties)


# Dataset config: discriminated union over the source types.


class WDKDatasetIdListContent(WDKModel):
    """Content for ``sourceType: "idList"``."""

    ids: list[str]


class WDKDatasetBasketContent(WDKModel):
    """Content for ``sourceType: "basket"``."""

    basket_name: str


class WDKDatasetFileContent(WDKModel):
    """Content for ``sourceType: "file"``."""

    temporary_file_id: str
    parser: str
    search_name: str
    parameter_name: str


class WDKDatasetStrategyContent(WDKModel):
    """Content for ``sourceType: "strategy"``."""

    strategy_id: int


class WDKDatasetUrlContent(WDKModel):
    """Content for ``sourceType: "url"``."""

    url: str
    parser: str
    search_name: str
    parameter_name: str


class WDKDatasetConfigIdList(WDKModel):
    """Dataset config with id-list source."""

    source_type: Literal["idList"]
    source_content: WDKDatasetIdListContent


class WDKDatasetConfigBasket(WDKModel):
    """Dataset config with basket source."""

    source_type: Literal["basket"]
    source_content: WDKDatasetBasketContent


class WDKDatasetConfigFile(WDKModel):
    """Dataset config with file source."""

    source_type: Literal["file"]
    source_content: WDKDatasetFileContent


class WDKDatasetConfigStrategy(WDKModel):
    """Dataset config with strategy source."""

    source_type: Literal["strategy"]
    source_content: WDKDatasetStrategyContent


class WDKDatasetConfigUrl(WDKModel):
    """Dataset config with URL source."""

    source_type: Literal["url"]
    source_content: WDKDatasetUrlContent


WDKDatasetConfig = Annotated[
    WDKDatasetConfigIdList
    | WDKDatasetConfigBasket
    | WDKDatasetConfigFile
    | WDKDatasetConfigStrategy
    | WDKDatasetConfigUrl,
    Discriminator("source_type"),
]
"""Discriminated union of WDK dataset config source types."""

# Enrichment response models (step-analysis plugin output).


class WDKEnrichmentRowBase(WDKModel):
    """Statistical fields shared by the GO, pathway, and word enrichment plugins.

    Every value arrives as a string, including the numeric ones.
    """

    bgd_genes: str = "0"
    result_genes: str = "0"
    percent_in_result: str = "0"
    fold_enrich: str = "0"
    odds_ratio: str = "0"
    p_value: str = "1"
    benjamini: str = "1"
    bonferroni: str = "1"


class WDKGoEnrichmentRow(WDKEnrichmentRowBase):
    """A single row from the GO enrichment plugin."""

    go_id: str
    go_term: str


class WDKPathwayEnrichmentRow(WDKEnrichmentRowBase):
    """A single row from the pathway enrichment plugin."""

    pathway_id: str
    pathway_name: str
    pathway_source: str = ""


class WDKWordEnrichmentRow(WDKEnrichmentRowBase):
    """Word enrichment result row.

    The word description arrives under the JSON key ``pathwayName``.
    """

    word: str
    pathway_name: str = ""


class WDKEnrichmentResponse(WDKModel):
    """Envelope returned by the analysis result endpoint."""

    result_data: list[JSONObject] = Field(default_factory=list)
    download_path: str = ""
    pvalue_cutoff: str = ""


# Request models. These are mutable, not frozen.


class PatchStepSpec(CamelModel):
    """Fields for updating an existing step."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="ignore",
    )

    custom_name: str | None = None
    expanded: bool | None = None
    expanded_name: str | None = None
    display_preferences: WDKDisplayPreferences | None = None


class NewStepSpec(PatchStepSpec):
    """Full spec for creating a new step."""

    search_name: str
    search_config: WDKSearchConfig


class CombinedStepSpec(PatchStepSpec):
    """Spec for creating a boolean combine step.

    The boolean search name and its parameter names depend on the record type
    and are resolved at call time.
    """

    primary_step_id: int
    secondary_step_id: int
    boolean_operator: BooleanOperator
    wdk_weight: int | None = None
