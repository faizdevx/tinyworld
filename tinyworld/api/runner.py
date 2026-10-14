"""One runner per active branch. It is the only thing that writes to that branch."""

import asyncio
import json

from tinyworld.core.events import Event
from tinyworld.core.session import WorldSession
from tinyworld.core.time import describe
from tinyworld.god.channel import GodChannel, GodResult
from tinyworld.llm import ledger
from tinyworld.llm.structured import StructuredLLM
from tinyworld.sim.budget import Budget
from tinyworld.sim.loop import Simulation, TickResult
from tinyworld.sim.scheduler import StepPolicy
from tinyworld.sim.timeskip import SkipResult, TimeSkip


def event_json(event: Event) -> dict:
    return event.model_dump(mode="json")


class BranchRunner:
    def __init__(
        self,
        session: WorldSession,
        llm: StructuredLLM | None,
        *,
        world_digest: str = "",
        embedder=None,
        offline: bool = False,
    ) -> None:
        self.session = session
        self.offline = offline
        self.budget = Budget(session.store, session.branch_id)
        self.sim = Simulation(
            session, llm, embedder=embedder, world_digest=world_digest,
            policy=StepPolicy(), budget=self.budget,
        )
        self.skipper = TimeSkip(self.sim)
        self.god = GodChannel(llm, world_digest=world_digest)
        self.lock = asyncio.Lock()
        self.running = False
        self.delay = 1.0
        self.busy = ""
        self.thoughts: dict[str, str] = {}
        self._task: asyncio.Task | None = None
        self._subscribers: set[asyncio.Queue] = set()

    # -- subscriptions --------------------------------------------------

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    def publish(self, kind: str, **payload) -> None:
        message = json.dumps({"type": kind, **payload})
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                # A reader that has fallen this far behind is dropped; it
                # reconnects and reloads rather than slowing the simulation.
                self._subscribers.discard(queue)

    def _announce(self, events: list[Event]) -> None:
        if events:
            self.publish("events", events=[event_json(e) for e in events])
        self.publish("status", status=self.status())

    # -- status ---------------------------------------------------------

    def status(self) -> dict:
        state = self.session.state
        usage = ledger.total(self.session.store, self.session.branch_id)
        return {
            "branch_id": self.session.branch_id,
            "seq": state.seq,
            "sim_time": state.sim_time.isoformat(),
            "sim_time_text": describe(state.sim_time),
            "running": self.running,
            "busy": self.busy,
            "delay": self.delay,
            "offline": self.offline,
            "cost": usage.cost,
            "calls": usage.calls,
            "run_cap": self.budget.run_cap,
            "agent_cap": self.budget.agent_cap,
            "level": self.budget.level(),
            "population": len(state.people()),
        }

    # -- control --------------------------------------------------------

    async def step(self) -> TickResult:
        async with self.lock:
            result = await self.sim.tick()
            self.thoughts.update({k: v for k, v in result.thoughts.items() if v})
        self._announce(result.events)
        return result

    async def _loop(self) -> None:
        try:
            while self.running:
                result = await self.step()
                if result.paused:
                    self.running = False
                    self.publish("paused", reason="budget", status=self.status())
                    break
                await asyncio.sleep(self.delay)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # the loop must report, not vanish
            self.running = False
            self.publish("error", message=f"{type(exc).__name__}: {exc}", status=self.status())

    def play(self, delay: float | None = None) -> None:
        if delay is not None:
            self.delay = min(max(delay, 0.0), 30.0)
        if self.running:
            return
        self.running = True
        self._task = asyncio.create_task(self._loop())
        self.publish("status", status=self.status())

    async def pause(self) -> None:
        self.running = False
        task, self._task = self._task, None
        if task is not None and not task.done():
            # Let a tick in flight finish, so nothing is left half-committed.
            async with self.lock:
                task.cancel()
        self.publish("status", status=self.status())

    async def skip(self, minutes: int) -> SkipResult:
        was_running = self.running
        await self.pause()
        async with self.lock:
            self.busy = "skipping time"
            self.publish("status", status=self.status())
            try:
                result = await self.skipper.skip(minutes)
            finally:
                self.busy = ""
        self._announce(result.events)
        if was_running and result.complete:
            self.play()
        return result

    async def god_submit(self, text: str) -> GodResult:
        async with self.lock:
            before = self.session.state.seq
            result = await self.god.submit(self.session, text)
            if result.applied:
                # Whoever the god touched matters now.
                targets = [
                    j.command.target for j in result.judgements
                    if j.command.target.startswith("person:")
                ]
                await self.sim.promote(targets, reason="touched by the god")
                await self.sim.remember(self.god.last_observations, before)
            events = self.session.store.events(self.session.branch_id, after=before)
        self._announce(events)
        return result

    def set_budget(
        self, run_cap: float | None = None, agent_cap: float | None = None, add: float = 0.0
    ) -> None:
        if run_cap is not None:
            self.budget.run_cap = run_cap if run_cap > 0 else None
        if agent_cap is not None:
            self.budget.agent_cap = agent_cap if agent_cap > 0 else None
        if add:
            self.budget.raise_cap(add)
        self.publish("status", status=self.status())
