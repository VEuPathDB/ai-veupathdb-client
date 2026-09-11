"""An installed copy with the devtools extra runs the two verify commands."""

import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Ruff trusts an argv of string literals, so every varying value below rides the
# working directory or a file the command names.


@pytest.fixture(scope="module")
def workspace(tmp_path_factory: pytest.TempPathFactory) -> Path:
    work = tmp_path_factory.mktemp("devtools-extra").resolve()
    (work / "project").symlink_to(PROJECT_ROOT)
    subprocess.run(
        ["/usr/bin/env", "uv", "build", "--project", "project", "--out-dir", "dist"],
        cwd=work,
        check=True,
    )
    return work


@pytest.fixture(scope="module")
def env_with_the_extra(workspace: Path) -> Path:
    wheels = sorted((workspace / "dist").glob("*.whl"))
    assert len(wheels) == 1, f"expected one wheel, found {wheels}"
    (workspace / "requirements.txt").write_text(f"{wheels[0]}[devtools]\n")
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
def test_the_two_devtools_import_with_the_extra_installed(
    env_with_the_extra: Path,
) -> None:
    """The modules the wheel ships import the readers the extra installs."""
    finished = subprocess.run(
        [
            "/usr/bin/env",
            "env/bin/python",
            "-c",
            """
import veupathdb.devtools.eda_schemas
import veupathdb.devtools.fixtures

print(veupathdb.devtools.fixtures.__name__)
print(veupathdb.devtools.eda_schemas.__name__)
""",
        ],
        cwd=env_with_the_extra.parent,
        capture_output=True,
        text=True,
        check=True,
    )

    assert finished.stdout.split() == [
        "veupathdb.devtools.fixtures",
        "veupathdb.devtools.eda_schemas",
    ]


@pytest.mark.wheel
def test_an_installed_copy_verifies_its_own_recorded_bodies(
    env_with_the_extra: Path,
) -> None:
    """The command README advertises reports the recorded bodies, with no checkout."""
    finished = subprocess.run(
        [
            "/usr/bin/env",
            "env/bin/python",
            "-m",
            "veupathdb.devtools.fixtures",
            "verify",
        ],
        cwd=env_with_the_extra.parent,
        capture_output=True,
        text=True,
        check=True,
    )

    summary = finished.stdout.splitlines()[-1]
    assert "17 fixture(s), 3 schema check(s), 0 failed" in summary
