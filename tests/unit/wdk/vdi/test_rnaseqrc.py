"""The rnaseqrc file set: the manifest, the generated sample info, and the refusals."""

from __future__ import annotations

import io

import pytest

from veupathdb.wdk.vdi.rnaseqrc import (
    SAMPLE_INFO_MAX_BYTES,
    RnaSeqCountFile,
    RnaSeqRcUpload,
)

EXTENSIONS = [".txt", ".tsv", ".csv", ".tab"]
DETAILS = "sample\ttreatment\nS1\tinfected\nS2\tcontrol\n"


def _count(name: str) -> RnaSeqCountFile:
    return RnaSeqCountFile(name=name, content=io.BytesIO(b"geneID\tS1\tS2\n"))


def _named(files: list[tuple[str, object]]) -> dict[str, object]:
    return dict(files)


class TestTheManifest:
    def test_the_manifest_names_each_role_and_ends_with_a_newline(self) -> None:
        unstranded = RnaSeqRcUpload(
            counts=(_count("HTSeq_run3.tsv"),), sample_details=DETAILS
        )
        stranded = RnaSeqRcUpload(
            counts=(_count("my_sense.tsv"), _count("my_anti.tsv")),
            sample_details=DETAILS,
        )

        assert _named(unstranded.files(EXTENSIONS))["manifest.tsv"] == (
            b"unstranded\tHTSeq_run3.tsv\nsample-info\tsample-info.txt\n"
        )
        assert _named(stranded.files(EXTENSIONS))["manifest.tsv"] == (
            b"sense\tmy_sense.tsv\n"
            b"antisense\tmy_anti.tsv\n"
            b"sample-info\tsample-info.txt\n"
        )

    def test_the_files_are_the_counts_then_the_sample_info_then_the_manifest(
        self,
    ) -> None:
        sense = _count("my_sense.tsv")
        anti = _count("my_anti.tsv")
        upload = RnaSeqRcUpload(counts=(sense, anti), sample_details=DETAILS)

        files = upload.files(EXTENSIONS)

        assert [name for name, _ in files] == [
            "my_sense.tsv",
            "my_anti.tsv",
            "sample-info.txt",
            "manifest.tsv",
        ]
        assert files[0][1] is sense.content
        assert files[1][1] is anti.content
        assert files[2][1] == DETAILS.encode()


class TestGeneratedNamesYieldToTheUsersOwn:
    def test_a_user_file_named_sample_info_keeps_its_name(self) -> None:
        upload = RnaSeqRcUpload(
            counts=(_count("sample-info.txt"),), sample_details=DETAILS
        )

        files = upload.files(EXTENSIONS)

        assert [name for name, _ in files] == [
            "sample-info.txt",
            "sample-info-1.txt",
            "manifest.tsv",
        ]
        assert _named(files)["manifest.tsv"] == (
            b"unstranded\tsample-info.txt\nsample-info\tsample-info-1.txt\n"
        )

    def test_the_generated_name_compares_without_case(self) -> None:
        upload = RnaSeqRcUpload(
            counts=(_count("Sample-Info.TXT"), _count("sample-info-1.txt")),
            sample_details=DETAILS,
        )

        files = upload.files(EXTENSIONS)

        assert [name for name, _ in files] == [
            "Sample-Info.TXT",
            "sample-info-1.txt",
            "sample-info-2.txt",
            "manifest.tsv",
        ]
        assert _named(files)["manifest.tsv"] == (
            b"sense\tSample-Info.TXT\n"
            b"antisense\tsample-info-1.txt\n"
            b"sample-info\tsample-info-2.txt\n"
        )

    def test_a_user_file_named_manifest_is_refused(self) -> None:
        with pytest.raises(ValueError, match=r"reserved"):
            RnaSeqRcUpload(counts=(_count("Manifest.TSV"),), sample_details=DETAILS)


class TestTheSampleDetails:
    def test_sample_details_are_counted_in_utf8_bytes(self) -> None:
        at_cap = "é" * 50_000
        assert len(at_cap.encode()) == SAMPLE_INFO_MAX_BYTES

        accepted = RnaSeqRcUpload(counts=(_count("c.tsv"),), sample_details=at_cap)
        assert _named(accepted.files(EXTENSIONS))["sample-info.txt"] == (
            at_cap.encode()
        )
        with pytest.raises(ValueError, match="100000 bytes"):
            RnaSeqRcUpload(counts=(_count("c.tsv"),), sample_details=at_cap + "a")

    @pytest.mark.parametrize("details", ["", " \n\t "])
    def test_blank_sample_details_are_refused(self, details: str) -> None:
        with pytest.raises(ValueError, match="sample details"):
            RnaSeqRcUpload(counts=(_count("c.tsv"),), sample_details=details)


class TestTheCountFiles:
    def test_no_count_file_is_refused(self) -> None:
        with pytest.raises(ValueError, match="counts"):
            RnaSeqRcUpload.model_validate({"counts": (), "sample_details": DETAILS})

    def test_three_count_files_are_refused(self) -> None:
        with pytest.raises(ValueError, match="counts"):
            RnaSeqRcUpload.model_validate(
                {
                    "counts": (_count("a.tsv"), _count("b.tsv"), _count("c.tsv")),
                    "sample_details": DETAILS,
                }
            )

    def test_two_files_with_one_name_are_refused_without_case(self) -> None:
        with pytest.raises(ValueError, match="same name"):
            RnaSeqRcUpload(
                counts=(_count("Counts.tsv"), _count("counts.TSV")),
                sample_details=DETAILS,
            )

    def test_a_tab_in_a_file_name_is_refused(self) -> None:
        with pytest.raises(ValueError, match="tab"):
            RnaSeqRcUpload(counts=(_count("my\tcounts.tsv"),), sample_details=DETAILS)

    def test_an_extension_the_plugin_does_not_list_is_refused(self) -> None:
        upload = RnaSeqRcUpload(counts=(_count("counts.xlsx"),), sample_details=DETAILS)

        with pytest.raises(ValueError, match=r"counts\.xlsx"):
            upload.files(EXTENSIONS)

    def test_the_extension_compares_without_case(self) -> None:
        upload = RnaSeqRcUpload(counts=(_count("Counts.TSV"),), sample_details=DETAILS)

        assert upload.files(EXTENSIONS)[0][0] == "Counts.TSV"
