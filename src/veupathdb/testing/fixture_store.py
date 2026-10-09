"""The files this package ships for tests: the recorded stores and the QA site list."""

import atexit
from contextlib import ExitStack
from importlib.resources import as_file, files
from pathlib import Path

_RESOURCES = ExitStack()
atexit.register(_RESOURCES.close)


def package_file(name: str) -> Path:
    return _RESOURCES.enter_context(as_file(files("veupathdb.testing") / name))


FIXTURE_ROOT: Path = package_file("fixtures")
