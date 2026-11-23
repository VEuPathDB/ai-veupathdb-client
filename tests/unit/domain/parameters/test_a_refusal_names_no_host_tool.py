from __future__ import annotations

import pytest

from veupathdb.domain.parameters.phyletic import (
    census_states,
    validate_phyletic_codes,
)
from veupathdb.errors import ValidationError

_HOST_TOOLS = (
    "lookup_phyletic_codes",
    "build_phyletic_expression",
    "get_parameter_options",
    "get_search_overview",
    "search_for_searches",
    "get_record_types",
)


def _refusal(refused: pytest.ExceptionInfo[ValidationError]) -> str:
    return f"{refused.value.title} {refused.value.detail}"


def test_a_phyletic_refusal_names_no_tool() -> None:
    with pytest.raises(ValidationError) as not_a_census:
        census_states("pfal")
    with pytest.raises(ValidationError) as unknown:
        validate_phyletic_codes(["zzzz"], {"pfal"})

    for text in (_refusal(not_a_census), _refusal(unknown)):
        assert [tool for tool in _HOST_TOOLS if tool in text] == []
        assert "pfal" in text
