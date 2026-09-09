"""The base model the WDK response and parameter models share."""

from pydantic import ConfigDict
from pydantic.alias_generators import to_camel

from veupathdb.model import CamelModel


class WDKModel(CamelModel):
    """Base for all WDK REST API response models."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="ignore",
        frozen=True,
    )
