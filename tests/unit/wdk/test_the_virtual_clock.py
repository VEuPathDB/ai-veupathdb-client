from __future__ import annotations

import asyncio

from tests.unit.wdk._virtual_clock import on_the_virtual_clock


def test_the_clock_moves_only_while_every_task_waits() -> None:
    seen: list[tuple[str, float]] = []

    async def busy() -> None:
        for _ in range(100):
            await asyncio.sleep(0)
        seen.append(("busy", asyncio.get_running_loop().time()))

    async def scenario() -> None:
        task = asyncio.create_task(busy())
        await asyncio.sleep(0.05)
        seen.append(("slept", asyncio.get_running_loop().time()))
        await task

    on_the_virtual_clock(scenario())

    assert seen == [("busy", 0.0), ("slept", 0.05)]


def test_a_wait_moves_the_clock_by_exactly_its_length() -> None:
    moved: list[float] = []

    async def scenario() -> None:
        loop = asyncio.get_running_loop()
        started = loop.time()
        await asyncio.sleep(3600)
        moved.append(loop.time() - started)

    on_the_virtual_clock(scenario())

    assert moved == [3600.0]
