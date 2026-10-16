"""The command console: one line, plain text or a command.

    refine the rival factions     plain text starts a goal (or, on a built world, a change)
    @juno make the old city denser   a message to one agent, read at its next step
    /answer d4 Merge              answer a decision
    /status  /help
    /pause @x  /resume @x  /stop @x  /spawn @x
    /budget 5                     set the goal's spend cap in dollars

Parsing only: the foreman does what a command asks.
"""

import re
from dataclasses import dataclass, field

HELP = [
    "plain text: start a goal, or ask for a change to the built world",
    "@name text: message an agent (it reads it at its next step)",
    "/answer [d4] <option> [text]: answer a decision (the oldest open one if no id)",
    "/status: the goal, the team, spend, what needs you",
    "/pause @x, /resume @x: hold an agent back, or let it go on",
    "/stop @x, /spawn @x: take an agent off shift, or bring it back",
    "/budget <dollars>: cap what this goal may spend",
    "/help: this list",
]


@dataclass
class Command:
    kind: str  # goal | message | answer | status | pause | resume | stop | spawn | budget | help | error
    text: str = ""
    agent: str | None = None
    args: list[str] = field(default_factory=list)


def _agent(token: str, names: dict[str, str]) -> str | None:
    """An agent id for '@juno', 'juno' or 'Juno'."""
    key = token.lstrip("@").strip().lower()
    return names.get(key)


def parse(line: str, names: dict[str, str]) -> Command:
    """``names`` maps every lowercase id and name to an agent id."""
    line = line.strip()
    if not line:
        return Command("error", "type something")
    if line.startswith("@"):
        head, _, rest = line.partition(" ")
        agent = _agent(head, names)
        if agent is None:
            return Command("error", f"no one called {head}")
        if not rest.strip():
            return Command("error", f"say something to {head}")
        return Command("message", rest.strip(), agent)
    if not line.startswith("/"):
        return Command("goal", line)

    word, _, rest = line[1:].partition(" ")
    word = word.lower()
    rest = rest.strip()
    if word in ("status", "help"):
        return Command(word)
    if word in ("pause", "resume", "stop", "spawn"):
        agent = _agent(rest.split()[0], names) if rest else None
        if agent is None:
            return Command("error", f"/{word} needs an agent, like /{word} @juno")
        return Command(word, agent=agent)
    if word == "budget":
        try:
            amount = float(rest)
        except ValueError:
            return Command("error", "/budget needs a number of dollars")
        if amount <= 0:
            return Command("error", "the budget must be more than zero")
        return Command("budget", args=[str(amount)])
    if word == "answer":
        match = re.match(r"^(d\d+)\s+(.*)$", rest)
        if match:
            return Command("answer", match.group(2).strip(), args=[match.group(1)])
        if not rest:
            return Command("error", "/answer needs an option")
        return Command("answer", rest)
    return Command("error", f"unknown command /{word}; try /help")
