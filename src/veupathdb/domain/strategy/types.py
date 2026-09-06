from __future__ import annotations

from typing import Protocol

from veupathdb.domain.strategy.validation import StepValidation

WireParams = dict[str, str]


class SyncStateProtocol(Protocol):
    @property
    def wdk_strategy_id(self) -> int | None: ...
    @property
    def step_counts(self) -> dict[str, int | None]: ...
    @property
    def wdk_step_ids(self) -> dict[str, int]: ...
    @property
    def wdk_push_errors(self) -> dict[str, str]: ...
    @property
    def step_validations(self) -> dict[str, StepValidation]: ...
