"""Each WDK entry module imports on a cold interpreter, whatever the order."""

import subprocess
import sys

import pytest


def _assert_imported(finished: "subprocess.CompletedProcess[str]") -> None:
    if finished.returncode != 0:
        pytest.fail(finished.stderr)


def test_wdk_parameters_imports_first() -> None:
    """The parameter models import without wdk_models being imported first."""
    _assert_imported(
        subprocess.run(
            [sys.executable, "-c", "import veupathdb.wdk.wdk_parameters"],
            capture_output=True,
            text=True,
            check=False,
        )
    )


def test_wdk_models_imports_first() -> None:
    """The response models import without wdk_parameters being imported first."""
    _assert_imported(
        subprocess.run(
            [sys.executable, "-c", "import veupathdb.wdk.wdk_models"],
            capture_output=True,
            text=True,
            check=False,
        )
    )


def test_phyletic_tree_imports_first() -> None:
    """The phyletic reader imports as the first module of the package."""
    _assert_imported(
        subprocess.run(
            [sys.executable, "-c", "import veupathdb.wdk.phyletic_tree"],
            capture_output=True,
            text=True,
            check=False,
        )
    )


def test_strategy_api_base_imports_first() -> None:
    """The strategy API base imports as the first module of the package."""
    _assert_imported(
        subprocess.run(
            [sys.executable, "-c", "import veupathdb.wdk.strategy_api.base"],
            capture_output=True,
            text=True,
            check=False,
        )
    )
