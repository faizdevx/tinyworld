"""Evaluating a world that never repeats.

One run proves nothing when every run differs, so these are measures of a run (or of
many) that can be compared across models and over time:

| metric | how |
|---|---|
| outcome spread | fact divergence across N runs (``multiverse.spread``) |
| liveliness | events per resident per day that are not routine |
| disagreement | share of conversations with a refusal, an argument or a threat |
| petition quality | judged: specific to the person, consequential |
| coherence | invariant violations (must be 0), mentions of what the era lacks, bible contradictions |
| readability | share of the day's weightiest events the paper's stories cover |
| cost | calls and money per resident per simulated day |

Judges must come from a different model family than the residents, and are trusted only
after they agree with human labels well enough (``calibrate``).
"""

import re
from collections import defaultdict
from dataclasses import dataclass, field

from pydantic import Field

from tinyworld.agents.persona import persona_of
from tinyworld.core import effects as fx
from tinyworld.core.session import WorldSession
from tinyworld.core.state import Model
from tinyworld.eval import anachronism, invariants
from tinyworld.llm import ledger
from tinyworld.sim import newspaper
from tinyworld.world import petitions

ROUTINE = re.compile(r"\b(sleeps|waits|rests|works at|goes from .* to|walks on|sets out|arrives at|get ready)\b", re.I)
REFUSAL = re.compile(
    r"\b(no|never|refuse|won't|will not|cannot|can't|how dare|liar|get out|leave me|mind your own|not your|enough)\b",
    re.I,
)


# -- liveliness ---------------------------------------------------------------------


def liveliness(session: WorldSession, after: int = 0) -> dict:
    """Events per resident per simulated day that are more than routine."""
    state = session.state
    residents = [p for p in state.people(alive=False) if persona_of(p) is not None]
    events = session.store.events(session.branch_id, after=after)
    if not events or not residents:
        return {"per_resident_day": 0.0, "events": 0}
    days = max((events[-1].sim_time - events[0].sim_time).total_seconds() / 86400, 1e-9)
    lively = []
    for e in events:
        if not e.narration or e.kind == "chronicle":
            continue
        effects = {type(x).__name__ for x in e.effects}
        if effects <= {"AdvanceTime"} or not effects:
            continue
        if e.actor.startswith("person:") and ROUTINE.search(e.narration) and not (effects - {"MoveEntity", "SetPosition", "SetAttr", "AdvanceProcess"}):
            continue
        if e.kind == "system" and effects <= {"SetAttr", "SetRule"}:
            continue
        lively.append(e)
    return {
        "per_resident_day": round(len(lively) / len(residents) / days, 3),
        "events": len(lively), "residents": len(residents), "days": round(days, 2),
    }


# -- disagreement -------------------------------------------------------------------


@dataclass
class Conversation:
    people: tuple
    lines: list = field(default_factory=list)


def conversations(session: WorldSession, after: int = 0, gap_minutes: int = 60) -> list[Conversation]:
    """Runs of speech between the same two people with no long pause."""
    open_: dict[tuple, tuple] = {}
    out: list[Conversation] = []
    for e in session.store.events(session.branch_id, after=after):
        for x in e.effects:
            if not isinstance(x, fx.Utter) or not x.addressees:
                continue
            pair = tuple(sorted({x.speaker, x.addressees[0]}))
            current = open_.get(pair)
            if current is None or (e.sim_time - current[1]).total_seconds() > gap_minutes * 60:
                conv = Conversation(pair)
                out.append(conv)
            else:
                conv = current[0]
            conv.lines.append((x.speaker, x.message_type, x.text))
            open_[pair] = (conv, e.sim_time)
    return [c for c in out if len({s for s, _, _ in c.lines}) > 0]


def disagrees(conv: Conversation) -> bool:
    return any(t in ("threaten", "lie") or REFUSAL.search(text) for _, t, text in conv.lines)


def disagreement(session: WorldSession, after: int = 0) -> dict:
    convs = conversations(session, after)
    if not convs:
        return {"conversations": 0, "share": 0.0}
    n = sum(1 for c in convs if disagrees(c))
    return {"conversations": len(convs), "with_disagreement": n, "share": round(n / len(convs), 3)}


# -- coherence ------------------------------------------------------------------------


def coherence(session: WorldSession, bible=None) -> dict:
    out = {
        "invariant_violations": len(invariants.check_log(session.store, session.branch_id)),
        "anachronisms": len([a for a in anachronism.scan(session.store, session.branch_id) if not a.by_god]),
    }
    if bible is not None:
        from tinyworld.genesis import critic

        out["bible_findings_blocking"] = len([f for f in critic.check(bible) if f.blocking])
    return out


# -- readability ----------------------------------------------------------------------


def readability(session: WorldSession, editions: dict[str, newspaper.Edition]) -> dict:
    """How much of each day's weightiest events the paper's stories account for, and whether it invents any."""
    from datetime import date

    events = session.store.events(session.branch_id)
    shares, invented = [], 0
    for day, edition in sorted(editions.items()):
        invented += len(newspaper.check(edition, events))
        todays = newspaper.day_events(events, date.fromisoformat(day))
        top = [e for e in sorted(todays, key=lambda e: (-newspaper.weight(e)[0], e.seq))[:5] if newspaper.weight(e)[0] >= 3.0]
        cited = {s for st in edition.stories for s in st.events}
        if top:
            shares.append(len([e for e in top if e.seq in cited]) / len(top))
    return {
        "editions": len(editions), "invented_events": invented,
        "coverage_of_weightiest_events": round(sum(shares) / len(shares), 3) if shares else None,
    }


# -- cost -----------------------------------------------------------------------------


def cost(session: WorldSession) -> dict:
    state = session.state
    residents = max(1, len([p for p in state.people(alive=False) if persona_of(p) is not None]))
    start = session.store.initial_state(session.branch_id).sim_time
    days = max((state.sim_time - start).total_seconds() / 86400, 1e-9)
    used = ledger.total(session.store, session.branch_id, own_only=True)
    return {
        "calls": used.calls, "dollars": round(used.cost, 4),
        "calls_per_resident_day": round(used.calls / residents / days, 2),
        "dollars_per_resident_day": round(used.cost / residents / days, 5),
    }


# -- petitions, judged ---------------------------------------------------------------


class Verdict(Model):
    specific: bool = False
    consequential: bool = False
    why: str = ""


def family(model: str) -> str:
    """The maker of a model, by its id: 'google/gemini-3' and 'gemini-2.5-flash' are both gemini."""
    name = model.lower().split("/")[-1]
    for known in ("claude", "gemini", "qwen", "llama", "mistral", "gpt", "nemotron", "deepseek", "gemma", "phi"):
        if known in name:
            return known
    return name.split("-")[0]


class Judge:
    """Scores petitions. It must be a different family from the residents; and it is trusted only once calibrated."""

    def __init__(self, llm, judge_model: str, resident_models: list[str]) -> None:
        clash = [m for m in resident_models if family(m) == family(judge_model)]
        if clash:
            raise ValueError(f"the judge ({judge_model}) is the same family as the residents' model ({clash[0]})")
        self.llm = llm
        self.model = judge_model
        self.trusted = False
        self.agreement: float | None = None

    async def score(self, session: WorldSession, petition: petitions.Petition) -> Verdict:
        from tinyworld.agents.persona import render
        from tinyworld.llm.types import CallContext

        state = session.state
        person = state.entities[petition.by]
        persona = persona_of(person)
        prompt = (
            "A resident of a simulated world made this petition to the god.\n\n"
            f"Who they are: {render(person, persona) if persona else person.name}\n"
            f"The petition ({petition.kind}): {petition.text}\n"
            f"What came of it: {petition.status}, {petition.answer or 'no answer'}.\n\n"
            "specific: does it name something particular to this person's situation (a person, a thing, a place, "
            "a fear), rather than a generic prayer?\nconsequential: was it about something that would matter to "
            "them or others if it went one way or the other?"
        )
        reply = await self.llm.call(
            "eval.petition", Verdict, system="You judge the quality of a petition in a simulation. Answer in JSON.",
            user=prompt, context=CallContext(session.branch_id, state.seq, "judge"), fallback=Verdict(), max_tokens=300,
        )
        return reply.value

    def calibrate(self, judged: list[bool], human: list[bool], min_labels: int = 20, min_kappa: float = 0.6) -> dict:
        res = calibrate(judged, human, min_labels, min_kappa)
        self.agreement = res["kappa"]
        self.trusted = res["trusted"]
        return res


def calibrate(judged: list[bool], human: list[bool], min_labels: int = 20, min_kappa: float = 0.6) -> dict:
    """Agreement of a judge with human labels: raw agreement and Cohen's kappa. Trusted if enough labels and kappa high."""
    n = len(judged)
    if n != len(human) or n == 0:
        raise ValueError("a judge and the human labels must cover the same items")
    agree = sum(1 for a, b in zip(judged, human) if a == b) / n
    pj, ph = sum(judged) / n, sum(human) / n
    chance = pj * ph + (1 - pj) * (1 - ph)
    kappa = 1.0 if chance == 1 else (agree - chance) / (1 - chance)
    return {"n": n, "agreement": round(agree, 3), "kappa": round(kappa, 3), "trusted": n >= min_labels and kappa >= min_kappa}


def rule_judge(session: WorldSession, petition: petitions.Petition) -> Verdict:
    """A judge that needs no model: specific if it shares a content word with its petitioner's own words
    more than with anyone else's; consequential if the answer moved something. For checking the harness."""
    state = session.state
    person = state.entities[petition.by]
    persona = persona_of(person)
    own = set(w.lower().strip(".,;:") for t in ((persona.goals + persona.fears) if persona else []) for w in t.split() if len(w) > 4)
    words = set(w.lower().strip(".,;:") for w in petition.text.split() if len(w) > 4)
    specific = bool(words & own)
    return Verdict(specific=specific, consequential=petition.status == "answered" and petition.answer in ("grant", "punish", "sign"))


async def petition_quality(session: WorldSession, judge=None) -> dict:
    ps = petitions.all_petitions(session.state)
    if not ps:
        return {"petitions": 0}
    verdicts = [(await judge.score(session, p)) if isinstance(judge, Judge) else rule_judge(session, p) for p in ps]
    return {
        "petitions": len(ps),
        "specific": round(sum(v.specific for v in verdicts) / len(ps), 3),
        "consequential": round(sum(v.consequential for v in verdicts) / len(ps), 3),
        "judge": judge.model if isinstance(judge, Judge) else "rules",
        "judge_trusted": judge.trusted if isinstance(judge, Judge) else None,
    }


async def report(session: WorldSession, *, after: int = 0, editions=None, bible=None, judge=None) -> dict:
    out = {
        "liveliness": liveliness(session, after),
        "disagreement": disagreement(session, after),
        "coherence": coherence(session, bible),
        "cost": cost(session),
        "petitions": await petition_quality(session, judge),
    }
    if editions is not None:
        out["readability"] = readability(session, editions)
    return out
