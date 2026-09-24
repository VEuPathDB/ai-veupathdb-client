"""The recorded VDI install bodies, and the command that records one live install.

A capture uploads an rnaseqrc file set on a live site under a registered account,
polls on the site's schedule, keeps each distinct status body, and deletes the
dataset. The kept bodies, with the owner and the account id replaced, are the fixtures.

Usage::

    python -m veupathdb.devtools.vdi_capture record NAME --site plasmodb \\
        --counts SENSE [--counts ANTISENSE] --sample-details FILE [--genome ID]

Recording needs WDK_TEST_TOKEN, or WDK_TEST_EMAIL/WDK_TEST_PASSWORD.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import sys
import time
from collections.abc import Awaitable, Callable
from contextlib import ExitStack
from pathlib import Path

import httpx
from pydantic import BaseModel, ConfigDict, TypeAdapter

from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.json_types import JSONObject
from veupathdb.testing.fixture_store import FIXTURE_ROOT
from veupathdb.testing.wdk_credentials import (
    NO_CREDENTIALS_REASON,
    registered_wdk_token,
)
from veupathdb.wdk.factory import get_site
from veupathdb.wdk.vdi.client import VdiClient, VdiDatasetGoneError
from veupathdb.wdk.vdi.genomes import reference_genomes
from veupathdb.wdk.vdi.models import (
    RNASEQRC,
    VdiDatasetOwner,
    VdiDatasetPostMeta,
    VdiDatasetStatus,
    VdiImportStatus,
    VdiInstallDisposition,
    VdiUploadStatus,
    poll_interval_seconds,
)
from veupathdb.wdk.vdi.rnaseqrc import RnaSeqCountFile, RnaSeqRcUpload

FIXTURE_DIR = FIXTURE_ROOT / "vdi"
PROVENANCE_FILE = "provenance.json"
_BUDGET_SECONDS = 2400.0
_BODY: TypeAdapter[JSONObject] = TypeAdapter(JSONObject)
_RECORDED_OWNER = VdiDatasetOwner(
    user_id=1000000001,
    first_name="Recorded",
    last_name="Owner",
    email="recorded.owner@example.invalid",
    affiliation="Example University",
)

type Sleep = Callable[[float], Awaitable[None]]


class VdiFixtureProvenance(BaseModel):
    """Where one recorded VDI body came from, and when in the install it was read."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    site: str
    method: str
    url: str
    status: int
    elapsed_s: float
    recorded_at: str
    reads: str


_PROVENANCE: TypeAdapter[dict[str, VdiFixtureProvenance]] = TypeAdapter(
    dict[str, VdiFixtureProvenance]
)


class ResponseRecorder(httpx.AsyncBaseTransport):
    """Forwards each request and keeps the last response body, decoded."""

    def __init__(self, inner: httpx.AsyncBaseTransport) -> None:
        self._inner = inner
        self.last_body: bytes = b""

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self._inner.handle_async_request(request)
        self.last_body = await response.aread()
        return response

    async def aclose(self) -> None:
        await self._inner.aclose()


class CapturedStatus(BaseModel):
    """One distinct body, and the seconds since the create was sent."""

    model_config = ConfigDict(frozen=True)

    label: str
    elapsed_s: float
    body: JSONObject


class CapturedInstall(BaseModel):
    """The create response, each distinct status body, and where the poll stopped."""

    model_config = ConfigDict(frozen=True)

    dataset_id: str
    post: CapturedStatus
    statuses: list[CapturedStatus]
    outcome: VdiInstallDisposition


def status_label(status: VdiDatasetStatus, project_id: str) -> str:
    """The axis that moved last, as a file-name suffix."""
    if status.disposition(project_id) is VdiInstallDisposition.INSTALLED:
        return "installed"
    if status.upload.status != VdiUploadStatus.SUCCESS:
        return f"upload_{status.upload.status}".replace("-", "_")
    if status.import_ is None or status.import_.status != VdiImportStatus.COMPLETE:
        imported = "queued" if status.import_ is None else status.import_.status
        return f"import_{imported}".replace("-", "_")
    entry = next((e for e in status.install if e.install_target == project_id), None)
    if entry is None:
        return "import_complete_no_install"
    if entry.data is None:
        return "import_complete_data_absent"
    return f"data_{entry.data.status}".replace("-", "_")


async def capture_install(
    client: VdiClient,
    recorder: ResponseRecorder,
    *,
    details: VdiDatasetPostMeta,
    upload: RnaSeqRcUpload,
    project_id: str,
    sleep: Sleep = asyncio.sleep,
) -> CapturedInstall:
    """Create, poll to an outcome, and delete. The delete runs on any failure."""
    started = time.monotonic()
    created = await client.create_rnaseqrc(details=details, upload=upload)
    post = CapturedStatus(
        label="post_response",
        elapsed_s=round(time.monotonic() - started, 1),
        body=_BODY.validate_json(recorder.last_body),
    )
    statuses: list[CapturedStatus] = []
    outcome = VdiInstallDisposition.CONTINUE
    try:
        polls = 0
        while time.monotonic() - started < _BUDGET_SECONDS:
            await sleep(poll_interval_seconds(polls, outcome))
            polls += 1
            details_read = await client.get(created.dataset_id)
            outcome = details_read.status.disposition(project_id)
            label = status_label(details_read.status, project_id)
            if not statuses or statuses[-1].label != label:
                statuses.append(
                    CapturedStatus(
                        label=label,
                        elapsed_s=round(time.monotonic() - started, 1),
                        body=_BODY.validate_json(recorder.last_body),
                    )
                )
            if outcome in {
                VdiInstallDisposition.INSTALLED,
                VdiInstallDisposition.FAILED,
            }:
                break
    finally:
        await client.delete(created.dataset_id)
    await _confirm_deleted(client, created.dataset_id, project_id)
    return CapturedInstall(
        dataset_id=created.dataset_id, post=post, statuses=statuses, outcome=outcome
    )


async def _confirm_deleted(client: VdiClient, vdi_id: str, project_id: str) -> None:
    try:
        await client.get(vdi_id)
    except VdiDatasetGoneError:
        pass
    else:
        msg = f"{vdi_id} is still readable after its delete"
        raise RuntimeError(msg)
    listed = await client.list_datasets(project_id)
    if any(entry.dataset_id == vdi_id for entry in listed):
        msg = f"{vdi_id} is still in the owned listing after its delete"
        raise RuntimeError(msg)


def _redacted(body: JSONObject) -> JSONObject:
    """The owner block and the account id inside the service's messages, replaced."""
    if "owner" not in body:
        return body
    owner = VdiDatasetOwner.model_validate(body["owner"])
    text = json.dumps(body).replace(f"{owner.user_id}/", f"{_RECORDED_OWNER.user_id}/")
    return _BODY.validate_json(text) | {
        "owner": _RECORDED_OWNER.model_dump(by_alias=True, mode="json")
    }


def load_provenance(directory: Path) -> dict[str, VdiFixtureProvenance]:
    """Every provenance entry the store in *directory* holds."""
    return _PROVENANCE.validate_json((directory / PROVENANCE_FILE).read_text())


def write_install(
    name: str,
    captured: CapturedInstall,
    *,
    site: str,
    base_url: str,
    recorded_at: str,
    into: Path,
) -> list[Path]:
    """Write each body as NAME_<label>.json with its provenance, and return the paths."""
    entries = load_provenance(into) if (into / PROVENANCE_FILE).exists() else {}
    written: list[Path] = []
    reads = [(captured.post, "POST", f"{base_url}/datasets", 202)] + [
        (status, "GET", f"{base_url}/datasets/{captured.dataset_id}", 200)
        for status in captured.statuses
    ]
    for status, method, url, code in reads:
        fixture = f"{name}_{status.label}"
        path = into / f"{fixture}.json"
        path.write_text(json.dumps(_redacted(status.body), indent=2) + "\n")
        entries[fixture] = VdiFixtureProvenance(
            site=site,
            method=method,
            url=url,
            status=code,
            elapsed_s=status.elapsed_s,
            recorded_at=recorded_at,
            reads=f"{name}: {status.label.replace('_', ' ')}",
        )
        written.append(path)
    ordered = dict(sorted(entries.items()))
    (into / PROVENANCE_FILE).write_text(
        _PROVENANCE.dump_json(ordered, indent=2).decode() + "\n"
    )
    return written


async def record_install(
    name: str, *, site_id: str, upload: RnaSeqRcUpload, genome: str | None
) -> CapturedInstall:
    """Run one capture live and write it into the store."""
    token = await registered_wdk_token()
    if token is None:
        raise RuntimeError(NO_CREDENTIALS_REASON)
    veupathdb_auth_token_ctx.set(token)
    site = get_site(site_id)
    offered = [] if genome is None else await reference_genomes(site_id)
    dependencies = [g for g in offered if g.resource_identifier == genome]
    if genome is not None and not dependencies:
        msg = f"{site_id} offers no genome {genome}"
        raise KeyError(msg)
    details = VdiDatasetPostMeta(
        type=RNASEQRC,
        install_targets=[site.project_id],
        name=f"veupathdb-py fixture {name}",
        summary="Recorded by vdi_capture and deleted after the capture.",
        dependencies=dependencies,
    )
    recorder = ResponseRecorder(httpx.AsyncHTTPTransport())
    client = VdiClient(base_url=site.vdi_base_url, transport=recorder)
    try:
        captured = await capture_install(
            client,
            recorder,
            details=details,
            upload=upload,
            project_id=site.project_id,
        )
    finally:
        await client.close()
    write_install(
        name,
        captured,
        site=site_id,
        base_url=site.vdi_base_url,
        recorded_at=datetime.datetime.now(tz=datetime.UTC).date().isoformat(),
        into=FIXTURE_DIR,
    )
    return captured


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vdi_capture", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    record = sub.add_parser("record", help="record one install live, then delete it")
    record.add_argument("name")
    record.add_argument("--site", default="plasmodb")
    record.add_argument("--counts", action="append", required=True, metavar="FILE")
    record.add_argument("--sample-details", required=True, metavar="FILE")
    record.add_argument("--genome", default=None, metavar="IDENTIFIER")
    args = parser.parse_args(argv)

    with ExitStack() as stack:
        counts = tuple(
            RnaSeqCountFile(
                name=Path(path).name, content=stack.enter_context(Path(path).open("rb"))
            )
            for path in args.counts
        )
        upload = RnaSeqRcUpload.model_validate(
            {"counts": counts, "sample_details": Path(args.sample_details).read_text()}
        )
        captured = asyncio.run(
            record_install(
                args.name, site_id=args.site, upload=upload, genome=args.genome
            )
        )
    for status in [captured.post, *captured.statuses]:
        print(f"{args.name}_{status.label}: {status.elapsed_s} s")
    print(f"{captured.dataset_id}: {captured.outcome}, deleted and confirmed")
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "FIXTURE_DIR",
    "PROVENANCE_FILE",
    "CapturedInstall",
    "CapturedStatus",
    "ResponseRecorder",
    "VdiFixtureProvenance",
    "capture_install",
    "load_provenance",
    "main",
    "record_install",
    "status_label",
    "write_install",
]
