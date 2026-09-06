"""The base model every VEuPathDB wire type inherits, and its number shapes."""

import math
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, PlainSerializer
from pydantic.alias_generators import to_camel


def _non_finite_to_none(v: object) -> object:
    """Map inf, -inf, nan and their WDK string forms to None.

    Pydantic lax mode handles str to float coercion, so every other value
    passes through untouched.
    """
    number = v
    if isinstance(number, str):
        try:
            number = float(number)
        except ValueError:
            return v
    if isinstance(number, float) and not math.isfinite(number):
        return None
    return v


def _round_4dp_or_none(v: float | None) -> float | None:
    return None if v is None else round(v, 4)


class CamelModel(BaseModel):
    """Base model with camelCase JSON aliases. snake_case kwargs only in Python.

    Do NOT set per-field ``Field(alias=...)`` on CamelModel subclasses - the
    class-level ``alias_generator`` covers it and keeps pyright happy. Explicit
    ``alias=`` forces pyright to require camelCase kwargs, breaking the invariant.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


NonFiniteToNone = Annotated[float | None, BeforeValidator(_non_finite_to_none)]
"""Float that is None when the source value is inf, -inf or nan."""

NonFiniteToNoneRounded = Annotated[
    float | None,
    BeforeValidator(_non_finite_to_none),
    PlainSerializer(_round_4dp_or_none, return_type=float | None),
]
"""NonFiniteToNone that also rounds to 4 dp on serialization."""
