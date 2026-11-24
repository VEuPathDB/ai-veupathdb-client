from datetime import UTC, datetime
from pathlib import Path

import pytest

from veupathdb.testing.wire import Cassette, CassetteHeader, WireStore
from veupathdb.testing.wire.__main__ import main


def test_merge_copies_a_recorded_cassette(tmp_path: Path) -> None:
    source = WireStore(tmp_path / "source")
    source.write_cassette(
        Cassette(
            header=CassetteHeader(
                cassette="f/a.spec.ts/one-1", recorded_at=datetime.now(UTC)
            )
        )
    )

    main(["merge", str(source.root), str(tmp_path / "target")])

    assert WireStore(tmp_path / "target").cassette_ids() == ["f/a.spec.ts/one-1"]


def test_refresh_needs_the_account_in_the_shell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("WDK_TEST_EMAIL", raising=False)
    monkeypatch.delenv("WDK_TEST_PASSWORD", raising=False)
    sites = tmp_path / "sites.yaml"
    sites.write_text("sites: {}\n")
    with pytest.raises(SystemExit, match="WDK_TEST_EMAIL"):
        main(
            [
                "refresh",
                str(tmp_path),
                f"--sites={sites}",
                f"--report={tmp_path / 'r.md'}",
            ]
        )
