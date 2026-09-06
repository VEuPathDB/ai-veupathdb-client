"""Domain-native step validation types.

Defines ``StepValidation`` and ``StepValidationErrors`` — the domain
representation of WDK step/search/strategy validation state.  These are
pure data types (frozen, no I/O) that happen to match the shape returned
by the WDK REST API.

Previously defined in ``integrations.veupathdb.wdk_models`` as
``WDKValidation`` / ``WDKValidationErrors``, they were stranded in the
wrong layer.  Validation state ("is this step valid, and what are the
error messages?") is a domain concept, not an integration concern.

Moving them here lets ``SyncStateProtocol`` declare ``step_validations``
without importing from the integration layer, eliminating the isinstance
narrowing that was required at every read site.
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
