"""Pydantic mirrors of the EDA REST wire shapes.

Python field names are snake_case; the camelCase keys come from the alias
generator. A field whose upstream spelling the generator cannot reach names
its aliases explicitly.
"""

from __future__ import annotations

from typing import Annotated, Any, ClassVar, Literal, Self

from pydantic import (
    AfterValidator,
    AliasChoices,
    ConfigDict,
    Discriminator,
    Field,
    JsonValue,
    model_validator,
)
from pydantic.alias_generators import to_camel

from veupathdb.json_types import JSONObject
from veupathdb.model import CamelModel

ANALYSIS_DISPLAY_NAME_BYTES = 50
ANALYSIS_DESCRIPTION_BYTES = 4000


def _cut_utf8(value: str, limit: int) -> str:
    """Keep at most ``limit`` UTF-8 bytes, without splitting a character."""
    if len(value.encode()) <= limit:
        return value
    return value.encode()[:limit].decode(errors="ignore").rstrip()


def _cut_display_name(value: str) -> str:
    return _cut_utf8(value, ANALYSIS_DISPLAY_NAME_BYTES)


def _cut_description(value: str) -> str:
    return _cut_utf8(value, ANALYSIS_DESCRIPTION_BYTES)


type AnalysisDisplayName = Annotated[str, AfterValidator(_cut_display_name)]
type AnalysisDescription = Annotated[str, AfterValidator(_cut_description)]


class EdaModel(CamelModel):
    """Base for all EDA REST wire models."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="ignore",
        frozen=True,
    )


class EdaStoredModel(EdaModel):
    """A node of a stored analysis document. It keeps every key the site stored.

    A node read from the site dumps with ``exclude_unset=True`` exactly as stored;
    a node built here dumps with its defaults. ``analysis_descriptor_patch`` applies both.
    """

    model_config = ConfigDict(extra="allow")


class EdaVariableSpec(EdaModel):
    entity_id: str
    variable_id: str


EdaSourceType = Literal["curated", "user_submitted"]


class EdaStudyOverview(EdaModel):
    """One element of ``GET /studies``. ``id`` is a study id, never parseable."""

    id: str
    dataset_id: str
    sha1hash: str = Field(
        default="",
        validation_alias=AliasChoices("sha1hash", "sha1_hash"),
        serialization_alias="sha1hash",
    )
    source_type: EdaSourceType
    display_name: str
    short_display_name: str | None = None
    description: str | None = None
    last_modified: str = ""


class EdaStudiesResponse(EdaModel):
    studies: list[EdaStudyOverview] = Field(default_factory=list)


class EdaActionAuthorization(EdaModel):
    study_metadata: bool = False
    subsetting: bool = False
    visualizations: bool = False
    results_first_page: bool = False
    results_all: bool = False


class EdaPermissionEntry(EdaModel):
    """One ``perDataset`` entry. The hash key is ``sha1Hash`` here."""

    study_id: str
    sha1_hash: str = Field(
        default="",
        validation_alias=AliasChoices("sha1Hash", "sha1_hash"),
    )
    is_user_study: bool = False
    display_name: str = ""
    short_display_name: str | None = None
    description: str | None = None
    type: str = ""
    action_authorization: EdaActionAuthorization = Field(
        default_factory=EdaActionAuthorization,
    )
    is_manager: bool = False
    access_request_status: str = ""


class EdaPermissionsResponse(EdaModel):
    per_dataset: dict[str, EdaPermissionEntry] = Field(default_factory=dict)


EdaVariableDataShape = Literal["continuous", "categorical", "ordinal", "binary"]
EdaVariableDisplayType = Literal[
    "default",
    "hidden",
    "multifilter",
    "geoaggregator",
    "latitude",
    "longitude",
]
EdaBinUnits = Literal["day", "week", "month", "year"]


class EdaNumberDistributionDefaults(EdaModel):
    display_range_min: float | None = None
    display_range_max: float | None = None
    range_min: float | None = None
    range_max: float | None = None
    bin_width: float | None = None
    bin_width_override: float | None = None


class EdaDateDistributionDefaults(EdaModel):
    display_range_min: str | None = None
    display_range_max: str | None = None
    range_min: str | None = None
    range_max: str | None = None
    bin_width: int | None = None
    bin_width_override: int | None = None
    bin_units: EdaBinUnits | None = None


class EdaVariableBase(EdaModel):
    id: str
    parent_id: str | None = None
    provider_label: str = ""
    display_name: str = ""
    definition: str | None = None
    display_type: EdaVariableDisplayType = "default"
    display_order: int | None = None
    hide_from: list[str] = Field(default_factory=list)


class EdaValueVariableBase(EdaVariableBase):
    data_shape: EdaVariableDataShape | None = None
    vocabulary: list[str] | None = None
    distinct_values_count: int = 0
    is_temporal: bool = False
    is_featured: bool = False
    is_merge_key: bool = False
    is_multi_valued: bool = False
    impute_zero: bool = False
    has_study_dependent_vocabulary: bool | None = None
    variable_spec_to_impute_zeroes_for: EdaVariableSpec | None = None


class EdaStringVariable(EdaValueVariableBase):
    type: Literal["string"] = "string"


class EdaIntegerVariable(EdaValueVariableBase):
    type: Literal["integer"] = "integer"
    distribution_defaults: EdaNumberDistributionDefaults = Field(
        default_factory=EdaNumberDistributionDefaults,
    )
    units: str | None = None


class EdaNumberVariable(EdaValueVariableBase):
    type: Literal["number"] = "number"
    distribution_defaults: EdaNumberDistributionDefaults = Field(
        default_factory=EdaNumberDistributionDefaults,
    )
    units: str | None = None
    precision: float | None = None


class EdaDateVariable(EdaValueVariableBase):
    type: Literal["date"] = "date"
    distribution_defaults: EdaDateDistributionDefaults = Field(
        default_factory=EdaDateDistributionDefaults,
    )


class EdaLongitudeVariable(EdaValueVariableBase):
    type: Literal["longitude"] = "longitude"
    precision: float | None = None


class EdaCategoryVariable(EdaVariableBase):
    """A tree node with no data. ``multifilter`` display makes it a filter target."""

    type: Literal["category"] = "category"


EdaVariable = Annotated[
    EdaStringVariable
    | EdaIntegerVariable
    | EdaNumberVariable
    | EdaDateVariable
    | EdaLongitudeVariable
    | EdaCategoryVariable,
    Discriminator("type"),
]


EdaCollectionType = Literal["number", "date", "integer", "string"]


class EdaCollection(EdaModel):
    """Same-typed variables on one entity. Reference it as (entityId, collectionId)."""

    id: str
    display_name: str = ""
    type: EdaCollectionType
    data_shape: EdaVariableDataShape | None = None
    vocabulary: list[str] | None = None
    distinct_values_count: int | None = None
    member_variable_ids: list[str] = Field(default_factory=list)
    impute_zero: bool = False
    normalization_method: str | None = None
    is_compositional: bool = False
    is_proportion: bool = False
    variable_spec_to_impute_zeroes_for: EdaVariableSpec | None = None
    member: str = ""
    member_plural: str = ""
    units: str | None = None
    precision: float | None = None


class EdaEntity(EdaModel):
    """One table of records. ``children`` is present only in the study call."""

    id: str
    id_column_name: str = ""
    display_name: str = ""
    display_name_plural: str = ""
    description: str = ""
    is_many_to_one_with_parent: bool = False
    variables: list[EdaVariable] = Field(default_factory=list)
    collections: list[EdaCollection] = Field(default_factory=list)
    children: list[EdaEntity] = Field(default_factory=list)


class EdaStudyDetail(EdaModel):
    """``GET /studies/{studyId}``. Carries no datasetId and no displayName."""

    id: str
    is_user_study: bool = False
    has_map: bool = False
    root_entity: EdaEntity


class EdaStudyDetailResponse(EdaModel):
    study: EdaStudyDetail


class EdaFilterBase(EdaModel):
    """Every filter names one variable on one entity."""

    entity_id: str
    variable_id: str


class EdaStringSetFilter(EdaFilterBase):
    type: Literal["stringSet"] = "stringSet"
    string_set: list[str] = Field(min_length=1)


class EdaNumberSetFilter(EdaFilterBase):
    type: Literal["numberSet"] = "numberSet"
    number_set: list[float] = Field(min_length=1)


class EdaDateSetFilter(EdaFilterBase):
    type: Literal["dateSet"] = "dateSet"
    date_set: list[str] = Field(min_length=1)


class EdaNumberRangeFilter(EdaFilterBase):
    type: Literal["numberRange"] = "numberRange"
    min: float
    max: float


class EdaDateRangeFilter(EdaFilterBase):
    """Bounds carry a time: a bare YYYY-MM-DD is a server error."""

    type: Literal["dateRange"] = "dateRange"
    min: str
    max: str


class EdaLongitudeRangeFilter(EdaFilterBase):
    """``left == right`` is a no-op that keeps every row."""

    type: Literal["longitudeRange"] = "longitudeRange"
    left: float
    right: float


class EdaSubFilter(EdaModel):
    """A multiFilter child. The parent's entity applies and the set is a string set."""

    variable_id: str
    string_set: list[str] = Field(min_length=1)


class EdaMultiFilter(EdaFilterBase):
    """The one nested type, and the only way to express OR."""

    type: Literal["multiFilter"] = "multiFilter"
    operation: Literal["union", "intersect"]
    sub_filters: list[EdaSubFilter] = Field(min_length=1)


# A named alias, so the schema carries one reusable EdaFilter definition
# instead of inlining the union at every field that holds a filter.
type EdaFilter = Annotated[
    EdaStringSetFilter
    | EdaNumberSetFilter
    | EdaDateSetFilter
    | EdaNumberRangeFilter
    | EdaDateRangeFilter
    | EdaLongitudeRangeFilter
    | EdaMultiFilter,
    Discriminator("type"),
]


class EdaLabeledRange(EdaStoredModel):
    """A comparator bin. ``min``/``max`` are declared required and are optional."""

    label: str
    min: str | None = None
    max: str | None = None


class EdaComparator(EdaStoredModel):
    variable: EdaVariableSpec
    group_a: list[EdaLabeledRange] = Field(min_length=1)
    group_b: list[EdaLabeledRange] = Field(min_length=1)


class EdaDifferentialExpressionConfig(EdaStoredModel):
    """The compute's own configuration. There is no collectionVariable here."""

    identifier_variable: EdaVariableSpec
    value_variable: EdaVariableSpec
    comparator: EdaComparator
    differential_expression_method: Literal["DESeq", "limma"] = "DESeq"
    p_value_floor: str = "1e-200"


class EdaDifferentialExpressionDescriptor(EdaStoredModel):
    """A differential-expression compute whose configuration is complete."""

    type: Literal["differentialexpression"] = "differentialexpression"
    configuration: EdaDifferentialExpressionConfig


class EdaDimensionalityReductionConfig(EdaStoredModel):
    """The PCA compute's configuration. Both variables are on one entity."""

    identifier_variable: EdaVariableSpec
    value_variable: EdaVariableSpec
    data_format: Literal["rawCounts", "normalizedValues"] = "normalizedValues"


class EdaDimensionalityReductionDescriptor(EdaStoredModel):
    """A dimensionality-reduction compute whose configuration is complete."""

    type: Literal["dimensionalityreduction"] = "dimensionalityreduction"
    configuration: EdaDimensionalityReductionConfig


# Left to right: a DE configuration carries a comparator, a PCA one does not.
type EdaComputeConfig = Annotated[
    EdaDifferentialExpressionConfig | EdaDimensionalityReductionConfig,
    Field(union_mode="left_to_right"),
]


class EdaPassDescriptor(EdaStoredModel):
    """The pass-through compute every plain visualization hangs off. It has no configuration."""

    type: Literal["pass"] = "pass"


class EdaOtherComputeDescriptor(EdaStoredModel):
    """Any other compute plugin, or a typed compute the UI has not finished configuring."""

    type: str
    configuration: JsonValue = None


# Left to right: a descriptor that fails the typed members is kept as it stands.
type EdaComputeDescriptor = Annotated[
    EdaDifferentialExpressionDescriptor
    | EdaDimensionalityReductionDescriptor
    | EdaPassDescriptor
    | EdaOtherComputeDescriptor,
    Field(union_mode="left_to_right"),
]


class EdaNumberRange(EdaStoredModel):
    min: float
    max: float


class EdaVolcanoConfiguration(EdaStoredModel):
    """The thresholds the WDK bridge plugin requires, and the plot settings the UI stores."""

    effect_size_threshold: float
    significance_threshold: float
    effect_direction: Literal["upOnly", "downOnly", "upAndDown"] = "upAndDown"
    marker_body_opacity: float | None = None
    independent_axis_range: EdaNumberRange | None = None
    dependent_axis_range: EdaNumberRange | None = None
    effect_size_label: str | None = None


class EdaVolcanoDescriptor(EdaStoredModel):
    type: Literal["volcanoplot"] = "volcanoplot"
    configuration: EdaVolcanoConfiguration
    current_plot_filters: list[EdaFilter] = Field(default_factory=list)
    thumbnail: str | None = None
    application_context: str | None = None


class EdaOtherVisualizationDescriptor(EdaStoredModel):
    """Any other visualization, or a volcano plot without its thresholds."""

    type: str
    configuration: JsonValue = None
    current_plot_filters: list[JsonValue] | None = None
    thumbnail: str | None = None
    application_context: str | None = None


type EdaVisualizationDescriptor = Annotated[
    EdaVolcanoDescriptor | EdaOtherVisualizationDescriptor,
    Field(union_mode="left_to_right"),
]


class EdaVisualization(EdaStoredModel):
    visualization_id: str
    display_name: str | None = None
    descriptor: EdaVisualizationDescriptor


class EdaComputation(EdaStoredModel):
    computation_id: str
    display_name: str | None = None
    descriptor: EdaComputeDescriptor
    visualizations: list[EdaVisualization] = Field(default_factory=list)


class EdaDifferentialExpressionComputation(EdaModel):
    """One computation of an analysis, beside its descriptor narrowed to the DE member."""

    computation: EdaComputation
    descriptor: EdaDifferentialExpressionDescriptor


class EdaSubsetDescriptor(EdaStoredModel):
    descriptor: list[EdaFilter] = Field(default_factory=list)
    ui_settings: JSONObject = Field(default_factory=dict)


class EdaAnalysisDescriptor(EdaStoredModel):
    """The whole semantic state. ``derivedVariables`` holds ids, not specs."""

    subset: EdaSubsetDescriptor = Field(default_factory=EdaSubsetDescriptor)
    computations: list[EdaComputation] = Field(default_factory=list)
    starred_variables: list[EdaVariableSpec] = Field(default_factory=list)
    data_table_config: JSONObject = Field(default_factory=dict)
    derived_variables: list[str] = Field(default_factory=list)


def differential_expression_computations(
    descriptor: EdaAnalysisDescriptor,
) -> list[EdaDifferentialExpressionComputation]:
    """The complete differential-expression computations of *descriptor*, in order."""
    return [
        EdaDifferentialExpressionComputation(
            computation=computation, descriptor=computation.descriptor
        )
        for computation in descriptor.computations
        if isinstance(computation.descriptor, EdaDifferentialExpressionDescriptor)
    ]


def _written(
    node: EdaStoredModel, *, built: bool, exclude: set[str] | None = None
) -> JSONObject:
    """A built node carries its defaults; a read node carries what the site stored."""
    return node.model_dump(
        by_alias=True,
        mode="json",
        exclude=exclude,
        exclude_none=built,
        exclude_unset=not built,
    )


def _built(descriptor: EdaComputeDescriptor | EdaVisualizationDescriptor) -> bool:
    """The wire always carries ``type``, so a descriptor without it set was built here."""
    return "type" not in descriptor.model_fields_set


def _visualization_body(visualization: EdaVisualization) -> JSONObject:
    return _written(visualization, built=_built(visualization.descriptor))


def _computation_body(computation: EdaComputation) -> JSONObject:
    written = _written(
        computation, built=_built(computation.descriptor), exclude={"visualizations"}
    )
    written["visualizations"] = [
        _visualization_body(visualization)
        for visualization in computation.visualizations
    ]
    return written


def analysis_descriptor_patch(descriptor: EdaAnalysisDescriptor) -> JSONObject:
    """The body of a descriptor PATCH: read nodes as stored, built nodes with defaults.

    The document level is written in full, as the site stores every member of it.
    """
    return descriptor.model_dump(
        by_alias=True, mode="json", exclude={"computations"}, exclude_none=True
    ) | {
        "computations": [
            _computation_body(computation) for computation in descriptor.computations
        ]
    }


class EdaNewAnalysis(EdaModel):
    """``studyId`` holds a DATASET id and must equal ``eda_dataset_id``."""

    study_id: str
    display_name: AnalysisDisplayName
    description: AnalysisDescription = ""
    is_public: bool = False
    study_version: str | None = None
    api_version: str | None = None
    descriptor: EdaAnalysisDescriptor = Field(
        default_factory=EdaAnalysisDescriptor,
    )


class EdaAnalysisSummary(EdaModel):
    analysis_id: str
    display_name: str = ""
    description: str | None = None
    study_id: str = ""
    is_public: bool = False
    creation_time: str = ""
    modification_time: str = ""
    num_filters: int = 0
    num_computations: int = 0


class EdaAnalysisDetail(EdaAnalysisSummary):
    descriptor: EdaAnalysisDescriptor = Field(
        default_factory=EdaAnalysisDescriptor,
    )


class EdaCreateAnalysisResponse(EdaModel):
    analysis_id: str


EdaJobStatus = Literal[
    "queued",
    "in-progress",
    "complete",
    "failed",
    "expired",
    "no-such-job",
]


class EdaComputeJob(EdaModel):
    """The job id is an MD5 of the request, so a caller never stores one."""

    job_id: str = Field(validation_alias=AliasChoices("jobID", "jobId", "job_id"))
    status: EdaJobStatus
    queue_position: int | None = None


class VolcanoStatsRow(EdaModel):
    """One point. Every number is a string, and a row may omit both p-values."""

    point_id: str = Field(
        validation_alias=AliasChoices("pointID", "pointId", "point_id"),
    )
    effect_size: str
    p_value: str | None = None
    adjusted_p_value: str | None = None


class VolcanoStatsResponse(EdaModel):
    effect_size_label: str = ""
    p_value_floor: str | None = None
    adjusted_p_value_floor: str | None = None
    statistics: list[VolcanoStatsRow] = Field(default_factory=list)


class EdaCountResponse(EdaModel):
    count: int


class EdaBinSpec(EdaModel):
    """Required for a continuous variable, refused for any other."""

    display_range_min: JsonValue = None
    display_range_max: JsonValue = None
    bin_width: float
    bin_units: EdaBinUnits | None = None


class EdaHistogramBin(EdaModel):
    value: float
    bin_start: str
    bin_end: str
    bin_label: str


class EdaDistributionStatistics(EdaModel):
    subset_size: int = 0
    subset_min: float | None = None
    subset_max: float | None = None
    subset_mean: float | None = None
    num_var_values: int = 0
    num_distinct_values: int = 0
    num_distinct_entity_records: int = 0
    num_missing_cases: int = 0


class EdaDistributionResponse(EdaModel):
    histogram: list[EdaHistogramBin] = Field(default_factory=list)
    statistics: EdaDistributionStatistics = Field(
        default_factory=EdaDistributionStatistics,
    )


EdaVariableClass = Literal["native", "derived", "computed"]
EdaPlotReference = Literal[
    "xAxis",
    "yAxis",
    "zAxis",
    "overlay",
    "facet1",
    "facet2",
    "geo",
    "latitude",
    "longitude",
    "undefined",
]
EdaStringBoolean = Literal["TRUE", "FALSE"]


class EdaVariableMapping(EdaModel):
    """One variable a plot or a compute names, with the role it plays there."""

    variable_class: EdaVariableClass
    variable_spec: EdaVariableSpec
    plot_reference: EdaPlotReference | None = None
    data_type: Literal["category", "string", "number", "date", "longitude", "integer"]
    data_shape: EdaVariableDataShape
    display_name: str | None = None
    display_range_min: str | float | None = None
    display_range_max: str | float | None = None
    vocabulary: list[str] | None = None
    impute_zero: bool = False
    has_study_dependent_vocabulary: bool | None = None
    is_collection: bool = False
    members: list[EdaVariableSpec] | None = None


class EdaComputedVariableMetadata(EdaModel):
    """``POST /computes/{name}/meta``: the variables a completed job generated."""

    variables: list[EdaVariableMapping]


class EdaPlotConfig(EdaModel):
    variables: list[EdaVariableMapping]
    complete_cases_all_vars: int | None = None
    complete_cases_axes_vars: int | None = None


class EdaStrataValue(EdaVariableSpec):
    """One value of an overlay or facet variable."""

    value: str


class EdaSampleSizeAxis(EdaVariableSpec):
    """The x-axis values a sample-size row counts, one per entry of ``size``."""

    value: list[str]


class EdaSampleSize(EdaModel):
    x_variable_details: EdaSampleSizeAxis | None = None
    overlay_variable_details: EdaStrataValue | None = None
    size: list[int]


class EdaCompleteCases(EdaModel):
    variable_details: EdaVariableSpec
    complete_cases: int


def _out_of_envelope(value: Any, envelope: str) -> Any:
    """The plot's ``data`` and ``config`` beside the tables that follow its key."""
    match value:
        case {**body}:
            match body.pop(envelope, None):
                case {**plot}:
                    return body | plot
                case _:
                    return value
        case _:
            return value


class _EdaPlotResponse(EdaModel):
    """A visualization answer: one plot under its own key, then the count tables."""

    envelope: ClassVar[str]

    config: EdaPlotConfig
    sample_size_table: list[EdaSampleSize] = Field(default_factory=list)
    complete_cases_table: list[EdaCompleteCases] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _lift_the_plot(cls, value: Any) -> Any:
        return _out_of_envelope(value, cls.envelope)


class EdaScatterplotConfig(EdaModel):
    """``ScatterplotSpec``. A compute's generated variables may stand on either axis."""

    output_entity_id: str
    value_spec: Literal[
        "raw", "smoothedMean", "smoothedMeanWithRaw", "bestFitLineWithRaw"
    ]
    x_axis_variable: EdaVariableSpec
    y_axis_variable: EdaVariableSpec
    overlay_variable: EdaVariableSpec | None = None
    return_point_ids: bool = True
    max_allowed_data_points: int | None = None
    show_missingness: EdaStringBoolean | None = None


class EdaScatterplotSeries(EdaModel):
    """One overlay value's points. Coordinates are strings, as a date axis needs."""

    overlay_variable_details: EdaStrataValue | None = None
    series_x: list[str] = Field(default_factory=list)
    series_y: list[str] = Field(default_factory=list)
    point_ids: list[str] = Field(default_factory=list)
    smoothed_mean_x: list[str] = Field(default_factory=list)
    smoothed_mean_y: list[float] = Field(default_factory=list)
    smoothed_mean_se: list[float] = Field(
        default_factory=list,
        validation_alias=AliasChoices("smoothedMeanSE", "smoothed_mean_se"),
        serialization_alias="smoothedMeanSE",
    )
    best_fit_line_x: list[str] = Field(default_factory=list)
    best_fit_line_y: list[float] = Field(default_factory=list)
    r2: float | None = None

    @model_validator(mode="after")
    def _one_point_per_index(self) -> Self:
        if len(self.series_x) != len(self.series_y):
            msg = "seriesX and seriesY do not have one value per point"
            raise ValueError(msg)
        if self.point_ids and len(self.point_ids) != len(self.series_x):
            msg = "pointIds does not have one id per point"
            raise ValueError(msg)
        if len(self.best_fit_line_x) != len(self.best_fit_line_y):
            msg = "bestFitLineX and bestFitLineY do not have one value per point"
            raise ValueError(msg)
        smoothed = {len(self.smoothed_mean_y), len(self.smoothed_mean_se)}
        if smoothed - {len(self.smoothed_mean_x)}:
            msg = "the smoothed mean arrays do not have one value per point"
            raise ValueError(msg)
        return self


class EdaScatterplotResponse(_EdaPlotResponse):
    envelope: ClassVar[str] = "scatterplot"

    data: list[EdaScatterplotSeries]


class EdaMosaicConfig(EdaModel):
    """``MosaicSpec`` without a facet, so the answer is one table."""

    output_entity_id: str
    x_axis_variable: EdaVariableSpec
    y_axis_variable: EdaVariableSpec
    show_missingness: EdaStringBoolean | None = None


class EdaTwoByTwoConfig(EdaMosaicConfig):
    """The reference values name the exposed column and the positive row."""

    x_axis_reference_value: str
    y_axis_reference_value: str


class EdaMosaicCounts(EdaModel):
    """``value[i][j]`` counts the records with x label ``i`` and y label ``y_label[i][j]``."""

    x_label: list[str]
    y_label: list[list[str]]
    value: list[list[int]]

    @model_validator(mode="after")
    def _one_count_per_cell(self) -> Self:
        rows = [len(labels) for labels in self.y_label]
        if len(self.x_label) != len(rows) or [len(r) for r in self.value] != rows:
            msg = "the mosaic counts do not have one value per x and y label"
            raise ValueError(msg)
        return self


class _EdaMosaicResponse(_EdaPlotResponse):
    """One unfaceted table, and its one statistics row lifted beside it."""

    envelope: ClassVar[str] = "mosaic"

    counts: EdaMosaicCounts

    @model_validator(mode="before")
    @classmethod
    def _one_table_and_one_row(cls, value: Any) -> Any:
        match _out_of_envelope(value, cls.envelope):
            case {"data": [table], **rest}:
                match rest.pop("statsTable", []):
                    case []:
                        return rest | {"counts": table}
                    case [{**row}]:
                        return rest | row | {"counts": table}
                    case _:
                        msg = "an unfaceted mosaic carries at most one statistics row"
                        raise ValueError(msg)
            case {"data": _}:
                msg = "an unfaceted mosaic carries exactly one table"
                raise ValueError(msg)
            case lifted:
                return lifted


class EdaContTableResponse(_EdaMosaicResponse):
    """Pearson's chi-squared test of independence on the table."""

    pvalue: float | str | None = None
    degrees_freedom: float | None = None
    chisq: float | None = None


class EdaTwoByTwoStatistic(EdaModel):
    value: float | None = None
    pvalue: str | None = None
    confidence_interval: str | None = None
    confidence_level: float | None = None


class EdaTwoByTwoResponse(_EdaMosaicResponse):
    """The 2x2 statistics, under the names the service's R package writes."""

    chi_sq: EdaTwoByTwoStatistic | None = None
    fisher: EdaTwoByTwoStatistic | None = None
    prevalence: EdaTwoByTwoStatistic | None = None
    odds_ratio: EdaTwoByTwoStatistic | None = None
    relative_risk: EdaTwoByTwoStatistic | None = None
    sensitivity: EdaTwoByTwoStatistic | None = None
    specificity: EdaTwoByTwoStatistic | None = None
    pos_predictive_value: EdaTwoByTwoStatistic | None = None
    neg_predictive_value: EdaTwoByTwoStatistic | None = None


class EdaBoxplotConfig(EdaModel):
    """``BoxplotSpec``. ``points`` and ``mean`` are string enums, not booleans."""

    output_entity_id: str
    points: Literal["outliers", "all"] = "outliers"
    mean: EdaStringBoolean = "TRUE"
    x_axis_variable: EdaVariableSpec
    y_axis_variable: EdaVariableSpec
    overlay_variable: EdaVariableSpec | None = None
    show_missingness: EdaStringBoolean | None = None


class EdaBoxplotGroup(EdaModel):
    """The box of one x-axis label."""

    label: str
    min: float | None = None
    lowerfence: float
    q1: float
    median: float
    q3: float
    upperfence: float
    max: float | None = None
    mean: float | None = None
    outliers: list[float] = Field(default_factory=list)
    raw_data: list[float] = Field(default_factory=list)


_BOXPLOT_COLUMNS = (
    "min",
    "lowerfence",
    "q1",
    "median",
    "q3",
    "upperfence",
    "max",
    "mean",
    "outliers",
    "rawData",
)


class EdaBoxplotSeries(EdaModel):
    """One overlay value's boxes, one group per label of the wire's parallel arrays."""

    overlay_variable_details: EdaStrataValue | None = None
    groups: list[EdaBoxplotGroup]

    @model_validator(mode="before")
    @classmethod
    def _one_group_per_label(cls, value: Any) -> Any:
        match value:
            case {"label": [*labels], **rest}:
                columns: dict[str, Any] = {
                    k: rest.pop(k) for k in _BOXPLOT_COLUMNS if k in rest
                }
                if {len(column) for column in columns.values()} - {len(labels)}:
                    msg = "a boxplot column does not have one value per label"
                    raise ValueError(msg)
                groups = [
                    {"label": label} | {k: c[i] for k, c in columns.items()}
                    for i, label in enumerate(labels)
                ]
                return rest | {"groups": groups}
            case _:
                return value


class EdaBoxplotResponse(_EdaPlotResponse):
    envelope: ClassVar[str] = "boxplot"

    data: list[EdaBoxplotSeries]
