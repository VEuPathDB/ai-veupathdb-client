from __future__ import annotations

from pydantic import ConfigDict, Field, JsonValue

from veupathdb.model import CamelModel


class _Body(CamelModel):
    model_config = ConfigDict(extra="ignore")


class PublishedParam(_Body):
    name: str
    type: str
    display_type: str | None = None
    vocabulary: JsonValue = None


class SearchData(_Body):
    parameters: list[PublishedParam] = Field(default_factory=list)
    param_names: list[str] = Field(default_factory=list)
    allowed_primary_input_record_class_names: JsonValue = None
    allowed_secondary_input_record_class_names: JsonValue = None
    output_record_class_name: JsonValue = None
    properties: dict[str, JsonValue] = Field(default_factory=dict)

    def by_name(self) -> dict[str, PublishedParam]:
        return {p.name: p for p in self.parameters}


class SearchDocument(_Body):
    search_data: SearchData


class AnswerMeta(_Body):
    total_count: int


class AnswerBody(_Body):
    meta: AnswerMeta


class CurrentUser(_Body):
    id: int


class StepValidation(_Body):
    level: JsonValue


class StepBody(_Body):
    validation: StepValidation
