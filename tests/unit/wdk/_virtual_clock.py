from __future__ import annotations

import asyncio
import selectors
from collections.abc import Coroutine


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0


class _Selector(selectors.DefaultSelector):
    def __init__(self, clock: _Clock) -> None:
        super().__init__()
        self._clock = clock

    def select(
        self, timeout: float | None = None
    ) -> list[tuple[selectors.SelectorKey, int]]:
        if timeout is None:
            return super().select(None)
        ready = super().select(0)
        if not ready and timeout > 0:
            self._clock.now += timeout
        return ready


class _VirtualClockLoop(asyncio.SelectorEventLoop):
    def __init__(self) -> None:
        self._clock = _Clock()
        super().__init__(_Selector(self._clock))

    def time(self) -> float:
        return self._clock.now


def on_the_virtual_clock(scenario: Coroutine[object, object, None]) -> None:
    with asyncio.Runner(loop_factory=_VirtualClockLoop) as runner:
        runner.run(scenario)
