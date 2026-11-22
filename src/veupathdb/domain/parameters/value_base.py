from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Hashable
from typing import Literal, Self

from pydantic import ConfigDict, JsonValue

from veupathdb.model import CamelModel


class HeldValue(CamelModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["held"] = "held"
    wire: str

    def to_wire(self) -> str:
        return self.wire

    def to_decoded(self) -> JsonValue:
        return self.wire

    def __eq__(self, other: object) -> bool:
        match other:
            case HeldValue(wire=wire):
                return self.wire == wire
            case KindValue():
                return other == self
            case _:
                return NotImplemented

    def __hash__(self) -> int:
        msg = "a held value has no kind to hash in; compare it with same_param_value"
        raise TypeError(msg)


class KindValue(CamelModel, ABC):
    model_config = ConfigDict(frozen=True)

    @classmethod
    @abstractmethod
    def from_wire(cls, wire: str) -> Self: ...

    @abstractmethod
    def identity(self) -> Hashable: ...

    @abstractmethod
    def to_wire(self) -> str: ...

    def _read(self, wire: str) -> Self | None:
        try:
            return type(self).from_wire(wire)
        except ValueError, TypeError:
            return None

    def __eq__(self, other: object) -> bool:
        match other:
            case HeldValue(wire=wire):
                read = self._read(wire)
                return read is not None and read.identity() == self.identity()
            case KindValue():
                return type(other) is type(self) and other.identity() == self.identity()
            case _:
                return NotImplemented

    def __hash__(self) -> int:
        return hash((type(self).__name__, self.identity()))
