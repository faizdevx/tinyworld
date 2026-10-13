"""The simulation tick: time passes, agents decide, the Game Master resolves,
witnesses remember."""

import asyncio
from dataclasses import dataclass, field

from tinyworld.agents.agent import Acted, Agent
from tinyworld.agents.beliefs import BeliefStore
from tinyworld.agents.memory import Compactor, ImportanceScorer, MemoryStore, NewMemory
from tinyworld.agents.persona import persona_of, render
from tinyworld.agents.planner import Planner
from tinyworld.agents.reflection import Reflector
from tinyworld.core import effects as fx
from tinyworld.core.events import Event, EventDraft, Outcome
from tinyworld.core.session import WorldSession
from tinyworld.core.state import Entity, WorldState
from tinyworld.gm.adjudicator import Adjudicator
from tinyworld.gm.master import GameMaster
from tinyworld.gm.perception import Observation, limit_attention
from tinyworld.llm.embed import Embedder, HashEmbedder
from tinyworld.llm.structured import StructuredLLM
from tinyworld.llm.types import CallContext
from tinyworld.sim.step import apply_intents


@dataclass
class TickResult:
    tick_seq: int
    events: list[Event] = field(default_factory=list)
    outcomes: list[Outcome] = field(default_factory=list)
    thoughts: dict[str, str] = field(default_factory=dict)
    memories_written: int = 0
    reflections: int = 0


class Simulation:
    def __init__(
        self,
        session: WorldSession,
        llm: StructuredLLM | None,
        *,
        embedder: Embedder | None = None,
        world_digest: str = "",
        step_minutes: int = 60,
        attention_limit: int = 8,
        reflect_threshold: float = 3.0,
        max_active_memories: int = 60,
        gm: GameMaster | None = None,
    ) -> None:
        self.session = session
        self.llm = llm
        self.world_digest = world_digest
        self.step_minutes = step_minutes
        self.attention_limit = attention_limit
        store = session.store
        self.memory = MemoryStore(store, embedder or HashEmbedder())
        self.beliefs = BeliefStore(store)
        self.planner = Planner(self.memory)
        self.scorer = ImportanceScorer(llm)
        self.reflector = Reflector(
            llm, self.memory, self.beliefs, threshold=reflect_threshold
        )
        self.compactor = Compactor(llm, self.memory, max_active=max_active_memories)
        self.gm = gm or GameMaster(
            Adjudicator(llm, world_digest=world_digest) if llm else None,
            seed=session.world_id,
        )
        self.agent = (
            Agent(llm, self.memory, self.beliefs, self.planner, world_digest=world_digest)
            if llm
            else None
        )

    # -- hooks later phases extend --------------------------------------

    def active_agents(self, state: WorldState, tick_seq: int) -> list[Entity]:
        """People who decide for themselves this tick."""
        return sorted(
            (p for p in state.people() if p.location and persona_of(p) is not None),
            key=lambda p: p.id,
        )

    def agent_for(self, entity: Entity) -> Agent | None:
        return self.agent

    def system_drafts(self, state: WorldState, tick_seq: int) -> list[EventDraft]:
        """Events the world itself produces at the start of a tick."""
        return []

    # -- the tick -------------------------------------------------------

    def _last_act_tick(self, agent_id: str) -> int:
        store = self.session.store
        clause, params = store.lineage_clause(
            self.session.branch_id, "tick_seq", before=True
        )
        row = store.query(
            f"SELECT MAX(tick_seq) AS last FROM llm_calls WHERE {clause}"
            " AND agent=? AND role LIKE 'agent.act%'",
            params + [agent_id],
        )[0]
        return row["last"] if row["last"] is not None else -1

    async def _remember(
        self, observer: Entity, observations: list[Observation], tick_seq: int
    ) -> int:
        branch = self.session.branch_id
        kept = limit_attention(observations, self.attention_limit)
        if not kept:
            return 0
        persona = persona_of(observer)
        who = render(observer, persona) if persona else observer.name
        scores = await self.scorer.score(
            who,
            [o.text for o in kept],
            CallContext(branch, tick_seq, observer.id),
            addressed=[o.addressed for o in kept],
        )
        items = [
            NewMemory(
                kind="utterance_heard"
                if o.speaker and o.speaker != observer.id
                else "observation",
                text=o.text,
                created_seq=o.event_seq,
                sim_time=o.sim_time,
                importance=score,
                confidence=o.confidence,
                source_events=[o.event_seq],
                participants=[p for p in o.participants if p != observer.id],
            )
            for o, score in zip(kept, scores)
        ]
        written = self.memory.write(branch, observer.id, items)
        for observation, memory in zip(kept, written):
            self.beliefs.update_from_observation(
                branch, self.session.state, observation, memory.id
            )
        return len(written)

    async def tick(self) -> TickResult:
        session = self.session
        branch = session.branch_id
        tick_seq = session.state.seq
        result = TickResult(tick_seq)

        # 1. Time passes, then whatever the world itself does.
        clock = EventDraft(
            kind="system", actor="system", visibility="god_only",
            effects=[fx.AdvanceTime(minutes=self.step_minutes)],
        )
        opening = session.commit(
            [clock] + self.system_drafts(session.state, tick_seq),
            atomic=False,
            observe=self._perceive,
        )
        result.events += opening.events
        observations = [o for batch in opening.observed for o in batch]

        # 2. Everyone decides at once, from the same view of the world.
        state = session.state
        actors = self.active_agents(state, tick_seq)
        deciders = [(e, self.agent_for(e)) for e in actors]
        deciders = [(e, a) for e, a in deciders if a is not None]
        acted: list[Acted] = await asyncio.gather(
            *(
                agent.act(
                    state, entity, branch,
                    CallContext(branch, tick_seq, entity.id),
                    self._last_act_tick(entity.id),
                )
                for entity, agent in deciders
            )
        )
        result.thoughts = {
            entity.id: act.thought for (entity, _), act in zip(deciders, acted)
        }

        # 3. The Game Master decides what actually happens.
        step = await apply_intents(
            session, self.gm, [a.intent for a in acted], CallContext(branch, tick_seq)
        )
        result.events += step.events
        result.outcomes = step.outcomes
        observations += step.observations

        # 4. Witnesses remember and update what they believe.
        state = session.state
        by_observer: dict[str, list[Observation]] = {}
        for observation in observations:
            by_observer.setdefault(observation.observer, []).append(observation)
        rememberers = [
            state.entities[o] for o in sorted(by_observer)
            if o in state.entities and persona_of(state.entities[o]) is not None
        ]
        counts = await asyncio.gather(
            *(self._remember(e, by_observer[e.id], tick_seq) for e in rememberers)
        )
        result.memories_written = sum(counts)

        # 5. Reflection and memory upkeep for those who have enough to chew on.
        due = [e for e in rememberers if self.reflector.due(branch, e.id)]
        reflected = await asyncio.gather(
            *(
                self.reflector.reflect(
                    branch, e.id, render(e, persona_of(e)), state.seq, state.sim_time,
                    CallContext(branch, tick_seq, e.id),
                )
                for e in due
            )
        )
        result.reflections = sum(1 for memories in reflected if memories)
        await asyncio.gather(
            *(
                self.compactor.compact(
                    branch, e.id, render(e, persona_of(e)), state.seq, state.sim_time,
                    CallContext(branch, tick_seq, e.id),
                )
                for e in rememberers
            )
        )
        return result

    @staticmethod
    def _perceive(event: Event, state: WorldState) -> list[Observation]:
        from tinyworld.gm.perception import perceive

        return perceive(event, state)

    async def run(self, ticks: int) -> list[TickResult]:
        return [await self.tick() for _ in range(ticks)]
