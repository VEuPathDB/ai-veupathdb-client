"""The VDI wire types PathFinder sends and reads."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import ConfigDict, Field

from veupathdb.model import CamelModel

GENELIST_PLUGIN_NAME = "genelist"
GENELIST_PLUGIN_VERSION = "1.0"
DIRECT_UPLOAD_ORIGIN = "direct-upload"

_NAME_MIN = 3
_NAME_MAX = 1024
_SUMMARY_MIN = 3
_SUMMARY_MAX = 4000


class VdiVisibility(StrEnum):
    """Who may see a dataset once it is installed."""

    PRIVATE = "private"
    PROTECTED = "protected"
    PUBLIC = "public"
    CONTROLLED = "controlled"


class VdiUploadStatus(StrEnum):
    """The ingestion axis: whether the service took the bytes."""

    RUNNING = "running"
    SUCCESS = "success"
    REJECTED = "rejected"
    FAILED = "failed"


class VdiImportStatus(StrEnum):
    """The import axis: whether the plugin accepted the file."""

    QUEUED = "queued"
    IN_PROGRESS = "in-progress"
    COMPLETE = "complete"
    INVALID = "invalid"
    FAILED = "failed"


class VdiInstallStatus(StrEnum):
    """The per-target axis: whether one site's database holds the dataset."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED_VALIDATION = "failed-validation"
    FAILED_INSTALLATION = "failed-installation"
    READY_FOR_REINSTALL = "ready-for-reinstall"
    MISSING_DEPENDENCY = "missing-dependency"


TERMINAL_INSTALL_STATUSES = frozenset(
    {
        VdiInstallStatus.COMPLETE,
        VdiInstallStatus.FAILED_VALIDATION,
        VdiInstallStatus.FAILED_INSTALLATION,
        VdiInstallStatus.MISSING_DEPENDENCY,
    }
)


class VdiModel(CamelModel):
    """Base for every VDI wire type. New service fields never break a read."""

    model_config = ConfigDict(extra="ignore")


class VdiDatasetType(VdiModel):
    """The plugin a dataset is submitted to, by name and version."""

    name: str = Field(min_length=_NAME_MIN)
    version: str = Field(min_length=1)


class VdiDatasetTypeDetail(VdiDatasetType):
    """The plugin as the service reports it, with the display category."""

    category: str = ""


class VdiUploadStatusInfo(VdiModel):
    status: VdiUploadStatus
    message: str | None = None


class VdiImportStatusInfo(VdiModel):
    status: VdiImportStatus
    messages: list[str] = Field(default_factory=list)


class VdiInstallStatusDetails(VdiModel):
    status: VdiInstallStatus
    messages: list[str] = Field(default_factory=list)


class VdiInstallStatusEntry(VdiModel):
    """One target site's installation of a dataset."""

    install_target: str
    meta: VdiInstallStatusDetails
    data: VdiInstallStatusDetails | None = None


class VdiDatasetStatus(VdiModel):
    """The three independent axes a dataset moves along after a create."""

    upload: VdiUploadStatusInfo
    import_: VdiImportStatusInfo | None = Field(default=None, validation_alias="import")
    install: list[VdiInstallStatusEntry] = Field(default_factory=list)

    def is_terminal(self) -> bool:
        """Report whether no axis can still change without a new request."""
        if self.upload.status in {VdiUploadStatus.REJECTED, VdiUploadStatus.FAILED}:
            return True
        if self.import_ is None:
            return False
        if self.import_.status in {VdiImportStatus.INVALID, VdiImportStatus.FAILED}:
            return True
        return bool(self.install) and all(
            entry.meta.status in TERMINAL_INSTALL_STATUSES for entry in self.install
        )


class VdiDatasetOwner(VdiModel):
    user_id: int
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    affiliation: str | None = None


class VdiDatasetPostMeta(VdiModel):
    """The ``details`` part of a create request."""

    type: VdiDatasetType
    install_targets: list[str] = Field(min_length=1)
    name: str = Field(min_length=_NAME_MIN, max_length=_NAME_MAX)
    summary: str = Field(min_length=_SUMMARY_MIN, max_length=_SUMMARY_MAX)
    description: str | None = None
    origin: str = DIRECT_UPLOAD_ORIGIN
    visibility: VdiVisibility = VdiVisibility.PRIVATE
    dependencies: list[str] = Field(default_factory=list)


class VdiDatasetPostResponse(VdiModel):
    """The 202 body: the identifier the installation will carry."""

    dataset_id: str


class VdiDatasetDetails(VdiModel):
    """One dataset, as ``GET /datasets/{id}`` reports it."""

    dataset_id: str
    name: str
    summary: str = ""
    description: str | None = None
    visibility: VdiVisibility
    owner: VdiDatasetOwner
    created: datetime
    install_targets: list[str] = Field(default_factory=list)
    type: VdiDatasetTypeDetail
    status: VdiDatasetStatus

    def installed_targets(self) -> list[str]:
        """The sites whose databases already hold this dataset."""
        return [
            entry.install_target
            for entry in self.status.install
            if entry.meta.status is VdiInstallStatus.COMPLETE
        ]
