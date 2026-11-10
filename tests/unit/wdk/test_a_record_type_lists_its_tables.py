from __future__ import annotations

import pytest

from veupathdb.testing import NEEDS_QA_RECORDING, needs_qa_recording
from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk.wdk_models import WDKRecordType


@pytest.mark.skipif(
    needs_qa_recording("wdk/record_type_build.json"), reason=NEEDS_QA_RECORDING
)
def test_an_expanded_record_type_lists_its_tables_and_their_columns() -> None:
    record_type = WDKRecordType.model_validate(
        load_recorded("record_type_build").json_body()
    )

    assert [
        (table.name, table.display_name, [a.name for a in table.attributes])
        for table in record_type.tables or []
    ] == [
        (
            "Datasets",
            "Datasets",
            ["build_number", "display_name", "display_category", "description", "note"],
        )
    ]


def test_a_record_type_without_tables_lists_none() -> None:
    assert WDKRecordType.model_validate({"urlSegment": "organism"}).tables is None
