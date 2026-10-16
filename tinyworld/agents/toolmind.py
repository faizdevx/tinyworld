"""A resident who looks things up before deciding.

The ordinary decision is one model call with everything it might need in the
prompt. When a resident deliberates (a new day, something important happened)
it can instead run a short tool session, the same loop the studio team uses:
look around, recall what it remembers about something, check its promises and
undertakings, and then decide. It chooses what to look at, so its attention is
its own, and what it looked at is in the record.

The session ends with ``decide``, whose arguments are an ordinary decision. It
is checked by the same rules as a one-shot decision, so a tool-using resident
cannot do anything a plain one could not.
"""

import json

from pydantic import ValidationError

from tinyworld.agents.agent import Acted, Agent, Decision, canonical, to_intent
from tinyworld.agents.memory import EPISODIC
from tinyworld.agents.persona import persona_of
from tinyworld.agents.retrieval import retrieve
from tinyworld.core.events import Intent, Verb
from tinyworld.core.state import Entity, WorldState
from tinyworld.gm import context as ctx
from tinyworld.gm import rules
from tinyworld.llm.types import CallContext
from tinyworld.studio.session import AgentSession, Tool

ROLE = "agent.mind"
DECIDE_DOC = (
    'decide(verb, target?, args?, text, say?): what you do now. The same fields as '
    'always: verb is one of move, speak, give, take, work, start, rest, wait, other; '
    'say is {"text": ..., "to": [person ids]}'
)


class ToolMind:
    def __init__(self, agent: Agent, *, max_steps: int = 4) -> None:
        self.agent = agent
        self.max_steps = max_steps

    async def act(
        self,
        state: WorldState,
        entity: Entity,
        branch_id: str,
        context: CallContext,
        last_seen_seq: int,
        hint: str = "",
        recent: list[str] | None = None,
        promises: list[str] | None = None,
    ) -> Acted:
        agent = self.agent
        persona = persona_of(entity)
        if persona is None:
            return Acted(Intent(agent=entity.id, verb=Verb.WAIT, text="unsure"), "", False, None)
        prompt, causes = agent._prompt(
            state, entity, persona, branch_id, last_seen_seq, hint, recent, promises
        )
        chosen: dict = {}

        async def look_around(args: dict) -> str:
            here = entity.location
            people = [p.name + f" [{p.id}]" for p in state.people_at(here) if p.id != entity.id]
            exits = [state.entities[x].name + f" [{x}]" for x in sorted(state.neighbors(here))]
            return "\n".join([
                ctx.describe_place(state, here, viewer=entity.id),
                "People here: " + (", ".join(people) or "nobody"),
                "Ways out: " + (", ".join(exits) or "none"),
            ])

        async def recall(args: dict) -> str:
            query = str(args.get("about", "")).strip()
            memories = agent.memory.list(branch_id, entity.id, kinds=EPISODIC)
            if not memories:
                return "you remember nothing in particular"
            vector = agent.memory.embedder.embed([query])[0] if query else None
            found = retrieve(memories, query=vector, now=state.sim_time, k=5, goal=None)
            return "\n".join(f"- {s.memory.text}" for s in found) or "nothing comes to mind"

        async def my_promises(args: dict) -> str:
            from tinyworld.sim import commitments as pledges

            return "\n".join(pledges.lines_for(state, entity.id)) or "no promises outstanding"

        async def my_undertakings(args: dict) -> str:
            from tinyworld.world import projects

            return "\n".join(projects.lines_for(state, entity)) or "nothing under way"

        async def decide(args: dict) -> str:
            try:
                decision = canonical(state, Decision.model_validate(args))
                intent = to_intent(entity.id, decision)
            except (ValidationError, ValueError) as exc:
                return f"That is not a decision: {str(exc)[:300]}. Try again."
            verdict = rules.check(state, intent)
            if verdict.status == "impossible":
                return f"That cannot be done: {verdict.reason}. Choose something possible."
            chosen["decision"] = decision
            return "decided"

        tools = [
            Tool("look_around", "look_around(): where you are, who is here, the ways out", look_around),
            Tool("recall", "recall(about): what you remember about something", recall),
            Tool("my_promises", "my_promises(): promises you made or were made to you", my_promises),
            Tool("my_undertakings", "my_undertakings(): your projects and ideas you could chase", my_undertakings),
            Tool("decide", DECIDE_DOC, decide),
        ]

        class Done(Exception):
            pass

        session = AgentSession(
            agent.llm, world_id=branch_id, agent_id=entity.id, name=entity.name,
            role="resident of this world", tools=tools, max_steps=self.max_steps,
            llm_role=ROLE, call_id=f"{entity.id}:{context.tick_seq}",
        )
        task = (
            prompt
            + "\n\nYou may look around or recall things first. When you know what to do, "
            "call decide. finish without deciding means you wait."
        )
        # The session stops when `decide` has been accepted.
        original = session.tools["decide"].run

        async def decide_and_stop(args: dict) -> str:
            reply = await original(args)
            if "decision" in chosen:
                raise Done
            return reply

        session.tools["decide"].run = decide_and_stop
        try:
            await session.run(task, "About this world:\n" + agent.world_digest if agent.world_digest else "")
        except Done:
            pass
        decision = chosen.get("decision")
        if decision is None:
            return Acted(
                Intent(agent=entity.id, verb=Verb.WAIT, text="could not decide"), "", False, None, causes
            )
        if decision.plan is not None:
            agent.planner.store(branch_id, entity.id, decision.plan, state.seq, state.sim_time)
        return Acted(to_intent(entity.id, decision), decision.thought, True, None, causes)


def describe(args: dict) -> str:
    return json.dumps(args)[:80]
