"""A rule-driven stand-in for the model, so a world can run with no API access.

It produces valid, varied but shallow behaviour: people wander, talk, work on
whatever is under way and occasionally hand things over. Useful for demos,
for exercising the whole pipeline in tests, and for long invariant runs. It is
not a substitute for a real model when judging how interesting a world is.
"""

import re
from collections.abc import Callable

from tinyworld.core.rng import seeded
from tinyworld.core.state import WorldState
from tinyworld.llm.fake import FakeLLM
from tinyworld.llm.types import LLMRequest

_NUMBERED = re.compile(r"^\d+\. ", re.MULTILINE)
_ACTOR = re.compile(r"Attempted action by \[([^\]]+)\]")

SMALL_TALK = [
    "Have you heard anything new?",
    "Hard times, these.",
    "I do not trust how things are going.",
    "Come by later, we should talk.",
    "Mind your own affairs.",
    "Did you see who was at the square?",
]


def offline_llm(get_state: Callable[[], WorldState], seed: str = "offline") -> FakeLLM:
    """A FakeLLM whose replies are generated from the current world state."""

    def act(request: LLMRequest) -> dict:
        state = get_state()
        agent_id = request.context.agent
        agent = state.entities[agent_id]
        rng = seeded(seed, request.context.tick_seq, agent_id)
        here = agent.location
        others = [p for p in state.people_at(here) if p.id != agent_id]
        exits = sorted(state.neighbors(here))
        works = [
            p for p in state.processes.values()
            if p.status == "active" and p.location in (None, here)
        ]
        roll = rng.random()
        if works and roll < 0.35:
            process = rng.choice(works)
            return {
                "thought": "There is work to be done.",
                "verb": "work",
                "target": process.id,
                "text": f"work on {process.name}",
            }
        if others and roll < 0.65:
            other = rng.choice(others)
            return {
                "thought": f"{other.name} is here.",
                "verb": "speak",
                "text": "pass the time of day",
                "say": {"text": rng.choice(SMALL_TALK), "to": [other.id]},
            }
        if others and agent.inventory and roll < 0.72:
            item = rng.choice(sorted(agent.inventory))
            return {
                "thought": "A small kindness.",
                "verb": "give",
                "target": rng.choice(others).id,
                "args": {"item": item, "quantity": 1},
                "text": "share a little of what I have",
            }
        if exits and roll < 0.92:
            return {
                "thought": "Time to move on.",
                "verb": "move",
                "target": rng.choice(exits),
                "text": "go and see what is happening elsewhere",
                "plan": ["look around", "talk to whoever is there"],
            }
        return {"thought": "Nothing to do.", "verb": "wait", "text": "wait and watch"}

    def importance(request: LLMRequest) -> dict:
        count = len(_NUMBERED.findall(request.user))
        rng = seeded(seed, "importance", request.context.tick_seq, request.context.agent)
        return {"scores": [rng.choice([1, 2, 2, 3, 3, 4, 6]) for _ in range(count)]}

    def conflict(request: LLMRequest) -> dict:
        agents = list(dict.fromkeys(_ACTOR.findall(request.user)))
        return {
            "outcomes": [
                {
                    "agent": agent,
                    "status": "failed",
                    "narration": "",
                    "reason": "they get in each other's way",
                }
                for agent in agents
            ]
        }

    return FakeLLM(
        {
            "agent.act": act,
            "memory.importance": importance,
            "memory.summarize": {
                "text": "Some uneventful days passed in the usual way.",
                "importance": 2,
            },
            "agent.reflect": {
                "insights": [
                    {"text": "Things go on much as before, and I should stay watchful.", "importance": 3}
                ],
                "beliefs": [],
            },
            "gm.adjudicate": {
                "status": "failed",
                "effects": [],
                "narration": "",
                "reason": "nothing comes of it",
                "minutes": 10,
            },
            "gm.conflict": conflict,
        }
    )
