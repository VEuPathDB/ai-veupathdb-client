"""The VDI wire types, checked against bodies the live service returned."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from tests.unit.wdk.vdi._wire import PROBE_ID, recorded

from veupathdb.wdk.vdi.models import (
    VdiDatasetDetails,
    VdiDatasetPostMeta,
    VdiDatasetPostResponse,
    VdiDatasetType,
    VdiImportStatus,
    VdiInstallStatus,
    VdiUploadStatus,
    VdiVisibility,
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
