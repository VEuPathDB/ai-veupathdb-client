"""The validity claim WDK states about a step, a search or a strategy.

The types are frozen data. WDK returns this shape on a step and inside the
bundle a refusal carries.
"""

from pydantic import ConfigDict, Field

from veupathdb.model import CamelModel


class StepValidationErrors(CamelModel):
    """Validation error details for a step."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    general: list[str] = Field(default_factory=list)
    by_key: dict[str, list[str]] = Field(default_factory=dict)


_UNCHECKED = "NONE"


class StepValidation(CamelModel):
    """A validity claim, and the level the claim was made at.

    Both keys are required: a default would turn a missing key into a claim
    nobody made.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    level: str
    is_valid: bool
    errors: StepValidationErrors | None = None

    def was_checked(self) -> bool:
        """Whether anything was validated. Level ``NONE`` means nothing was."""
        return self.level.upper() != _UNCHECKED

    def rejects(self) -> bool:
        """A negative verdict. False at level NONE means nobody looked."""
        return self.was_checked() and not self.is_valid

    def messages(self) -> list[str]:
        """The reported problems, per parameter first."""
        if self.errors is None:
            return []
        keyed = [
            f"{key}: {text}"
            for key, texts in self.errors.by_key.items()
            for text in texts
        ]
        return keyed + list(self.errors.general)
