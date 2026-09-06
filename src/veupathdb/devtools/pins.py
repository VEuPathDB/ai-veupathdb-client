"""The sha256 pin a vendored upstream tree answers to."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class VendoredPin(BaseModel):
    """The upstream commit a vendored tree was copied from.

    ``files`` maps each vendored path to the sha256 of the upstream bytes, so a
    hand-edited copy is a failure rather than a silent divergence.
    """

    model_config = ConfigDict(frozen=True)

    repo: str
    sha: str
    root: str
    vendored_at: str
    files: dict[str, str] = Field(default_factory=dict)

    @property
    def base_url(self) -> str:
        """The upstream directory the vendored tree mirrors, at the pinned commit."""
        return f"https://raw.githubusercontent.com/{self.repo}/{self.sha}/{self.root}/"


def pin_drift(
    pin: VendoredPin,
    directory: Path,
    vendored: Iterable[str],
) -> list[str]:
    """Every vendored file that is missing, edited, or absent from the pin."""
    problems: list[str] = []
    for relative, digest in sorted(pin.files.items()):
        path = directory / relative
        if not path.is_file():
            problems.append(f"{relative}: pinned but not vendored")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            problems.append(f"{relative}: differs from the pinned upstream bytes")
    problems.extend(
        f"{relative}: vendored but not pinned"
        for relative in sorted(set(vendored) - set(pin.files))
    )
    return problems
