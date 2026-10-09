from pathlib import Path

from veupathdb.testing import FIXTURE_ROOT, needs_qa_recording


def test_a_recording_in_the_store_is_not_needed() -> None:
    assert not needs_qa_recording("wdk/schema-pin.json")


def test_a_recording_absent_from_the_store_is_needed() -> None:
    assert needs_qa_recording("wdk/schema-pin.json", "wdk/no_such_recording.json")


def test_an_absolute_path_is_read_as_it_stands(tmp_path: Path) -> None:
    recording = tmp_path / "body.json"

    assert needs_qa_recording(recording)

    recording.write_text("{}")

    assert not needs_qa_recording(recording)
    assert FIXTURE_ROOT / recording == recording
