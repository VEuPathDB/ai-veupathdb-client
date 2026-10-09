import json
from pathlib import Path

import pytest

from veupathdb.devtools import eda_schemas, fixtures
from veupathdb.testing import NEEDS_QA_RECORDING, wdk_fixtures


@pytest.fixture
def empty_stores(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(wdk_fixtures, "FIXTURE_DIR", tmp_path)
    monkeypatch.setattr(eda_schemas, "FIXTURE_DIR", tmp_path)
    return tmp_path


def test_the_wdk_verify_names_every_missing_recording(
    empty_stores: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    del empty_stores

    assert fixtures.main(["verify"]) == 0

    out = capsys.readouterr().out
    for request in wdk_fixtures.FIXTURES:
        assert f"{request.name:44} MISSING {NEEDS_QA_RECORDING}" in out
    assert f"{len(wdk_fixtures.FIXTURES)} missing" in out


def test_the_wdk_verify_still_fails_a_recording_its_schema_refuses(
    empty_stores: Path,
) -> None:
    (empty_stores / "record_types.json").write_text(
        json.dumps(
            {
                "provenance": {
                    "site": "plasmodb",
                    "method": "GET",
                    "url": "https://qa.plasmodb.org/plasmo.qa/service/record-types",
                    "status": 200,
                    "content_type": "application/json",
                    "recorded_at": "2026-10-09",
                    "reads": "WDK-HTTP-004",
                },
                "body": {"not": "a list"},
            }
        )
    )

    assert fixtures.main(["verify"]) == 1


def test_the_eda_verify_names_every_missing_recording(
    empty_stores: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    del empty_stores

    assert eda_schemas.main(["verify"]) == 0

    out = capsys.readouterr().out
    for binding in eda_schemas.BINDINGS:
        assert f"{binding.fixture:42} MISSING {NEEDS_QA_RECORDING}" in out
    assert f"{len(eda_schemas.BINDINGS)} missing" in out
