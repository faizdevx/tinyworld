"""LLM adjudication of intents the rules cannot settle.

The model proposes an outcome in the closed effect vocabulary. The proposal is
checked three ways before it is accepted: the effect types are ones an
adjudicator may use, they touch only what the actor could reach, and they
apply cleanly to the current state.
"""

from pydantic import Field

from tinyworld.core import effects as fx
from tinyworld.core.effects import Effect
from tinyworld.core.events import Intent, Outcome, OutcomeStatus
from tinyworld.core.reducers import EffectError, apply_effects
from tinyworld.core.registry import REGISTRY, AttrRegistry
from tinyworld.core.state import Model, WorldState
from tinyworld.gm import context as ctx
from tinyworld.llm.structured import StructuredLLM
from tinyworld.llm.types import CallContext

# World-level changes belong to the god channel and the system, not to the
# outcome of one person's action.
FORBIDDEN = (fx.SetRule, fx.AdvanceTime, fx.SetEdge, fx.RemoveEntity)
# Attributes that define who an agent is; an action's outcome may not rewrite them.
PROTECTED_ATTRS = frozenset({"persona", "tier"})
MAX_MINUTES = 24 * 60

SYSTEM = """You are the Game Master of a simulated world. A person attempts an action. \
Decide what actually happens, as a fair and realistic referee.

Rules:
- Judge plausibility from the situation given. People fail, are refused, get caught.
- Do not favour the actor. Other people keep their own interests and may resist.
- Express every change to the world as effects from the allowed list. If nothing \
changes, return no effects.
- Only affect people and things that are present. Use the ids shown in brackets.
- status: success, partial, failed (attempted but did not work) or impossible.
- narration: one or two plain sentences describing what an onlooker would see.
- minutes: how long it took.
- loud: true if people next door would hear it."""

EFFECT_GUIDE = """Allowed effects (JSON objects with a "type"):
- MoveEntity {entity, to}
- TransferItem {item, quantity, source, dest}
- ChangeQuantity {holder, item, delta}  (create or use up a quantity)
- SetAttr {entity, key, value}
- CreateEntity {entity: {id, kind: "item", name, location, attrs, inventory}}
- Kill {entity, cause}
- SetRelation {source, dest, kind, value}  (value from -100 to 100)
- AssertFact {fact: {id: "fact:...", text, subject, predicate, value}}
- RetractFact {fact_id}
- StartProcess {process: {id: "process:...", name, owner, location, description, work_minutes}}
- AdvanceProcess {process_id, delta}
- EndProcess {process_id, status}
- Utter {speaker, text, addressees, channel, message_type, claims}"""


class Adjudication(Model):
    status: OutcomeStatus
    effects: list[Effect] = Field(default_factory=list)
    narration: str = ""
    reason: str = ""
    minutes: int = 10
    loud: bool = False


class AgentAdjudication(Adjudication):
    agent: str


class GroupAdjudication(Model):
    outcomes: list[AgentAdjudication]


def effect_ids(effect) -> set[str]:
    """Ids of existing entities and processes an effect refers to."""
    if isinstance(effect, fx.MoveEntity):
        return {effect.entity, effect.to}
    if isinstance(effect, fx.TransferItem):
        return {effect.item, effect.source, effect.dest}
    if isinstance(effect, fx.ChangeQuantity):
        return {effect.holder, effect.item}
    if isinstance(effect, (fx.SetAttr, fx.Kill)):
        return {effect.entity}
    if isinstance(effect, fx.CreateEntity):
        located = {effect.entity.location} if effect.entity.location else set()
        return located | set(effect.entity.inventory)
    if isinstance(effect, fx.SetRelation):
        return {effect.source, effect.dest}
    if isinstance(effect, fx.StartProcess):
        located = {effect.process.location} if effect.process.location else set()
        return {effect.process.owner} | located
    if isinstance(effect, (fx.AdvanceProcess, fx.EndProcess)):
        return {effect.process_id}
    if isinstance(effect, fx.Utter):
        return {effect.speaker, *effect.addressees}
    return set()


def check_effects(
    state: WorldState,
    actors: list[str],
    effects: list,
    *,
    extra_reach: set[str] | None = None,
    registry: AttrRegistry = REGISTRY,
) -> str | None:
    """Return why the effects are unacceptable, or None when they are fine."""
    reach: set[str] = set(extra_reach or ())
    for actor in actors:
        reach |= ctx.local_ids(state, actor)
        location = state.entities[actor].location
        if location:
            # A move may end in a neighbouring place.
            reach |= set(state.neighbors(location))
    created: set[str] = set()
    for effect in effects:
        if isinstance(effect, FORBIDDEN):
            return f"{effect.type} is not available to the Game Master"
        if isinstance(effect, fx.SetAttr) and effect.key in PROTECTED_ATTRS:
            return f"the attribute {effect.key!r} cannot be changed by an action"
        if isinstance(effect, fx.CreateEntity):
            if effect.entity.kind != "item":
                return "only items can be created by an action"
            created.add(effect.entity.id)
        if isinstance(effect, fx.StartProcess):
            created.add(effect.process.id)
        outside = effect_ids(effect) - reach - created
        if outside:
            return f"{effect.type} refers to something out of reach: {sorted(outside)}"
    try:
        apply_effects(state, effects, registry)
    except EffectError as exc:
        return f"effects do not apply: {exc}"
    return None


class Adjudicator:
    def __init__(
        self,
        llm: StructuredLLM,
        *,
        world_digest: str = "",
        registry: AttrRegistry = REGISTRY,
    ) -> None:
        self.llm = llm
        self.world_digest = world_digest
        self.registry = registry

    def _stable_context(self) -> str:
        parts = [EFFECT_GUIDE]
        if self.world_digest:
            parts.append("About this world:\n" + self.world_digest)
        return "\n\n".join(parts)

    def _situation(self, state: WorldState, intent: Intent) -> str:
        agent = state.entities[intent.agent]
        lines = [
            f"Time: {state.sim_time:%A %d %B %Y, %H:%M}",
            ctx.describe_place(state, agent.location),
            "",
            f"Actor: {ctx.describe_person(state, agent.id)}",
        ]
        target = state.entities.get(intent.target) if intent.target else None
        if target is not None and target.id != agent.location:
            if target.kind == "person":
                lines.append(f"Target: {ctx.describe_person(state, target.id)}")
                lines.append(
                    f"Actor's view of target: {ctx.describe_relation(state, agent.id, target.id)}; "
                    f"target's view of actor: {ctx.describe_relation(state, target.id, agent.id)}"
                )
            else:
                lines.append(f"Target: {target.name} [{target.id}]")
        elif intent.target in state.processes:
            process = state.processes[intent.target]
            lines.append(
                f"Target: ongoing work {process.name} [{process.id}], "
                f"{round(process.progress * 100)}% done"
            )
        lines += ["", "Known facts:", ctx.describe_facts(state, public_only=False)]
        return "\n".join(lines)

    @staticmethod
    def _attempt(intent: Intent, preset: list | None) -> str:
        lines = [
            f"Attempted action by [{intent.agent}]: verb={intent.verb.value}"
            + (f", target=[{intent.target}]" if intent.target else "")
            + (f", details={intent.args}" if intent.args else ""),
            f"In their words: {intent.text or '(no explanation)'}",
        ]
        if preset:
            said = "; ".join(e.text for e in preset if isinstance(e, fx.Utter))
            if said:
                lines.append(f'While doing so they say: "{said}" (already recorded; do not repeat it)')
        return "\n".join(lines)

    async def adjudicate(
        self,
        state: WorldState,
        intent: Intent,
        context: CallContext,
        *,
        preset: list | None = None,
    ) -> Outcome:
        preset = list(preset or [])

        def check(result: Adjudication) -> str | None:
            if result.status in ("failed", "impossible") and result.effects:
                return "a failed or impossible action cannot have effects"
            return check_effects(
                state, [intent.agent], preset + list(result.effects),
                registry=self.registry,
            )

        reply = await self.llm.call(
            "gm.adjudicate",
            Adjudication,
            system=SYSTEM,
            stable_context=self._stable_context(),
            user=self._situation(state, intent) + "\n\n" + self._attempt(intent, preset),
            context=CallContext(context.branch_id, context.tick_seq, intent.agent),
            fallback=lambda error: Adjudication(
                status="failed",
                narration="",
                reason=f"the Game Master could not resolve this: {error[:200]}",
            ),
            check=check,
        )
        result = reply.value
        return Outcome(
            intent=intent,
            status=result.status,
            effects=(preset + list(result.effects)) if reply.ok else [],
            narration=result.narration,
            reason=result.reason,
            minutes=min(max(result.minutes, 1), MAX_MINUTES),
            loud=result.loud,
            trace_id=reply.trace_id,
        )

    async def adjudicate_group(
        self,
        state: WorldState,
        intents: list[Intent],
        context: CallContext,
        *,
        presets: dict[str, list] | None = None,
    ) -> list[Outcome]:
        """Resolve intents that interfere with each other in one decision."""
        presets = presets or {}
        agents = [intent.agent for intent in intents]

        def check(result: GroupAdjudication) -> str | None:
            if sorted(o.agent for o in result.outcomes) != sorted(agents):
                return f"return exactly one outcome for each of: {agents}"
            combined: list = []
            for outcome in result.outcomes:
                if outcome.status in ("failed", "impossible") and outcome.effects:
                    return "a failed or impossible action cannot have effects"
                combined += presets.get(outcome.agent, []) + list(outcome.effects)
            return check_effects(state, agents, combined, registry=self.registry)

        situation = "\n\n".join(
            dict.fromkeys(self._situation(state, intent) for intent in intents)
        )
        attempts = "\n\n".join(
            self._attempt(intent, presets.get(intent.agent)) for intent in intents
        )
        reply = await self.llm.call(
            "gm.conflict",
            GroupAdjudication,
            system=SYSTEM
            + "\n\nSeveral people act at the same moment and their actions interfere. "
            "Decide all of them together so the results are consistent. "
            "Return one outcome per actor, each with that actor's id in `agent`.",
            stable_context=self._stable_context(),
            user=situation + "\n\nSimultaneous attempts:\n" + attempts,
            context=CallContext(
                context.branch_id, context.tick_seq, "+".join(sorted(agents))
            ),
            fallback=lambda error: GroupAdjudication(
                outcomes=[
                    AgentAdjudication(
                        agent=agent,
                        status="failed",
                        reason=f"the Game Master could not resolve this: {error[:200]}",
                    )
                    for agent in agents
                ]
            ),
            check=check,
        )
        by_agent = {outcome.agent: outcome for outcome in reply.value.outcomes}
        outcomes = []
        for intent in intents:
            result = by_agent[intent.agent]
            preset = presets.get(intent.agent, [])
            outcomes.append(
                Outcome(
                    intent=intent,
                    status=result.status,
                    effects=(preset + list(result.effects)) if reply.ok else [],
                    narration=result.narration,
                    reason=result.reason,
                    minutes=min(max(result.minutes, 1), MAX_MINUTES),
                    loud=result.loud,
                    trace_id=reply.trace_id,
                )
            )
        return outcomes
