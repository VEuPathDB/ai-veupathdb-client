"""The bodies a step write sends, each built from a whole search config."""

from veupathdb.json_types import JSONObject
from veupathdb.wdk._searches import BooleanSearch
from veupathdb.wdk.wdk_models import CombinedStepSpec, NewStepSpec, WDKSearchConfig


def search_config_write_body(config: WDKSearchConfig) -> JSONObject:
    """Every key the endpoint reads, since it resets each key the body omits.

    ``viewFilters`` is not part of a search config, and WDK's schema rejects it.
    """
    body: JSONObject = config.model_dump(
        by_alias=True, exclude_none=True, exclude={"view_filters"}
    )
    body["filters"] = [f.model_dump(by_alias=True) for f in config.filters]
    return body


def new_step_body(spec: NewStepSpec) -> JSONObject:
    config = spec.search_config
    search_config: JSONObject = config.model_dump(
        by_alias=True, exclude_defaults=True, exclude={"view_filters"}
    )
    if config.filters:
        search_config["filters"] = [f.model_dump(by_alias=True) for f in config.filters]
    body: JSONObject = {"searchName": spec.search_name, "searchConfig": search_config}
    if spec.custom_name:
        body["customName"] = spec.custom_name
    return body


def combined_step_body(spec: CombinedStepSpec, boolean: BooleanSearch) -> JSONObject:
    config = WDKSearchConfig(
        parameters={
            boolean.left_param: "",
            boolean.right_param: "",
            boolean.operator_param: spec.boolean_operator.value,
        },
        filters=spec.filters,
    )
    if spec.wdk_weight is not None:
        config = config.model_copy(update={"wdk_weight": spec.wdk_weight})
    return new_step_body(
        NewStepSpec(
            search_name=boolean.search_name,
            search_config=config,
            custom_name=spec.custom_name,
        )
    )
