"""A record type string matches one WDK record type, or none."""

from __future__ import annotations

from veupathdb.wdk.record_types import resolve_record_type
from veupathdb.wdk.wdk_models import WDKRecordType

TYPES = [
    WDKRecordType(
        url_segment="transcript",
        full_name="TranscriptRecordClasses.TranscriptRecordClass",
        display_name="Gene",
    ),
    WDKRecordType(
        url_segment="genomic-sequence",
        full_name="SequenceRecordClasses.SequenceRecordClass",
        display_name="Genomic Sequence",
    ),
]


class TestTheMatchingOrder:
    def test_the_url_segment_matches_first(self) -> None:
        assert resolve_record_type(TYPES, "transcript") == "transcript"

    def test_the_full_name_matches_next(self) -> None:
        segment = resolve_record_type(
            TYPES, "TranscriptRecordClasses.TranscriptRecordClass"
        )

        assert segment == "transcript"

    def test_a_unique_display_name_matches_last(self) -> None:
        assert resolve_record_type(TYPES, "Gene") == "transcript"

    def test_the_match_ignores_case_and_surrounding_space(self) -> None:
        assert resolve_record_type(TYPES, "  TRANSCRIPT ") == "transcript"


class TestWhatMatchesNothing:
    def test_an_unknown_string_matches_nothing(self) -> None:
        assert resolve_record_type(TYPES, "organism") is None

    def test_an_empty_list_matches_nothing(self) -> None:
        assert resolve_record_type([], "transcript") is None

    def test_a_display_name_two_types_share_matches_nothing(self) -> None:
        ambiguous = [
            WDKRecordType(url_segment="transcript", display_name="Gene"),
            WDKRecordType(url_segment="popsetSequence", display_name="Gene"),
        ]

        assert resolve_record_type(ambiguous, "Gene") is None
