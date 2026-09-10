from __future__ import annotations

from pydantic import Field

from veupathdb.model import CamelModel


class UnboundParameter(CamelModel):
    """A parameter of a search that holds no value yet, and the ask that binds it.

    ``options`` carries the parameter's vocabulary, and is empty for a
    parameter that takes a value of its own.
    """

    param_name: str
    question: str = ""
    options: list[str] = Field(default_factory=list)
