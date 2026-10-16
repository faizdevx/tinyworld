"""Adaptive concurrency: use as much parallelism as the server will take.

A local model server (vLLM, Ollama) or a rate-limited host has no fixed limit
the client can know in advance. This limiter starts at a given number of
requests in flight, raises it a step after a run of successes, and halves it
when the server pushes back (a 429, a timeout). It never goes below one or
above ``ceiling``.
"""

import asyncio
from contextlib import asynccontextmanager


class AdaptiveLimiter:
    def __init__(self, start: int = 4, *, floor: int = 1, ceiling: int = 32, grow_after: int = 8) -> None:
        self.floor = max(1, floor)
        self.ceiling = max(self.floor, ceiling)
        self.limit = min(max(start, self.floor), self.ceiling)
        self.grow_after = max(1, grow_after)
        self._in_flight = 0
        self._streak = 0
        self._cond = asyncio.Condition()
        self.peak = 0

    @property
    def in_flight(self) -> int:
        return self._in_flight

    @asynccontextmanager
    async def slot(self):
        async with self._cond:
            await self._cond.wait_for(lambda: self._in_flight < self.limit)
            self._in_flight += 1
            self.peak = max(self.peak, self._in_flight)
        try:
            yield
        finally:
            async with self._cond:
                self._in_flight -= 1
                self._cond.notify_all()

    def ok(self) -> None:
        """A request succeeded. A long enough run raises the limit by one."""
        self._streak += 1
        if self._streak >= self.grow_after and self.limit < self.ceiling:
            self.limit += 1
            self._streak = 0
            self._wake()

    def pushed_back(self) -> None:
        """The server said slow down. Halve the limit, within the floor."""
        self._streak = 0
        self.limit = max(self.floor, self.limit // 2)

    def _wake(self) -> None:
        # Called from a coroutine on the same loop; waiters re-check the limit.
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        async def notify() -> None:
            async with self._cond:
                self._cond.notify_all()

        loop.create_task(notify())
