"""The directory that holds the recorded WDK and EDA stores inside the package."""

import atexit
from contextlib import ExitStack
from importlib.resources import as_file, files
from pathlib import Path

_RESOURCES = ExitStack()
atexit.register(_RESOURCES.close)

FIXTURE_ROOT: Path = _RESOURCES.enter_context(
    as_file(files("veupathdb.testing") / "fixtures")
)
