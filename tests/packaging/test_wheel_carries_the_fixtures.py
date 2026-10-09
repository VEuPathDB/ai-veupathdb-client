"""The built wheel carries the recorded stores, and an installed copy reads them."""

import subprocess
import tarfile
import zipfile
from pathlib import Path

import pytest

from veupathdb.testing import NEEDS_QA_RECORDING, needs_qa_recording

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_SOURCE = PROJECT_ROOT / "src" / "veupathdb" / "testing" / "fixtures"
WHEEL_PREFIX = "veupathdb/testing/fixtures/"

# Ruff trusts an argv of string literals, so every varying value below rides the
# working directory or a file the command names.


@pytest.fixture(scope="module")
def workspace(tmp_path_factory: pytest.TempPathFactory) -> Path:
    work = tmp_path_factory.mktemp("packaging").resolve()
    (work / "project").symlink_to(PROJECT_ROOT)
    subprocess.run(
        ["/usr/bin/env", "uv", "build", "--project", "project", "--out-dir", "dist"],
        cwd=work,
        check=True,
    )
    return work


@pytest.fixture(scope="module")
def built_wheel(workspace: Path) -> Path:
    wheels = sorted((workspace / "dist").glob("*.whl"))
    assert len(wheels) == 1, f"expected one wheel, found {wheels}"
    return wheels[0]


@pytest.fixture(scope="module")
def installed_env(workspace: Path, built_wheel: Path) -> Path:
    (workspace / "requirements.txt").write_text(f"{built_wheel}\n")
    subprocess.run(
        ["/usr/bin/env", "uv", "venv", "--python", "3.14", "env"],
        cwd=workspace,
        check=True,
    )
    subprocess.run(
        [
            "/usr/bin/env",
            "uv",
            "pip",
            "install",
            "--python",
            "env/bin/python",
            "--requirement",
            "requirements.txt",
        ],
        cwd=workspace,
        check=True,
    )
    return workspace / "env"


@pytest.mark.wheel
def test_the_wheel_holds_every_recorded_file(built_wheel: Path) -> None:
    """Each file of the two stores is packed under the testing package."""
    on_disk = {
        path.relative_to(FIXTURE_SOURCE).as_posix()
        for path in FIXTURE_SOURCE.rglob("*")
        if path.is_file()
    }
    assert on_disk, f"{FIXTURE_SOURCE} holds no recorded file"
    with zipfile.ZipFile(built_wheel) as archive:
        packed = {
            name.removeprefix(WHEEL_PREFIX)
            for name in archive.namelist()
            if name.startswith(WHEEL_PREFIX)
        }
    assert packed == on_disk


@pytest.mark.wheel
def test_the_wheel_carries_the_qa_list_and_no_production_list(
    built_wheel: Path,
) -> None:
    with zipfile.ZipFile(built_wheel) as archive:
        names = set(archive.namelist())
    assert "veupathdb/testing/qa_sites.yaml" in names
    assert "veupathdb/sites.yaml" not in names
    assert not any("production" in name for name in names)


@pytest.mark.wheel
def test_the_sdist_leaves_the_production_backup_out(workspace: Path) -> None:
    (sdist,) = sorted((workspace / "dist").glob("*.tar.gz"))
    with tarfile.open(sdist) as archive:
        names = archive.getnames()
    assert any(name.endswith("/qa_sites.yaml") for name in names)
    assert not any("fixtures-production-backup" in name for name in names)


@pytest.mark.wheel
@pytest.mark.skipif(
    needs_qa_recording(
        "wdk/record_types.json",
        "eda/studies_list.json",
        "eda/gene_id_distribution_de_filtered.json",
    ),
    reason=NEEDS_QA_RECORDING,
)
def test_an_installed_copy_reads_both_stores(installed_env: Path) -> None:
    """An interpreter that holds only the wheel reads a WDK and two EDA fixtures."""
    finished = subprocess.run(
        [
            "/usr/bin/env",
            "env/bin/python",
            "-c",
            """
import json
import sys

import veupathdb
from veupathdb.testing.eda_fixtures import FIXTURE_DIR, recorded_distribution
from veupathdb.testing.wdk_fixtures import load_recorded

print(sys.prefix)
print(veupathdb.__file__)
print(load_recorded("record_types").json_body()[0])
print(json.loads((FIXTURE_DIR / "studies_list.json").read_text())["studies"][0]["id"])
de_genes = recorded_distribution("gene_id_distribution_de_filtered").statistics
print(de_genes.num_distinct_values)
""",
        ],
        cwd=installed_env.parent,
        capture_output=True,
        text=True,
        check=True,
    )
    prefix, module, record_type, study_id, de_genes = finished.stdout.split()
    assert Path(prefix) == installed_env
    assert module.startswith(f"{installed_env}/")
    assert record_type == "transcript"
    assert study_id == "STUDY_ccab256dfb"
    assert de_genes == "842"
