"""The podium: where residents bring their petitions to you.

Each open petition becomes a decision in the studio's queue (the same queue the
builders use for their questions): the bell rings, and the card says who is
asking, what they ask, how much faith they have, and what led them here (the
cause chain from the event log).

The god answers with a *power*: grant, whisper, show a sign, refuse, punish, or
ignore. Grant and punish take a sentence of what to do ("give her three loaves")
which goes through the ordinary god channel, so the same judging and compiling
apply. Not answering is also an answer: when the petition times out in the
world's own time it closes as silence and its decision is withdrawn.
"""

import asyncio

from tinyworld.agents.persona import persona_of
from tinyworld.core import causes
from tinyworld.studio.protocol import Decision
from tinyworld.world import petitions

POWERS = {
    "Grant": "grant",
    "Whisper": "whisper",
    "Show a sign": "sign",
    "Refuse": "refuse",
    "Punish": "punish",
    "Ignore": "ignore",
}


def card(town, petition: petitions.Petition) -> str:
    """Who is asking, and what led here."""
    session = town.session
    state = session.state
    person = state.entities.get(petition.by)
    if person is None:
        return ""
    persona = persona_of(person)
    lines = [
        f"{person.name}, {person.attrs.get('occupation') or 'resident'}"
        + (f", {person.attrs['age']}" if "age" in person.attrs else "")
        + f". Faith {petitions.faith_of(person)}/100."
    ]
    if persona is not None:
        if persona.goals:
            lines.append("Wants: " + "; ".join(persona.goals[:3]))
        if persona.fears:
            lines.append("Fears: " + "; ".join(persona.fears[:3]))
    if petition.offering:
        lines.append(f"Offers: {petition.offering}")
    event = next(
        (e for e in reversed(session.store.events(session.branch_id, actor=petition.by))
         if any(getattr(x, "fact", None) is not None and x.fact.id == petition.id for x in e.effects)),
        None,
    )
    if event is not None:
        graph = causes.cause_graph(session.store, session.branch_id, event.seq, depth=3, limit=8)
        chain = [n["narration"] for n in graph["nodes"] if n["seq"] != event.seq and n["narration"]]
        if chain:
            lines.append("What led here: " + " Then: ".join(chain[-4:]))
    return "\n".join(lines)


class PetitionDesk:
    def __init__(self, studio, town) -> None:
        self.studio = studio
        self.town = town
        self.asked: dict[str, str] = {}  # petition id -> decision id
        self._tasks: list[asyncio.Task] = []

    def sync(self) -> list[str]:
        """Open a decision for each new petition; withdraw those the world has closed."""
        state = self.town.session.state
        opened: list[str] = []
        waiting = {p.id: p for p in petitions.open_petitions(state)}
        for pid, petition in waiting.items():
            if pid in self.asked:
                continue
            who = state.entities[petition.by].name
            decision = Decision(
                id="", agent_id=petition.by, kind="petition",
                question=f"{who} asks the god ({petition.kind}): {petition.text}",
                options=list(POWERS), context=card(self.town, petition),
            )
            future = self.studio.ask(decision)
            self.asked[pid] = decision.id
            self._tasks.append(asyncio.create_task(self._carry(future, pid)))
            opened.append(decision.id)
        for pid, did in list(self.asked.items()):
            if pid not in waiting:
                self.studio.cancel_decision(did)
                del self.asked[pid]
        return opened

    async def _carry(self, future, petition_id: str) -> None:
        try:
            decision = await future
        except asyncio.CancelledError:
            return
        power = POWERS.get(decision.answer, "ignore")
        if petitions.get(self.town.session.state, petition_id) is None or not any(
            p.id == petition_id for p in petitions.open_petitions(self.town.session.state)
        ):
            return
        command = decision.note.strip() if power in ("grant", "punish") else ""
        words = decision.note.strip() if power not in ("grant", "punish") else ""
        result = await self.town.answer(petition_id, power, words, command=command)
        self.asked.pop(petition_id, None)
        if getattr(result, "refused", None):
            self.studio.say(f"The world cannot take that: {result.refused}", None, "system")

    async def drain(self) -> None:
        """Wait for answers already given to be carried out (for tests and shutdown)."""
        pending, self._tasks = self._tasks, []
        for task in pending:
            if task.done():
                continue
            try:
                await asyncio.wait_for(asyncio.shield(task), 0.5)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._tasks.append(task)
