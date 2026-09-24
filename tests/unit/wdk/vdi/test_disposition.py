"""Whether one project's install is still moving, finished, or failed, from recorded bodies.

The rules mirror the site's poller and its install predicate: both install axes of
this project's entry decide, and a status VDI adds later keeps the poll going.
"""

from __future__ import annotations

import copy

import pytest
from tests.unit.wdk.vdi._wire import recorded

from veupathdb.wdk.vdi.models import (
    VdiDatasetDetails,
    VdiDatasetStatus,
    VdiInstallDisposition,
    poll_interval_seconds,
)

PROJECT = "PlasmoDB"


def _status(name: str) -> VdiDatasetStatus:
    return VdiDatasetDetails.model_validate(recorded(name)).status


def _edited(name: str, **axes: object) -> VdiDatasetStatus:
    """A recorded body with one install entry's axes replaced."""
    body = copy.deepcopy(recorded(name))
    assert isinstance(body, dict)
    body["status"]["install"][0].update(axes)
    return VdiDatasetDetails.model_validate(body).status


@pytest.mark.parametrize(
    ("fixture", "expected"),
    [
        ("rnaseqrc_import_in_progress", VdiInstallDisposition.CONTINUE),
        ("rnaseqrc_import_complete_data_absent", VdiInstallDisposition.CONTINUE),
        ("rnaseqrc_data_running", VdiInstallDisposition.CONTINUE),
        ("rnaseqrc_installed", VdiInstallDisposition.INSTALLED),
        ("rnaseqrc_import_invalid", VdiInstallDisposition.FAILED),
        ("rnaseqrc_import_failed", VdiInstallDisposition.FAILED),
        ("dataset_import_queued", VdiInstallDisposition.CONTINUE),
        ("dataset_installed", VdiInstallDisposition.INSTALLED),
    ],
)
def test_the_disposition_follows_the_recorded_install(
    fixture: str, expected: VdiInstallDisposition
) -> None:
    assert _status(fixture).disposition(PROJECT) is expected


def test_meta_complete_with_data_running_is_not_installed() -> None:
    status = _status("rnaseqrc_data_running")

    assert status.install[0].meta.status == "complete"
    assert status.disposition(PROJECT) is VdiInstallDisposition.CONTINUE


def test_an_install_failure_on_another_project_does_not_stop_this_one() -> None:
    body = copy.deepcopy(recorded("rnaseqrc_data_running"))
    assert isinstance(body, dict)
    body["status"]["install"].append(
        {
            "installTarget": "ToxoDB",
            "meta": {"status": "failed-installation", "messages": ["no genome"]},
        }
    )
    status = VdiDatasetDetails.model_validate(body).status

    assert status.disposition(PROJECT) is VdiInstallDisposition.CONTINUE
    assert status.disposition("ToxoDB") is VdiInstallDisposition.FAILED
    assert status.failure_messages(PROJECT) == []


def test_no_entry_for_the_project_continues() -> None:
    assert (
        _status("rnaseqrc_installed").disposition("ToxoDB")
        is VdiInstallDisposition.CONTINUE
    )


def test_ready_for_reinstall_is_continue_slow() -> None:
    status = _edited("rnaseqrc_data_running", data={"status": "ready-for-reinstall"})

    assert status.disposition(PROJECT) is VdiInstallDisposition.CONTINUE_SLOW


@pytest.mark.parametrize(
    "failure", ["failed-validation", "failed-installation", "missing-dependency"]
)
def test_a_failed_data_axis_fails_the_install(failure: str) -> None:
    status = _edited(
        "rnaseqrc_data_running", data={"status": failure, "messages": ["no rows"]}
    )

    assert status.disposition(PROJECT) is VdiInstallDisposition.FAILED
    assert status.failure_messages(PROJECT) == ["no rows"]


def test_an_unknown_status_continues() -> None:
    status = _edited("rnaseqrc_data_running", data={"status": "verifying"})

    assert status.install[0].data is not None
    assert status.install[0].data.status == "verifying"
    assert status.disposition(PROJECT) is VdiInstallDisposition.CONTINUE


def test_an_invalid_import_reports_the_plugins_message_byte_for_byte() -> None:
    raw = recorded("rnaseqrc_import_invalid")
    assert isinstance(raw, dict)

    assert (
        _status("rnaseqrc_import_invalid").failure_messages(PROJECT)
        == (raw["status"]["import"]["messages"])
    )
    assert raw["status"]["import"]["messages"] == [
        (
            "Your counts file contains a non-count value ('-5' in sample 'S2', gene "
            "'PF3D7_0500'). Every count must be a whole, non-negative number with no "
            "thousands separators."
        )
    ]


def test_a_failed_import_reports_every_message_in_order() -> None:
    messages = _status("rnaseqrc_import_failed").failure_messages(PROJECT)

    assert messages == [
        "import exited with unexpected status 255",
        (
            "process error: error while making a(n) import request to plugin "
            "wrangler for dataset 1000000001/lIZ5ZVpEVE0FE targeting project N/A: "
            "import failed for dataset 1000000001/lIZ5ZVpEVE0FE in plugin wrangler "
            "targeting N/A: import exited with unexpected status 255"
        ),
    ]


def test_a_dataset_still_moving_has_no_failure_messages() -> None:
    assert _status("rnaseqrc_data_running").failure_messages(PROJECT) == []


def test_installed_targets_needs_both_axes() -> None:
    running = VdiDatasetDetails.model_validate(recorded("rnaseqrc_data_running"))
    done = VdiDatasetDetails.model_validate(recorded("rnaseqrc_installed"))

    assert running.installed_targets() == []
    assert done.installed_targets() == [PROJECT]


def test_a_rejected_upload_fails_with_its_message() -> None:
    body = copy.deepcopy(recorded("rnaseqrc_import_in_progress"))
    assert isinstance(body, dict)
    body["status"] = {
        "upload": {"status": "rejected", "message": "total upload size is larger"}
    }
    status = VdiDatasetDetails.model_validate(body).status

    assert status.disposition(PROJECT) is VdiInstallDisposition.FAILED
    assert status.failure_messages(PROJECT) == ["total upload size is larger"]


@pytest.mark.parametrize(
    ("poll_count", "seconds"),
    [(0, 2), (4, 2), (5, 5), (10, 5), (11, 15), (40, 15)],
)
def test_the_poll_follows_the_sites_three_rates(poll_count: int, seconds: int) -> None:
    assert poll_interval_seconds(poll_count, VdiInstallDisposition.CONTINUE) == seconds


def test_a_reinstall_wait_polls_once_a_minute() -> None:
    assert poll_interval_seconds(0, VdiInstallDisposition.CONTINUE_SLOW) == 60
    assert poll_interval_seconds(30, VdiInstallDisposition.CONTINUE_SLOW) == 60
