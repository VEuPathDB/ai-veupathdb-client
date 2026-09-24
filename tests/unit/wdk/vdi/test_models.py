"""The VDI wire types, checked against bodies the live service returned."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from tests.unit.wdk.vdi._wire import PROBE_ID, recorded

from veupathdb.wdk.vdi.models import (
    EDA_USER_DATASET_PREFIX,
    RNASEQRC,
    VdiDatasetDependency,
    VdiDatasetDetails,
    VdiDatasetListEntry,
    VdiDatasetPostMeta,
    VdiDatasetPostResponse,
    VdiDatasetType,
    VdiImportStatus,
    VdiInstallDisposition,
    VdiInstallStatus,
    VdiPlugin,
    VdiUploadStatus,
    VdiVisibility,
    eda_dataset_id,
)

GENELIST = VdiDatasetType(name="genelist", version="1.0")


def _meta(visibility: VdiVisibility = VdiVisibility.PRIVATE) -> VdiDatasetPostMeta:
    return VdiDatasetPostMeta(
        type=GENELIST,
        install_targets=["PlasmoDB"],
        name="Kinases with a signal peptide",
        summary="42 genes from PathFinder.",
        visibility=visibility,
    )


class TestTheCreateBodyMatchesWhatTheServiceAccepted:
    def test_the_details_part_serializes_the_recorded_field_names(self) -> None:
        body = _meta().model_dump(by_alias=True, mode="json", exclude_none=True)

        assert body == {
            "type": {"name": "genelist", "version": "1.0"},
            "installTargets": ["PlasmoDB"],
            "name": "Kinases with a signal peptide",
            "summary": "42 genes from PathFinder.",
            "origin": "direct-upload",
            "visibility": "private",
            "dependencies": [],
        }

    def test_a_description_is_sent_only_when_one_is_given(self) -> None:
        with_text = VdiDatasetPostMeta(
            type=GENELIST,
            install_targets=["ToxoDB"],
            name="A set",
            summary="Two genes.",
            description="Taken from strategy 42.",
        )

        assert "description" not in _meta().model_dump(by_alias=True, exclude_none=True)
        assert with_text.model_dump(by_alias=True, exclude_none=True)[
            "description"
        ] == ("Taken from strategy 42.")

    def test_an_empty_install_target_list_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            VdiDatasetPostMeta(
                type=GENELIST, install_targets=[], name="A set", summary="Two genes."
            )

    def test_a_name_shorter_than_the_service_accepts_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            VdiDatasetPostMeta(
                type=GENELIST, install_targets=["PlasmoDB"], name="ab", summary="Genes."
            )

    def test_a_visibility_the_service_does_not_define_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            VdiDatasetPostMeta.model_validate(
                {
                    "type": {"name": "genelist", "version": "1.0"},
                    "installTargets": ["PlasmoDB"],
                    "name": "A set",
                    "summary": "Two genes.",
                    "visibility": "everyone",
                }
            )


class TestTheRecordedResponsesParse:
    def test_the_create_response_names_the_new_dataset(self) -> None:
        parsed = VdiDatasetPostResponse.model_validate(
            recorded("dataset_post_response")
        )

        assert parsed.dataset_id == PROBE_ID

    def test_a_dataset_still_importing_carries_no_install_entry(self) -> None:
        parsed = VdiDatasetDetails.model_validate(recorded("dataset_import_queued"))

        assert parsed.status.upload.status is VdiUploadStatus.SUCCESS
        assert parsed.status.import_ is not None
        assert parsed.status.import_.status is VdiImportStatus.QUEUED
        assert parsed.status.install == []
        assert parsed.installed_targets() == []

    def test_an_installed_dataset_names_the_target_it_reached(self) -> None:
        parsed = VdiDatasetDetails.model_validate(recorded("dataset_installed"))

        assert parsed.dataset_id == PROBE_ID
        assert parsed.visibility is VdiVisibility.PRIVATE
        assert parsed.install_targets == ["PlasmoDB"]
        assert parsed.type.category == "Gene List"
        assert parsed.status.install[0].install_target == "PlasmoDB"
        assert parsed.status.install[0].meta.status is VdiInstallStatus.COMPLETE
        assert parsed.installed_targets() == ["PlasmoDB"]


GENOME = VdiDatasetDependency(
    resource_identifier="PlasmoDB-71_Pfalciparum3D7_Genome",
    resource_display_name="Plasmodium falciparum 3D7",
    resource_version="71",
)


class TestTheDependencyIsAnObject:
    def test_a_dependency_serializes_the_three_fields_the_service_reads(self) -> None:
        meta = VdiDatasetPostMeta(
            type=RNASEQRC,
            install_targets=["PlasmoDB"],
            name="Heat shock counts",
            summary="Twelve samples.",
            dependencies=[GENOME],
        )

        assert meta.model_dump(by_alias=True, mode="json")["dependencies"] == [
            {
                "resourceIdentifier": "PlasmoDB-71_Pfalciparum3D7_Genome",
                "resourceDisplayName": "Plasmodium falciparum 3D7",
                "resourceVersion": "71",
            }
        ]

    def test_the_recorded_dataset_carries_the_dependency_it_was_sent(self) -> None:
        raw = recorded("rnaseqrc_installed")
        assert isinstance(raw, dict)

        parsed = [VdiDatasetDependency.model_validate(d) for d in raw["dependencies"]]

        assert parsed == [GENOME]

    def test_an_identifier_longer_than_the_service_accepts_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            VdiDatasetDependency(
                resource_identifier="x" * 51,
                resource_display_name="Plasmodium falciparum 3D7",
                resource_version="71",
            )


class TestTheRecordedListing:
    def test_every_owned_entry_parses_with_its_status(self) -> None:
        raw = recorded("datasets_owned")
        assert isinstance(raw, list)

        entries = [VdiDatasetListEntry.model_validate(entry) for entry in raw]

        assert len(entries) == len(raw)
        assert {entry.type.name for entry in entries} == {"genelist", "rnaseqrc"}
        installed = [
            entry
            for entry in entries
            if entry.status.disposition("PlasmoDB") is VdiInstallDisposition.INSTALLED
        ]
        failed = [
            entry
            for entry in entries
            if entry.status.disposition("PlasmoDB") is VdiInstallDisposition.FAILED
        ]
        assert len(installed) == 6
        assert len(failed) == 3

    def test_a_listed_failure_carries_no_message(self) -> None:
        raw = recorded("datasets_owned")
        assert isinstance(raw, list)
        entries = [VdiDatasetListEntry.model_validate(entry) for entry in raw]
        invalid = [
            entry
            for entry in entries
            if entry.status.import_ is not None
            and entry.status.import_.status is VdiImportStatus.INVALID
        ]

        assert [entry.dataset_id for entry in invalid] == ["MoZ5BBpM8U0IM"]
        assert invalid[0].status.failure_messages("PlasmoDB") == []


class TestTheRecordedPlugins:
    def test_the_rnaseqrc_type_reports_its_extensions_and_cap(self) -> None:
        raw = recorded("plugins")
        assert isinstance(raw, list)
        plugins = [VdiPlugin.model_validate(plugin) for plugin in raw]

        found = [
            data_type
            for plugin in plugins
            if (data_type := plugin.data_type(RNASEQRC)) is not None
        ]

        assert len(found) == 1
        assert found[0].category == "RNA-Seq raw counts"
        assert found[0].max_file_size == 1073741824
        assert found[0].allowed_file_extensions == [".txt", ".tsv", ".csv", ".tab"]

    def test_an_empty_target_list_places_no_restriction(self) -> None:
        raw = recorded("plugins")
        assert isinstance(raw, list)
        plugins = {p["pluginName"]: VdiPlugin.model_validate(p) for p in raw}

        assert plugins["noop"].install_targets == []
        assert plugins["noop"].installs_into("PlasmoDB")
        assert plugins["wrangler"].installs_into("PlasmoDB")
        assert not plugins["biom"].installs_into("PlasmoDB")


def test_the_eda_dataset_id_is_the_vdi_id_behind_the_prefix() -> None:
    assert EDA_USER_DATASET_PREFIX == "EDAUD_"
    assert eda_dataset_id("4xZ5Q5pV1s4IM") == "EDAUD_4xZ5Q5pV1s4IM"
