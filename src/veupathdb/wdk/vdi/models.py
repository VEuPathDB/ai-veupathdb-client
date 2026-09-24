"""The VDI wire types the client sends and reads."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import ConfigDict, Field

from veupathdb.model import CamelModel

GENELIST_PLUGIN_NAME = "genelist"
GENELIST_PLUGIN_VERSION = "1.0"
DIRECT_UPLOAD_ORIGIN = "direct-upload"
EDA_USER_DATASET_PREFIX = "EDAUD_"
DEPENDENCY_IDENTIFIER_MAX = 50

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


class VdiInstallDisposition(StrEnum):
    """What a poller does next for one project: keep going, slow down, or stop."""

    CONTINUE = "continue"
    CONTINUE_SLOW = "continue-slow"
    INSTALLED = "installed"
    FAILED = "failed"


# The site's own poller: fast while a user watches, then slow over a long import.
_POLL_TIERS = ((5, 2.0), (11, 5.0))
_POLL_STEADY_SECONDS = 15.0
_POLL_REINSTALL_SECONDS = 60.0


def poll_interval_seconds(poll_count: int, disposition: VdiInstallDisposition) -> float:
    """Seconds to wait before poll number ``poll_count + 1``."""
    if disposition is VdiInstallDisposition.CONTINUE_SLOW:
        return _POLL_REINSTALL_SECONDS
    return next(
        (seconds for through, seconds in _POLL_TIERS if poll_count < through),
        _POLL_STEADY_SECONDS,
    )


_FAILED_UPLOAD = frozenset({VdiUploadStatus.REJECTED, VdiUploadStatus.FAILED})
_FAILED_IMPORT = frozenset({VdiImportStatus.INVALID, VdiImportStatus.FAILED})
_FAILED_INSTALL = frozenset(
    {
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


RNASEQRC = VdiDatasetType(name="rnaseqrc", version="1.0")


class VdiDatasetDependency(VdiModel):
    """A resource the dataset needs on the target site, such as a reference genome."""

    resource_identifier: str = Field(min_length=3, max_length=DEPENDENCY_IDENTIFIER_MAX)
    resource_display_name: str = Field(min_length=3, max_length=100)
    resource_version: str = Field(min_length=1, max_length=50)


# A status VDI adds later parses as text, so a poll keeps going instead of failing.
class VdiUploadStatusInfo(VdiModel):
    status: VdiUploadStatus | str = Field(union_mode="left_to_right")
    message: str | None = None


class VdiImportStatusInfo(VdiModel):
    status: VdiImportStatus | str = Field(union_mode="left_to_right")
    messages: list[str] = Field(default_factory=list)


class VdiInstallStatusDetails(VdiModel):
    status: VdiInstallStatus | str = Field(union_mode="left_to_right")
    messages: list[str] = Field(default_factory=list)


class VdiInstallStatusEntry(VdiModel):
    """One target site's installation of a dataset: its metadata and its data."""

    install_target: str
    meta: VdiInstallStatusDetails
    data: VdiInstallStatusDetails | None = None

    def axes(self) -> list[VdiInstallStatusDetails]:
        """The axes the service has reported, meta first."""
        return [self.meta] if self.data is None else [self.meta, self.data]

    def disposition(self) -> VdiInstallDisposition:
        """A failure on either axis fails the install; both must be complete."""
        statuses = [axis.status for axis in self.axes()]
        if any(status in _FAILED_INSTALL for status in statuses):
            return VdiInstallDisposition.FAILED
        if VdiInstallStatus.READY_FOR_REINSTALL in statuses:
            return VdiInstallDisposition.CONTINUE_SLOW
        if statuses == [VdiInstallStatus.COMPLETE, VdiInstallStatus.COMPLETE]:
            return VdiInstallDisposition.INSTALLED
        return VdiInstallDisposition.CONTINUE


class VdiDatasetStatus(VdiModel):
    """The three independent axes a dataset moves along after a create."""

    upload: VdiUploadStatusInfo
    import_: VdiImportStatusInfo | None = Field(default=None, validation_alias="import")
    install: list[VdiInstallStatusEntry] = Field(default_factory=list)

    def _entry(self, project_id: str) -> VdiInstallStatusEntry | None:
        return next(
            (entry for entry in self.install if entry.install_target == project_id),
            None,
        )

    def disposition(self, project_id: str) -> VdiInstallDisposition:
        """Where one project's install stands; only that project's entry decides.

        Installed means the import is complete and both install axes are complete.
        A status this client does not know keeps the poll going.
        """
        if self.upload.status in _FAILED_UPLOAD or (
            self.import_ is not None and self.import_.status in _FAILED_IMPORT
        ):
            return VdiInstallDisposition.FAILED
        entry = self._entry(project_id)
        if (
            self.upload.status != VdiUploadStatus.SUCCESS
            or self.import_ is None
            or self.import_.status != VdiImportStatus.COMPLETE
            or entry is None
        ):
            return VdiInstallDisposition.CONTINUE
        return entry.disposition()

    def failure_messages(self, project_id: str) -> list[str]:
        """The service's own text for each axis that failed, upload first."""
        messages: list[str] = []
        if self.upload.status in _FAILED_UPLOAD and self.upload.message:
            messages.append(self.upload.message)
        if self.import_ is not None and self.import_.status in _FAILED_IMPORT:
            messages.extend(self.import_.messages)
        entry = self._entry(project_id)
        if entry is not None:
            for axis in entry.axes():
                if axis.status in _FAILED_INSTALL:
                    messages.extend(axis.messages)
        return messages


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
    dependencies: list[VdiDatasetDependency] = Field(default_factory=list)


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
        """The sites whose databases hold both this dataset's metadata and its data."""
        return [
            entry.install_target
            for entry in self.status.install
            if self.status.disposition(entry.install_target)
            is VdiInstallDisposition.INSTALLED
        ]


class VdiDatasetListEntry(VdiModel):
    """One row of ``GET /datasets``. A failed import lists its status without messages."""

    dataset_id: str
    owner: VdiDatasetOwner
    type: VdiDatasetTypeDetail
    visibility: VdiVisibility
    name: str
    install_targets: list[str] = Field(default_factory=list)
    status: VdiDatasetStatus
    created: datetime
    summary: str = ""


class VdiPluginDataType(VdiDatasetTypeDetail):
    """One dataset type a plugin serves, with the checks a multi-file upload skips."""

    max_file_size: int
    allowed_file_extensions: list[str] = Field(default_factory=list)


class VdiPlugin(VdiModel):
    """One plugin ``GET /plugins`` lists. No install target means any site."""

    plugin_name: str
    data_types: list[VdiPluginDataType] = Field(default_factory=list)
    install_targets: list[str] = Field(default_factory=list)

    def data_type(self, dataset_type: VdiDatasetType) -> VdiPluginDataType | None:
        """The served type with this name and version, if this plugin serves it."""
        return next(
            (
                served
                for served in self.data_types
                if served.name == dataset_type.name
                and served.version == dataset_type.version
            ),
            None,
        )

    def installs_into(self, project_id: str) -> bool:
        return not self.install_targets or project_id in self.install_targets


def eda_dataset_id(vdi_id: str) -> str:
    """The EDA dataset id the WDK vocabulary gives an installed user dataset."""
    return f"{EDA_USER_DATASET_PREFIX}{vdi_id}"
