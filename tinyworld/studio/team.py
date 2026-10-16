"""The foreman: a visible team of agents that builds a world, with you in the loop.

A goal (a premise) becomes a task graph. Agents pick up ready tasks and work
them with tools: search the web, read notes, write sections of the world bible,
review each other's work, message each other, and ask you when a call is
genuinely yours. All of it goes to a *draft*. Nothing becomes the world until
you press Merge.

The foreman owns the scheduling and the rules (permissions, budgets, the merge
gate); the agents own the thinking. A viewer is only a window onto
``Studio.bus``.
"""

import asyncio
import hashlib
import json
import re
from datetime import datetime

from pydantic import ValidationError

from tinyworld.genesis import critic
from tinyworld.genesis.bible import (
    ARTIFACTS, SECTION_BRIEFS, SECTIONS, Bible, BibleStore, Critique, Finding,
)
from tinyworld.genesis.research import SearchHit, SearchProvider
from tinyworld.llm.structured import StructuredLLM
from tinyworld.llm.types import CallContext
from tinyworld.studio import console, diffing, policy, shapes
from tinyworld.studio.protocol import (
    MERGE_OPTIONS, PERMISSION_OPTIONS, Agent, AgentState, Decision, Station, Task,
)
from tinyworld.studio.session import AgentSession, SessionResult, Tool
from tinyworld.studio.state import Studio

CAST: list[tuple[str, str, str, str, str]] = [
    # id, name, role, title, colour
    ("marlow", "Marlow", "lead", "Lead architect", "#c9a227"),
    ("iris", "Iris", "researcher", "Researcher", "#2fa3a0"),
    ("ash", "Ash", "researcher", "Researcher", "#4f9f7a"),
    ("juno", "Juno", "cartographer", "Cartographer", "#8fa98b"),
    ("sage", "Sage", "historian", "Historian", "#d97757"),
    ("otto", "Otto", "economist", "Economist", "#6b8ec9"),
    ("wren", "Wren", "caster", "Casting director", "#b06ab3"),
    ("vera", "Vera", "critic", "Critic", "#c94c4c"),
]
OWNER = {
    "premise": "marlow", "divergence": "sage", "digest": "marlow",
    "geography": "juno", "politics": "sage", "culture": "sage",
    "economy": "otto", "technology": "otto",
    "factions": "wren", "figures": "wren", "tensions": "wren",
}
# Which tool puts an agent where, and in what state. Derived, never self-reported.
TOOL_STATE: dict[str, tuple[AgentState, Station]] = {
    "web_search": ("researching", "web"),
    "fetch_page": ("researching", "web"),
    "read_memory": ("reading", "library"),
    "write_memory": ("writing", "library"),
    "read_draft": ("reading", "drafting"),
    "read_live": ("reading", "drafting"),
    "write_section": ("writing", "drafting"),
    "plan_tasks": ("thinking", "wall"),
    "send_message": ("thinking", "wall"),
    "ask_user": ("waiting_user", "podium"),
    "check_draft": ("reviewing", "review"),
    "review_draft": ("reviewing", "review"),
    "request_fix": ("reviewing", "review"),
}
WRITABLE = ["premise", "divergence", *SECTIONS, "digest"]
MAX_ATTEMPTS = 3

# How each kind of job is done, step by step. A clear end matters most: a model
# that does not know when it is finished keeps searching until it runs out.
PROCEDURE = {
    "research": (
        "How to do it:\n"
        "1. web_search at most three times, each a different question.\n"
        "2. fetch_page the one or two most useful results (snippets count too).\n"
        "3. write_memory three to six notes: one concrete fact each, with where it came from.\n"
        "4. finish. Do not keep searching once you have notes worth keeping."
    ),
    "section": (
        "How to do it:\n"
        "1. read_memory for the team's notes, and read_draft for sections this one depends on.\n"
        "2. write_section with the whole section as one JSON object. Keep it compact: "
        "short descriptions, and no more than eight items in any list.\n"
        "3. If it is not saved, fix exactly what the reply says and write it again.\n"
        "4. finish as soon as it is saved."
    ),
    "digest": (
        "How to do it:\n"
        "1. read_draft the sections.\n"
        "2. write_section digest: an overview paragraph and a few topics.\n"
        "3. finish."
    ),
    "review": (
        "How to do it:\n"
        "1. check_draft, then review_draft.\n"
        "2. request_fix only for problems that would stop the world being simulated, "
        "at most once per section.\n"
        "3. finish with a one-line verdict. A review is done once you have read the draft."
    ),
    "plan": (
        "How to do it:\n"
        "1. write_section premise (when there is none yet).\n"
        "2. plan_tasks: the research and the sections, with dependencies.\n"
        "3. ask_user only for a choice that is genuinely the user's.\n"
        "4. finish."
    ),
}
# Room for one reply. A section goes out whole inside the reply, so it needs room.
STEP_TOKENS = {"section": 7000, "digest": 3000, "plan": 5000, "review": 2000, "research": 1500}
# "Shall I go on?" is not a question for the user.
CONFIRMATION = re.compile(
    r"^\s*(do you want (me )?to|shall i|should i|can i|may i|is it ok(ay)? (if|to)|would you like me to)"
    r"\b.*\b(proceed|continue|start|begin|go ahead|carry on|move on|do (this|that|it))\b",
    re.IGNORECASE,
)
# Two searches are "the same" when most of their words are.
NEAR_DUPLICATE = 0.6
MAX_FIX_ROUNDS = 2
BUDGET_STEPS = ["Add $1", "Add $5", "Stop"]


def standard_plan(research_topics: list[str], *, touch: list[str] | None = None) -> list[dict]:
    """The usual shape of a world build, as plan_tasks entries (deps by index).

    ``touch`` limits the plan to those sections, for changing a world that
    already exists instead of building one.
    """
    tasks: list[dict] = []
    for topic in research_topics:
        tasks.append({"title": f"Research: {topic}", "kind": "research"})
    n = len(tasks)
    research = list(range(n))
    if touch is not None:
        index: dict[str, int] = {}
        for section in touch:
            tasks.append({"title": f"Update {section}", "kind": "section",
                          "section": section, "deps": research})
            index[section] = len(tasks) - 1
        tasks.append({"title": "Review the draft", "kind": "review",
                      "deps": list(index.values())})
        return tasks
    tasks.append({"title": "What changes: the divergence", "kind": "section",
                  "section": "divergence", "deps": research})
    div = len(tasks) - 1
    index = {}
    for section in ("geography", "politics", "economy", "technology", "culture", "factions"):
        tasks.append({"title": f"Write {section}", "kind": "section",
                      "section": section, "deps": [div, *research]})
        index[section] = len(tasks) - 1
    tasks.append({
        "title": "Write figures", "kind": "section", "section": "figures",
        "deps": [index["geography"], index["factions"], index["economy"]],
    })
    index["figures"] = len(tasks) - 1
    tasks.append({"title": "Write tensions", "kind": "section", "section": "tensions",
                  "deps": [index["figures"]]})
    index["tensions"] = len(tasks) - 1
    tasks.append({"title": "Review the draft", "kind": "review",
                  "deps": list(index.values())})
    tasks.append({"title": "Write the digest", "kind": "digest", "section": "digest",
                  "deps": [len(tasks) - 1]})
    return tasks


class Foreman:
    def __init__(
        self,
        studio: Studio,
        llm: StructuredLLM,
        search: SearchProvider,
        *,
        max_parallel: int = 3,
        step_cap: int = 10,
        auto_answer: bool = False,
        llm_for: dict[str, StructuredLLM] | None = None,
        answers: dict[str, str] | None = None,
        limits: policy.Limits | None = None,
        trial_ticks: int = 12,
        now=datetime.now,
    ) -> None:
        self.studio = studio
        self.llm = llm
        self.search = search
        self.max_parallel = max_parallel
        self.step_cap = step_cap
        self.auto_answer = auto_answer
        # Individual agents may run on a different model (an open-weight researcher
        # under a hosted lead).
        self.llm_for = llm_for or {}
        # Answers fixed in advance, by question text. A replay uses them.
        self.answers = answers or {}
        self.limits = limits or policy.Limits()
        self.trial_ticks = trial_ticks
        self._now = now
        self._active: dict[str, asyncio.Task] = {}
        self._hits: dict[str, SearchHit] = {}
        self._runner: asyncio.Task | None = None
        self._fix_rounds = 0
        self._findings: list[Finding] = []
        self._budget_asked = False
        # A question about a site that is already out, by domain.
        self._asking: dict[str, asyncio.Future] = {}
        # Searches made per task, so a retry is told what was already tried.
        self._queries: dict[str, list[str]] = {}
        # Planning tasks that have already put their plan on the wall.
        self._planned: set[str] = set()
        # Sections each review task has already sent back.
        self._fixes_asked: dict[str, set[str]] = {}
        # The result ids of each task's last search, so "fetch the first one" works.
        self._latest: dict[str, list[str]] = {}
        self.store = studio.store
        self.world_id = studio.world_id
        self._ensure_cast()

    # -- cast and goal --------------------------------------------------

    def _ensure_cast(self) -> None:
        have = {a.id for a in self.studio.data.agents}
        for agent_id, name, role, title, colour in CAST:
            if agent_id not in have:
                self.studio.add_agent(
                    Agent(id=agent_id, name=name, role=role, title=title, color=colour)
                )

    def names(self) -> dict[str, str]:
        """Every lowercase id and name, mapped to an agent id."""
        out: dict[str, str] = {}
        for agent in self.studio.data.agents:
            out[agent.id.lower()] = agent.id
            out[agent.name.lower()] = agent.id
        return out

    def _live(self) -> Bible | None:
        bibles = BibleStore(self.store)
        if bibles.get(self.world_id, "digest") is None:
            return None
        return bibles.load(self.world_id)

    def _live_sections(self) -> dict[str, dict]:
        live = self._live()
        if live is None:
            return {}
        out = {}
        for section in ARTIFACTS:
            if section == "critique":
                continue
            value = getattr(live, section, None)
            if value is not None:
                out[section] = value.model_dump(mode="json")
        return out

    def submit(self, goal_text: str, *, budget: float | None = None) -> None:
        """Start a build, or a change to a world that already exists."""
        if self._runner is not None and not self._runner.done():
            raise RuntimeError("the team is already working on a goal")
        studio = self.studio
        goal = studio.set_goal(goal_text)
        if budget is not None:
            studio.update_goal(budget=budget)
        live = self._live_sections()
        # The live world as it is now: a draft is judged against this, and a
        # merge is refused if it moved while the team worked.
        studio.data.base_hash = self._hash(live)
        studio.data.base_live = live
        studio.data.draft = {k: dict(v) for k, v in live.items()} if live else {}
        # A fresh draft version for this goal, starting from the live world.
        studio.data.draft_version = -(studio.data.counters.get("g", 1))
        studio.data.trial = {}
        bibles = BibleStore(self.store)
        for section, content in studio.data.draft.items():
            if section in ARTIFACTS:
                bibles.put_at(
                    self.world_id, studio.data.draft_version, section,
                    ARTIFACTS[section].model_validate(content),
                )
        studio.data.fetches = studio.data.searches = 0
        studio.data.web_mode = "ask"
        self._fix_rounds = 0
        self._budget_asked = False
        brief = f"The premise to build a world from:\n{goal_text}"
        if live:
            brief = (
                "A world already exists. Change only what the goal needs; keep the rest "
                f"as it is.\nThe goal:\n{goal_text}"
            )
        task = studio.graph.create(
            "Plan the change" if live else "Plan the world", kind="plan",
            created_by="user", priority=10, description=brief,
        )
        studio.task_changed(task.id)
        studio.log("you", "goal", goal_text)
        studio.say(f"New goal: {goal_text}", None, "system")
        _ = goal
        self.start()

    @staticmethod
    def _hash(sections: dict[str, dict]) -> str:
        return hashlib.sha1(json.dumps(sections, sort_keys=True).encode()).hexdigest()

    def start(self) -> None:
        if self._runner is None or self._runner.done():
            self._runner = asyncio.create_task(self.run())

    async def wait(self) -> None:
        if self._runner is not None:
            await self._runner

    async def stop(self) -> None:
        if self._runner is not None:
            self._runner.cancel()
        for work in list(self._active.values()):
            work.cancel()
        await asyncio.gather(
            *(w for w in [self._runner, *self._active.values()] if w is not None),
            return_exceptions=True,
        )
        self._active.clear()

    # -- the team: pause, stop, bring back ------------------------------

    def pause_agent(self, agent_id: str) -> None:
        self.studio.set_agent(agent_id, paused=True)
        self.studio.log("you", "pause", agent_id)

    def resume_agent(self, agent_id: str) -> None:
        self.studio.set_agent(agent_id, paused=False, active=True)
        self.studio.log("you", "resume", agent_id)

    async def stop_agent(self, agent_id: str) -> None:
        """Take an agent off shift. What it was doing goes back on the wall."""
        studio = self.studio
        studio.set_agent(agent_id, active=False, state="idle", station="lounge", activity="")
        for task_id, work in list(self._active.items()):
            if studio.graph.get(task_id).assignee == agent_id:
                work.cancel()
                await asyncio.gather(work, return_exceptions=True)
                self._active.pop(task_id, None)
                studio.graph.move(task_id, "todo", assignee=None)
                studio.task_changed(task_id)
        studio.log("you", "stop", agent_id)

    # -- scheduling -----------------------------------------------------

    def _owner_for(self, task: Task) -> str | None:
        """The agent who should take this task, if one is free."""
        busy = {self.studio.graph.get(tid).assignee for tid in self._active}
        if task.kind == "research":
            candidates = ["iris", "ash"]
        elif task.kind in ("plan", "digest"):
            candidates = ["marlow"]
        elif task.kind == "review":
            candidates = ["vera"]
        else:
            candidates = [OWNER.get(task.section or "", "marlow")]
        for agent_id in candidates:
            try:
                agent = self.studio.agent(agent_id)
            except KeyError:
                continue
            if agent.active and not agent.paused and agent_id not in busy:
                return agent_id
        return None

    def _dispatch(self) -> None:
        graph = self.studio.graph
        for task in graph.ready():
            if len(self._active) >= self.max_parallel:
                return
            owner = self._owner_for(task)
            if owner is None:
                continue
            graph.move(task.id, "doing", assignee=owner)
            self.studio.task_changed(task.id)
            self._active[task.id] = asyncio.create_task(self._work(task.id, owner))

    # -- budgets --------------------------------------------------------

    def _over_budget(self) -> str | None:
        goal = self.studio.data.goal
        if goal is None:
            return None
        spent = self.studio.spend()[0]
        if goal.budget is not None and spent >= goal.budget:
            return f"spent ${spent:.2f} of ${goal.budget:.2f}"
        if self.studio.spend()[1] >= self.limits.max_steps:
            return f"made {self.studio.spend()[1]} model calls (limit {self.limits.max_steps})"
        return None

    async def _budget_gate(self, reason: str) -> bool:
        """Ask whether to go on past a limit. False means stop here."""
        studio = self.studio
        decision = Decision(
            id="", agent_id="marlow", kind="permission",
            question=f"The team has reached a limit: {reason}. Keep going?",
            options=list(BUDGET_STEPS),
            context="Nothing new starts until you answer. Work in progress finishes.",
        )
        future = studio.ask(decision)
        studio.update_goal(status="paused")
        self._set("marlow", "waiting_user", "podium", "budget reached")
        self._preset(decision)
        answered = await future
        studio.log("you", "budget", f"{reason}: {answered.answer}")
        if answered.answer == "Stop":
            studio.say("Stopped at the budget.", "marlow", "system")
            return False
        add = 5.0 if answered.answer == "Add $5" else 1.0
        goal = studio.data.goal
        if goal is not None and goal.budget is not None:
            studio.update_goal(budget=round(goal.budget + add, 2))
        self.limits.max_steps += 200
        studio.update_goal(status="running")
        self._set("marlow", "idle", "lounge", "")
        return True

    def _preset(self, decision: Decision) -> None:
        """Answer straight away when an answer is fixed in advance, or when automatic."""
        known = self.answers.get(decision.question)
        if known is not None:
            self.studio.answer(decision.id, known)
        elif self.auto_answer:
            self.studio.answer(
                decision.id, decision.options[0] if decision.options else "",
                "go with your judgement",
            )

    async def run(self) -> None:
        graph = self.studio.graph
        self.studio.update_goal(status="running")
        while True:
            reason = self._over_budget()
            if reason is None:
                self._dispatch()
            elif not self._active:
                if not await self._budget_gate(reason):
                    self.studio.update_goal(status="paused")
                    return
                continue
            if self._active:
                done, _ = await asyncio.wait(
                    list(self._active.values()), return_when=asyncio.FIRST_COMPLETED
                )
                for tid, work in list(self._active.items()):
                    if work in done:
                        self._active.pop(tid)
                        exc = work.exception() if not work.cancelled() else None
                        if exc is not None:
                            self.studio.say(f"a task crashed: {exc!r}", None, "system")
                continue
            if graph.finished():
                break
            stuck = [t for t in graph.all() if t.status not in ("done", "cancelled")]
            self.studio.say(
                "The team is stuck: " + "; ".join(
                    f"{t.title} ({t.status}{': ' + t.blocked_reason if t.blocked_reason else ''})"
                    for t in stuck[:4]
                ),
                None, "system",
            )
            self.studio.update_goal(status="failed")
            return
        await self._merge_stage()

    # -- one task -------------------------------------------------------

    def _set(self, agent_id: str, state: AgentState, station: Station, activity: str = "",
             task_id: str | None = None) -> None:
        self.studio.set_agent(
            agent_id, state=state, station=station, activity=activity, task_id=task_id
        )

    def _llm_for(self, agent_id: str) -> StructuredLLM:
        return self.llm_for.get(agent_id, self.llm)

    def _llm_role(self, agent: Agent, task: Task) -> str:
        # A task that already failed once goes to the strongest tier.
        if task.attempts >= 1:
            return "studio.escalate"
        return f"studio.{agent.role}"

    def _refresh_cost(self, agent_id: str) -> None:
        dollars, calls = self.studio.spend_of(agent_id)
        self.studio.set_agent(agent_id, cost=round(dollars, 6), calls=calls)

    async def _work(self, task_id: str, agent_id: str) -> None:
        studio = self.studio
        task = studio.graph.get(task_id)
        agent = studio.agent(agent_id)
        self._set(agent_id, "thinking", "wall", task.title, task_id)
        studio.say(f"takes on: {task.title}", agent_id, "task")

        def on_step(index: int, tool: str, args: dict) -> None:
            state, station = TOOL_STATE.get(tool, ("thinking", "wall"))
            self._set(agent_id, state, station, _describe(tool, args), task_id)
            studio.set_agent(agent_id, steps=index)
            studio.say(_describe(tool, args), agent_id, "tool")
            self._refresh_cost(agent_id)

        session = AgentSession(
            self._llm_for(agent_id), world_id=self.world_id, agent_id=agent_id,
            name=agent.name, role=agent.title or agent.role,
            tools=self._tools(task, agent), max_steps=self.step_cap, on_step=on_step,
            llm_role=self._llm_role(agent, task),
            inbox=lambda: studio.take_messages(agent_id),
            call_id=f"{agent_id}:{task_id}",
            max_tokens=STEP_TOKENS.get(task.kind, 1500),
        )
        try:
            result = await session.run(self._task_text(task), self._world_note())
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            result = SessionResult("failed", error=f"{type(exc).__name__}: {exc}")
        self._refresh_cost(agent_id)
        self._close(task_id, agent_id, result)

    def _close(self, task_id: str, agent_id: str, result: SessionResult) -> None:
        studio = self.studio
        graph = studio.graph
        task = graph.get(task_id)
        produced = self._produced(task, agent_id)
        # Running out of steps after saving the work still counts: the work is there.
        salvaged = result.status == "capped" and produced and task.kind in (
            "research", "section", "digest",
        ) or (
            result.status == "capped" and task.kind == "review"
            and "review_draft" in result.used
        )
        ok = (result.status == "finished" and produced) or salvaged
        if salvaged:
            result.summary = f"ran out of steps, but the work was saved ({task.kind})"
        if ok:
            if task.kind == "plan" and len(graph.all()) == 1:
                # The lead made no plan of its own: use the usual shape. On an
                # existing world, touch only the part a change most often needs.
                touch = ["factions"] if studio.data.base_live else None
                self._plan(standard_plan(self._topics(), touch=touch), "marlow")
            elif task.kind == "plan" and not studio.data.base_live:
                self._complete_plan()
            if task.kind == "plan" and "rebase" in task.title.lower():
                # The team has looked at the changed world; judge against it from now on.
                studio.data.base_live = self._live_sections()
                studio.data.base_hash = self._hash(studio.data.base_live)
            graph.move(task_id, "done", summary=result.summary)
            studio.say(f"finished: {result.summary}", agent_id, "task")
            self._set(agent_id, "idle", "lounge", "")
        else:
            attempts = task.attempts + 1
            reason = result.error or (
                "the work was not produced" if result.status == "finished"
                else f"{result.status} after {result.steps} steps"
            )
            if attempts < MAX_ATTEMPTS:
                graph.move(task_id, "todo", attempts=attempts, assignee=None,
                           blocked_reason=reason)
                studio.say(f"will try {task.title!r} again: {reason}", agent_id, "task")
            elif task.kind == "research":
                # Writers can work from what they know. Say so, and let them.
                graph.move(task_id, "done", attempts=attempts, blocked_reason=reason,
                           summary=f"research incomplete: {reason}")
                studio.say(
                    f"gave up on {task.title!r} ({reason}); the writers carry on without it",
                    agent_id, "task",
                )
            else:
                graph.move(task_id, "blocked", attempts=attempts, blocked_reason=reason)
                studio.say(f"stuck on {task.title!r}: {reason}", agent_id, "task")
            self._set(agent_id, "error" if attempts >= MAX_ATTEMPTS else "idle",
                      "lounge", reason[:80])
        studio.task_changed(task_id)

    def _produced(self, task: Task, agent_id: str | None = None) -> bool:
        """Did a task that should leave something behind actually leave it?"""
        if task.kind in ("section", "digest") and task.section:
            return task.section in self.studio.data.draft
        if task.kind == "research":
            author = agent_id or task.assignee
            return any(
                m.author == author and task.created_at is not None
                and (m.updated_at is None or m.updated_at >= task.created_at)
                for m in self.studio.data.memory
            )
        if task.kind == "plan":
            return "premise" in self.studio.data.draft or len(self.studio.graph.all()) > 1
        return True

    def _topics(self) -> list[str]:
        goal = self.studio.data.goal.text if self.studio.data.goal else "the setting"
        return [
            f"everyday life and economy ({goal[:60]})",
            f"politics, institutions and power ({goal[:60]})",
            f"technology and what does not exist yet ({goal[:60]})",
        ]

    def _task_text(self, task: Task) -> str:
        head = f"{task.title}\nKIND: {task.kind}" + (
            f" | SECTION: {task.section}" if task.section else ""
        )
        goal = self.studio.data.goal.text if self.studio.data.goal else ""
        body = task.description or ""
        extra = ""
        if task.section in SECTION_BRIEFS:
            extra = "\nWhat this section is: " + SECTION_BRIEFS[task.section]
        if task.section in ARTIFACTS:
            extra += (
                f"\nThe exact JSON shape of {task.section} (use these field names): "
                + shapes.shape(ARTIFACTS[task.section])
            )
        names = self._draft_names()
        if task.section in ("figures", "factions", "tensions", "economy", "politics") and names:
            extra += "\nUse these names exactly as written where you refer to them:\n" + names
        if task.section in shapes.TARGET:
            key, want = shapes.TARGET[task.section]
            extra += (
                f"\nAim for about {want} {key}. If one reply cannot hold them all, write "
                "three, then add more with mode \"append\"."
            )
        if task.kind == "research":
            extra = "\nFind facts about everyday life, institutions, economy and technology."
        procedure = PROCEDURE.get(task.kind)
        if procedure:
            extra += "\n\n" + procedure
        if task.attempts and task.blocked_reason:
            # A retry continues from what was saved; it does not start over.
            saved = [
                m.title for m in self.studio.data.memory if m.author == (task.assignee or "")
            ][-6:]
            tried = self._queries.get(task.id, [])[-6:]
            extra += f"\n\nA previous attempt stopped: {task.blocked_reason}."
            if saved:
                extra += " Notes already saved: " + "; ".join(saved) + "."
            if tried:
                extra += " Searches already made: " + "; ".join(tried) + "."
            extra += " Continue from there; do not repeat it."
        asked = [
            d for d in self.studio.data.decisions
            if d.task_id == task.id and d.kind == "question" and d.status == "answered"
        ]
        if asked:
            extra += "\n\nThe user already answered (do not ask again):\n" + "\n".join(
                f"- {d.question} -> {d.answer}" for d in asked
            )
        return f"{head}\nGoal: {goal}\n{body}{extra}".strip()

    def _draft_names(self) -> str:
        """Places, factions and people already in the draft, for cross-references."""
        draft = self.studio.data.draft
        lines = []
        places = [p.get("name") for p in (draft.get("geography") or {}).get("places", [])]
        if places:
            lines.append("- places: " + ", ".join(p for p in places if p))
        factions = [f.get("name") for f in (draft.get("factions") or {}).get("factions", [])]
        if factions:
            lines.append("- factions: " + ", ".join(f for f in factions if f))
        people = [f.get("name") for f in (draft.get("figures") or {}).get("figures", [])]
        if people:
            lines.append("- people: " + ", ".join(p for p in people if p))
        return "\n".join(lines)

    def _world_note(self) -> str:
        draft = self.studio.data.draft
        premise = draft.get("premise")
        lines = []
        if premise:
            lines.append("Premise (draft): " + json.dumps(premise)[:700])
        div = draft.get("divergence")
        if div:
            lines.append("Divergence (draft): " + str(div.get("summary", ""))[:500])
        return "\n".join(lines)

    # -- planning -------------------------------------------------------

    def _plan(self, entries: list[dict], created_by: str) -> list[str]:
        graph = self.studio.graph
        created: list[str] = []
        by_title: dict[str, str] = {}
        for index, entry in enumerate(entries):
            deps: list[str] = []
            for dep in entry.get("deps", []) or []:
                if isinstance(dep, int) and 0 <= dep < len(created):
                    deps.append(created[dep])
                elif isinstance(dep, str) and dep in by_title:
                    deps.append(by_title[dep])
            kind = entry.get("kind", "custom")
            if kind not in ("research", "section", "review", "digest", "custom"):
                kind = "custom"
            section = entry.get("section")
            if section is not None and section not in WRITABLE:
                section = None
            task = graph.create(
                str(entry.get("title", f"Task {index + 1}")), kind=kind,
                deps=deps, section=section, created_by=created_by,
                description=str(entry.get("description", "")),
            )
            created.append(task.id)
            by_title[task.title] = task.id
            self.studio.task_changed(task.id)
        return created

    def _complete_plan(self) -> list[str]:
        """Add what a world needs and the lead's plan left out, with the usual order.

        A small model's plan reads well and covers little ("develop the
        characters", "define the plot"). The foreman, not the model, makes sure
        every section has a task, that figures wait for places and factions, and
        that a review and a digest come last.
        """
        graph = self.studio.graph
        tasks = graph.all()
        by_section = {t.section: t for t in tasks if t.kind in ("section", "digest") and t.section}
        research = [t.id for t in tasks if t.kind == "research"]
        if not research:
            for topic in self._topics():
                created = graph.create(f"Research: {topic}", kind="research", created_by="marlow")
                research.append(created.id)
                self.studio.task_changed(created.id)
        added: list[str] = []

        def ensure(section: str, deps: list[str], title: str, kind: str = "section") -> str:
            if section in by_section:
                return by_section[section].id
            created = graph.create(title, kind=kind, section=section, deps=deps, created_by="marlow")
            by_section[section] = created
            added.append(section)
            self.studio.task_changed(created.id)
            return created.id

        div = ensure("divergence", research, "What changes: the divergence")
        base = [div, *research]
        for section in ("geography", "politics", "economy", "technology", "culture", "factions"):
            ensure(section, base, f"Write {section}")
        ensure("figures", [by_section[s].id for s in ("geography", "factions", "economy")], "Write figures")
        ensure("tensions", [by_section["figures"].id], "Write tensions")
        review = next((t for t in graph.all() if t.kind == "review"), None)
        section_ids = [by_section[s].id for s in SECTIONS]
        if review is None:
            review = graph.create("Review the draft", kind="review", deps=section_ids, created_by="marlow")
            added.append("review")
            self.studio.task_changed(review.id)
        else:
            # The review must come after every section, whatever the lead said.
            graph.set_deps(review.id, sorted(set(review.deps) | set(section_ids)))
            self.studio.task_changed(review.id)
        ensure("digest", [review.id], "Write the digest", kind="digest")
        if added:
            self.studio.say(
                "The plan was missing " + ", ".join(added) + "; added to the wall.",
                "marlow", "system",
            )
        return added

    # -- tools ----------------------------------------------------------

    def _tools(self, task: Task, agent: Agent) -> list[Tool]:
        studio = self.studio
        agent_id = agent.id

        async def web_search(args: dict) -> str:
            query = str(args.get("query", "")).strip()
            if not query:
                return "give a query"
            if studio.data.searches >= self.limits.max_searches:
                return "the search budget for this goal is used up"
            words = set(query.lower().split())
            for earlier in self._queries.get(task.id, []):
                seen = set(earlier.lower().split())
                if words and seen and len(words & seen) / len(words | seen) >= NEAR_DUPLICATE:
                    return (
                        f"You already searched for nearly this ({earlier!r}). Read a result "
                        "with fetch_page, save what you know with write_memory, or finish."
                    )
            self._queries.setdefault(task.id, []).append(query)
            studio.data.searches += 1
            studio.log(agent_id, "search", query)
            hits = await self.search.search(query, 4)
            if not hits:
                return "no results"
            lines = []
            latest = []
            for hit in hits:
                key = f"r{len(self._hits) + 1}"
                self._hits[key] = hit
                latest.append(key)
                lines.append(f"{key}: {hit.title} - {hit.url}\n    {hit.snippet[:160]}")
            self._latest[task.id] = latest
            return "\n".join(lines) + "\nRead one with fetch_page(id), for example fetch_page(r" + latest[0][1:] + ")."

        def find_hit(args: dict) -> SearchHit | None:
            """A result by id ("r3"), by number (3, or 0 for the first of the last search), or by address."""
            url = str(args.get("url", "")).strip()
            ref = args.get("id", args.get("result", ""))
            if url:
                for hit in self._hits.values():
                    if hit.url == url:
                        return hit
                from tinyworld.genesis.web import public_url

                return SearchHit(url=url, title=url, provider="web") if public_url(url) else None
            text = str(ref).strip().lower()
            if text in self._hits:
                return self._hits[text]
            if text.startswith("r") and text[1:].isdigit():
                return self._hits.get(text)
            if text.isdigit():
                n = int(text)
                latest = self._latest.get(task.id, [])
                if f"r{n}" in self._hits and n > len(latest):
                    return self._hits[f"r{n}"]
                # Small numbers mean a position in the last list of results.
                if latest and n < len(latest):
                    return self._hits[latest[n]] if n == 0 else self._hits[latest[n - 1]]
                return self._hits.get(f"r{n}")
            if text.startswith("http"):
                return find_hit({"url": text})
            return None

        async def fetch_page(args: dict) -> str:
            hit = find_hit(args)
            if hit is None:
                known = ", ".join(self._latest.get(task.id, [])[:6]) or "none yet: use web_search first"
                return f"no such result; give the id of one, for example {known}"
            domain = policy.domain_of(hit.url)
            if not policy.allowed(domain, studio.data.allowed_domains) and studio.data.web_mode == "ask":
                # One question for the whole build, not one per site.
                future = self._asking.get("*")
                first = future is None
                if first:
                    decision = Decision(
                        id="", agent_id=agent_id, kind="permission",
                        question=policy.WEB_QUESTION, options=list(policy.WEB_OPTIONS),
                        context=f"First page asked for: {hit.url}", task_id=task.id,
                    )
                    future = studio.ask(decision)
                    self._asking["*"] = future
                    self._preset(decision)
                self._set(agent_id, "waiting_user", "podium", "may we read the web?", task.id)
                answered = await future
                if first:
                    self._asking.pop("*", None)
                    studio.data.web_mode = {
                        "Allow for this build": "all", "Ask for each site": "per_site",
                    }.get(answered.answer, "none")
                    studio.log("you", "permission", f"web: {answered.answer}")
                    studio.save()
            if studio.data.web_mode == "none" and not policy.allowed(domain, studio.data.allowed_domains):
                return (
                    "The user chose no web pages for this build. Use the search snippets "
                    "and what you know, save notes, and finish."
                )
            if (
                studio.data.web_mode == "per_site"
                and not policy.allowed(domain, studio.data.allowed_domains)
            ):
                # Two agents wanting the same site share one question.
                future = self._asking.get(domain)
                first = future is None
                if first:
                    decision = Decision(
                        id="", agent_id=agent_id, kind="permission",
                        question=policy.permission_text(domain),
                        options=list(PERMISSION_OPTIONS), context=hit.url, task_id=task.id,
                    )
                    future = studio.ask(decision)
                    self._asking[domain] = future
                    self._preset(decision)
                self._set(agent_id, "waiting_user", "podium", f"may I read {domain}?", task.id)
                answered = await future
                if first:
                    self._asking.pop(domain, None)
                    studio.log("you", "permission", f"{domain}: {answered.answer}")
                    if answered.answer == "Always allow" and domain not in studio.data.allowed_domains:
                        studio.data.allowed_domains.append(domain)
                        studio.save()
                if answered.answer == "Deny":
                    return f"the user did not allow reading pages from {domain}"
            if studio.data.fetches >= self.limits.max_fetches:
                return "the page budget for this goal is used up"
            studio.data.fetches += 1
            studio.log(agent_id, "fetch", hit.url)
            text = await self.search.fetch(hit)
            if not text.strip():
                return "the page had no readable text"
            return f"{hit.title} ({hit.url}), first 1500 characters:\n{text[:1500]}"

        async def write_memory(args: dict) -> str:
            title = str(args.get("title", "")).strip()
            body = str(args.get("body", "")).strip()
            if not title or not body:
                return "give a title and a body"
            studio.remember(title, body, agent_id)
            return f"saved note {title!r}"

        async def read_memory(args: dict) -> str:
            found = studio.recall(agent_id, str(args.get("query", "")))
            if not found:
                return "no notes yet"
            return "\n\n".join(f"## {m.title} ({m.author})\n{m.body[:500]}" for m in found)

        async def read_draft(args: dict) -> str:
            section = str(args.get("section", "")).strip()
            if not section:
                return "draft has: " + (", ".join(sorted(studio.data.draft)) or "nothing yet")
            content = studio.data.draft.get(section)
            return json.dumps(content)[:1800] if content else f"{section} is not written yet"

        async def read_live(args: dict) -> str:
            section = str(args.get("section", "")).strip()
            live = self._live_sections()
            if not live:
                return "there is no live world yet"
            if not section:
                return "the live world has: " + ", ".join(sorted(live))
            content = live.get(section)
            return json.dumps(content)[:1800] if content else f"{section} is not in the live world"

        async def write_section(args: dict) -> str:
            section = str(args.get("section", task.section or "")).strip()
            if section not in WRITABLE:
                return f"{section!r} is not a section. Sections: {', '.join(WRITABLE)}"
            content = args.get("content")
            if isinstance(content, str):
                try:
                    content = json.loads(content)
                except ValueError:
                    pass
            if not isinstance(content, dict):
                return (
                    "content must be a JSON object with this shape: "
                    + shapes.shape(ARTIFACTS[section])
                )
            model = ARTIFACTS[section]
            notes: list[str] = []
            content = shapes.normalise(model, content, notes)
            try:
                valid = model.model_validate(content)
            except ValidationError as exc:
                problems = "; ".join(
                    f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}"
                    for e in exc.errors()[:6]
                )
                return (
                    f"{section} was not saved. Fix: {problems}. The shape is: "
                    + shapes.shape(model)
                )
            if str(args.get("mode", "")).lower() == "append" and section in studio.data.draft:
                merged, added = shapes.append(studio.data.draft[section], valid.model_dump(mode="json"))
                try:
                    valid = model.model_validate(merged)
                except ValidationError as exc:
                    return f"could not add to {section}: {str(exc)[:300]}"
                notes.append(f"added {added} item(s) to the existing {section}")
            thin = shapes.too_thin(section, valid.model_dump(mode="json"))
            if thin:
                return (
                    f"{section} was not saved: {thin}. The shape is: " + shapes.shape(model)
                    + (". Corrections made: " + "; ".join(notes[:6]) if notes else "")
                )
            studio.data.draft[section] = valid.model_dump(mode="json")
            if studio.data.draft_version:
                BibleStore(self.store).put_at(
                    self.world_id, studio.data.draft_version, section, valid
                )
            studio.emit("draft.upsert", section=section)
            studio.save()
            short = shapes.short_of_target(section, valid.model_dump(mode="json"))
            done = (
                f" {short}" if short and section == task.section
                else " Your task is done: call finish now." if section == task.section
                else ""
            )
            if notes:
                return (
                    f"{section} saved to the draft, after these corrections: "
                    + "; ".join(notes[:8])
                    + ". Use the real field names next time." + done
                )
            return f"{section} saved to the draft." + done

        async def plan_tasks(args: dict) -> str:
            # One plan per planning task: a second call would put everything up twice.
            if task.id in self._planned:
                return "The plan is already on the wall. Do not plan again; finish now."
            tasks = args.get("tasks")
            if not isinstance(tasks, list) or not tasks:
                return "give a list of tasks: [{title, kind, section?, deps?}]"
            clean, problems = [], []
            for index, entry in enumerate(tasks):
                if not isinstance(entry, dict) or not str(entry.get("title", "")).strip():
                    problems.append(f"task {index}: needs a title")
                    continue
                kind = entry.get("kind")
                if kind not in ("research", "section", "review", "digest"):
                    problems.append(
                        f"task {index} ({entry.get('title')!r}): kind must be research, "
                        "section, review or digest"
                    )
                    continue
                if kind == "section" and entry.get("section") not in WRITABLE:
                    problems.append(
                        f"task {index} ({entry.get('title')!r}): section must be one of "
                        + ", ".join(WRITABLE)
                    )
                    continue
                clean.append(entry)
            ids = self._plan(clean, agent_id) if clean else []
            if ids:
                self._planned.add(task.id)
            reply = f"created {len(ids)} tasks"
            if problems:
                reply += ". Not created: " + "; ".join(problems[:6])
            return reply

        async def send_message(args: dict) -> str:
            target = self.names().get(str(args.get("to", "")).lstrip("@").lower())
            text = str(args.get("text", "")).strip()
            if target is None or not text:
                return "give `to` (a teammate's name) and `text`"
            if target == agent_id:
                return "that is you"
            studio.send(target, text, agent.name)
            return f"told {studio.agent(target).name}; they read it at their next step"

        async def ask_user(args: dict) -> str:
            question = str(args.get("question", "")).strip()
            if not question:
                return "give a question"
            if CONFIRMATION.search(question):
                # Small models ask leave to carry on. The user should not see that.
                return (
                    "Do not ask the user for permission to carry on with your own task: "
                    "decide and continue. Ask only about a choice that is genuinely theirs."
                )
            options = [str(o) for o in (args.get("options") or [])][:4]
            decision = Decision(
                id="", agent_id=agent_id, kind="question", question=question,
                options=options, context=str(args.get("context", ""))[:500],
                task_id=task.id,
            )
            future = studio.ask(decision)
            self._set(agent_id, "waiting_user", "podium", question[:80], task.id)
            self._preset(decision)
            answered = await future
            return f"The user answered: {answered.answer}"

        async def check_draft(args: dict) -> str:
            bible = self._draft_bible()
            found = critic.check(bible)
            if not found:
                return "no mechanical problems"
            return "\n".join(
                f"- [{'BLOCKING' if f.blocking else 'note'}] ({f.section}) {f.text}" for f in found
            )

        async def review_draft(args: dict) -> str:
            bible = self._draft_bible()
            found = await critic.review(
                self._llm_for(agent_id), bible, CallContext(self.world_id, 0, agent_id)
            )
            self._findings = [*critic.check(bible), *found]
            if not found:
                return "the reviewer found nothing"
            return "\n".join(
                f"- [{'BLOCKING' if f.blocking else 'note'}] ({f.kind}, {f.section}) {f.text}"
                for f in found
            )

        async def request_fix(args: dict) -> str:
            section = str(args.get("section", "")).strip()
            note = str(args.get("note", "")).strip()
            if section not in WRITABLE or not note:
                return (
                    f"Nothing sent: give a section from {', '.join(WRITABLE)} and a note. "
                    "If nothing needs fixing, finish."
                )
            # One fix per section per review: asking again just loops.
            asked = self._fixes_asked.setdefault(task.id, set())
            if section in asked:
                return (
                    f"{section} is already being fixed. Send another section back, "
                    "or finish the review."
                )
            if self._fix_rounds >= MAX_FIX_ROUNDS * len(SECTIONS):
                return "Enough rounds of fixes; leave the rest as notes and finish."
            asked.add(section)
            self._fix_rounds += 1
            fix = studio.graph.create(
                f"Fix {section}: {note[:60]}", kind="section", section=section,
                created_by=agent_id, priority=5,
                description=f"The reviewer asks for this change to {section}:\n{note}\n"
                f"Read the draft first, then write the corrected section.",
            )
            studio.task_changed(fix.id)
            return f"asked {OWNER.get(section, 'marlow')} to fix {section}"

        finish = Tool("finish", "finish(summary): the task is done; say what you did", _noop)
        talk = Tool(
            "send_message", "send_message(to, text): tell a teammate something", send_message
        )
        common = [
            Tool("read_memory", "read_memory(query): notes the team has written", read_memory),
            Tool("ask_user", "ask_user(question, options): ask the human; use sparingly", ask_user),
            talk, finish,
        ]
        live_tool = Tool(
            "read_live", "read_live(section): a section of the world as it stands now", read_live
        )
        kind = task.kind
        if kind == "research":
            # No ask_user here: facts are found by searching, not by asking the user.
            return [
                Tool("web_search", "web_search(query): search the web and Wikipedia", web_search),
                Tool("fetch_page", "fetch_page(id): read a result from web_search, by its id (like r3) or its url", fetch_page),
                Tool("write_memory", "write_memory(title, body): save a note with its source", write_memory),
                Tool("read_memory", "read_memory(query): notes the team has written", read_memory),
                talk, finish,
            ]
        if kind == "review":
            return [
                Tool("check_draft", "check_draft(): mechanical problems in the draft", check_draft),
                Tool("review_draft", "review_draft(): a careful read of the whole draft", review_draft),
                Tool("request_fix", "request_fix(section, note): send a section back to be fixed", request_fix),
                Tool("read_draft", "read_draft(section): a section of the draft", read_draft),
                talk, finish,
            ]
        writing = [
            Tool("read_draft", "read_draft(section): a section of the draft", read_draft),
            live_tool,
            Tool("write_section",
                 "write_section(section, content, mode?): save a section; content is a JSON "
                 "object that must match the section's shape; mode \"append\" adds items "
                 "to what is already written", write_section),
        ]
        if kind == "plan":
            return [
                Tool("plan_tasks",
                     "plan_tasks(tasks): create the work as [{title, kind: research|section|"
                     "review|digest, section?, deps?: [index]}]", plan_tasks),
                Tool("write_memory", "write_memory(title, body): save a note", write_memory),
                *writing, *common,
            ]
        return [*writing, *common]

    # -- the draft and the merge ---------------------------------------

    @staticmethod
    def _draft_bible_of(studio: Studio) -> Bible:
        data = {k: v for k, v in studio.data.draft.items() if k in ARTIFACTS}
        try:
            return Bible.model_validate(data)
        except ValidationError:
            return Bible()

    def _draft_bible(self) -> Bible:
        return self._draft_bible_of(self.studio)

    def draft_view(self) -> dict:
        bible = self._draft_bible()
        diffs = diffing.diff(self._live(), self.studio.data.draft)
        return {
            "sections": sorted(self.studio.data.draft),
            "draft": self.studio.data.draft,
            "findings": [f.model_dump() for f in critic.check(bible)],
            "diff": [d.to_dict() for d in diffs],
            "merged_version": self.studio.data.merged_version,
        }

    def _live_changes(self) -> list[str]:
        """Live sections that changed since this goal began."""
        now = self._live_sections()
        base = self.studio.data.base_live
        return sorted(s for s in set(now) | set(base) if now.get(s) != base.get(s))

    def _real_person_findings(self) -> list[Finding]:
        return [f for f in self._findings if f.kind == "real_person" and f.blocking]

    async def _merge_stage(self) -> None:
        studio = self.studio
        changed = self._live_changes()
        if changed:
            # The world moved while the team worked. Settle that before merging.
            studio.say(
                "The live world changed while we worked (" + ", ".join(changed)
                + "). The team will rebase before you merge.", "marlow", "system",
            )
            task = studio.graph.create(
                "Rebase onto the changed world", kind="plan", created_by="marlow", priority=10,
                description="The live world changed in: " + ", ".join(changed)
                + ". Read those sections with read_live, and update the draft only where "
                "it now conflicts. Then finish.",
            )
            studio.task_changed(task.id)
            studio.log("marlow", "conflict", ", ".join(changed))
            await self.run()
            return
        studio.update_goal(status="review")
        bible = self._draft_bible()
        findings = critic.check(bible)
        # Try the world before asking to merge it, as a CI run is shown with a review.
        from tinyworld.studio.trial import trial as try_world

        studio.say("Trying the draft world before the merge…", "vera", "system")
        report = await try_world(bible, ticks=self.trial_ticks, goal=studio.data.goal.text)
        studio.data.trial = report.to_dict()
        studio.save()
        studio.emit("trial", report=report.to_dict())
        studio.say(report.line(), "vera", "system")
        blocking = [f for f in findings if f.blocking]
        diffs = diffing.diff(self._live(), studio.data.draft)
        real = self._real_person_findings()
        summary = (
            f"Draft world: {len(bible.geography.places)} places, "
            f"{len(bible.figures.figures)} people, {len(bible.factions.factions)} factions. "
            + (f"{len(blocking)} blocking problem(s) remain." if blocking else "No blocking problems.")
            + "\n" + report.line()
            + "\n" + diffing.summary(diffs)
        )
        options = list(MERGE_OPTIONS)
        if real:
            options = ["Request changes", "Merge anyway", "Reject"]
            summary += (
                "\nThe reviewer flagged real, living people: "
                + "; ".join(f.text[:80] for f in real[:3])
            )
        decision = Decision(
            id="", agent_id="marlow", kind="merge",
            question="Merge this draft as the world?", options=options, context=summary,
        )
        future = studio.ask(decision)
        self._set("marlow", "waiting_user", "podium", "waiting for your decision")
        self._preset(decision)
        answered = await future
        self._set("marlow", "idle", "lounge", "")
        if answered.answer in ("Merge", "Merge anyway"):
            if answered.answer == "Merge anyway":
                studio.log("you", "override", "merged with real-person findings open")
            send_back, keep = self._partial(answered.note)
            version = self.apply_merge(findings, sections=keep)
            studio.log("you", "merge", f"bible version {version}")
            if send_back:
                for section, note in send_back.items():
                    fix = studio.graph.create(
                        f"Revise {section}: {note[:60]}", kind="section", section=section,
                        created_by="user", priority=5,
                        description=f"The user merged the rest and sent this back:\n{note}",
                    )
                    studio.task_changed(fix.id)
                studio.say(
                    "Merged the rest. " + ", ".join(send_back) + " go back to the team.",
                    "marlow", "system",
                )
                studio.data.base_live = self._live_sections()
                studio.data.base_hash = self._hash(studio.data.base_live)
                await self.run()
                return
            studio.update_goal(status="merged", progress=1.0)
            studio.say("The world is merged. It is ready to seed.", "marlow", "system")
        elif answered.answer == "Request changes":
            note = answered.note or "the user asked for changes"
            task = studio.graph.create(
                "Apply the requested changes", kind="plan", created_by="user", priority=10,
                description=f"The user reviewed the draft and asked for changes.\n{note}",
            )
            studio.task_changed(task.id)
            studio.say("Changes requested; the team is back at work.", "marlow", "system")
            await self.run()
        else:
            studio.update_goal(status="rejected")
            studio.log("you", "reject", "draft rejected")
            studio.say("The draft was rejected. Nothing was merged.", "marlow", "system")

    @staticmethod
    def _partial(note: str) -> tuple[dict[str, str], list[str] | None]:
        """(sections sent back with a note, sections to merge) from the answer's note.

        The note is JSON: {"merge": [...], "send_back": {section: note}}. Anything
        else, or nothing, means merge everything.
        """
        try:
            data = json.loads(note) if note.strip().startswith("{") else {}
        except ValueError:
            data = {}
        back = {
            s: str(n) for s, n in (data.get("send_back") or {}).items() if s in WRITABLE
        }
        merge = data.get("merge")
        keep = [s for s in merge if s in WRITABLE] if isinstance(merge, list) else None
        if back and keep is None:
            keep = [s for s in WRITABLE if s not in back]
        return back, keep

    def apply_merge(
        self, findings: list[Finding] | None = None, *, sections: list[str] | None = None
    ) -> int:
        """Write the draft into the world's bible as a new version. The only way in."""
        bibles = BibleStore(self.store)
        world = self.world_id
        if bibles.get(world, "digest") is not None:
            bibles.new_version(world)
        for section, content in self.studio.data.draft.items():
            if sections is not None and section not in sections:
                continue
            bibles.put(world, section, ARTIFACTS[section].model_validate(content))
        bible = self._draft_bible()
        bibles.put(world, "critique", Critique(findings=findings or critic.check(bible)))
        start = bible.premise.start_date
        try:
            when = datetime.fromisoformat(start).replace(hour=8)
        except ValueError:
            when = None
        branches = self.store.query("SELECT 1 FROM branches WHERE world_id=?", (world,))
        if when is not None and not branches:
            self.store.execute(
                "UPDATE worlds SET start_time=? WHERE id=?", (when.isoformat(), world)
            )
        version = bibles.version(world)
        self.studio.data.merged_version = version
        self.studio.save()
        return version

    # -- the console ----------------------------------------------------

    async def command(self, line: str) -> list[str]:
        """Run one console line. Returns what to show the user."""
        studio = self.studio
        cmd = console.parse(line, self.names())
        if cmd.kind == "error":
            return [cmd.text]
        if cmd.kind == "help":
            return console.HELP
        if cmd.kind == "goal":
            try:
                self.submit(cmd.text)
            except RuntimeError as exc:
                return [str(exc)]
            return ["Goal started."]
        if cmd.kind == "message":
            studio.send(cmd.agent, cmd.text, "you")
            studio.log("you", "message", f"{cmd.agent}: {cmd.text}")
            return [f"Sent to {studio.agent(cmd.agent).name}."]
        if cmd.kind == "pause":
            self.pause_agent(cmd.agent)
            return [f"{studio.agent(cmd.agent).name} is paused."]
        if cmd.kind == "resume" or cmd.kind == "spawn":
            self.resume_agent(cmd.agent)
            self.start()
            return [f"{studio.agent(cmd.agent).name} is back on shift."]
        if cmd.kind == "stop":
            await self.stop_agent(cmd.agent)
            return [f"{studio.agent(cmd.agent).name} is off shift."]
        if cmd.kind == "budget":
            amount = float(cmd.args[0])
            studio.update_goal(budget=amount)
            studio.log("you", "budget", f"${amount:.2f}")
            return [f"Budget set to ${amount:.2f}."]
        if cmd.kind == "answer":
            open_ones = studio.open_decisions()
            target = None
            if cmd.args:
                target = next((d for d in open_ones if d.id == cmd.args[0]), None)
            elif open_ones:
                target = open_ones[0]
            if target is None:
                return ["There is nothing to answer."]
            option = next(
                (o for o in target.options if o.lower() == cmd.text.lower()), ""
            )
            studio.answer(target.id, option, "" if option else cmd.text)
            return [f"Answered {target.id}."]
        if cmd.kind == "status":
            return self.status_lines()
        return ["Not understood."]

    def status_lines(self) -> list[str]:
        studio = self.studio
        goal = studio.data.goal
        lines = []
        if goal is None:
            return ["No goal yet."]
        spent = studio.spend()[0]
        cap = f" of ${goal.budget:.2f}" if goal.budget is not None else ""
        lines.append(
            f"Goal: {goal.text} [{goal.status}, {round(goal.progress * 100)}%] "
            f"spent ${spent:.2f}{cap}"
        )
        for agent in studio.data.agents:
            flags = " (paused)" if agent.paused else " (off shift)" if not agent.active else ""
            lines.append(f"  {agent.name}: {agent.state}{flags} {agent.activity}".rstrip())
        open_ones = studio.open_decisions()
        if open_ones:
            lines.append(f"{len(open_ones)} decision(s) need you: " + "; ".join(
                f"{d.id} {d.question[:50]}" for d in open_ones))
        return lines


async def _noop(args: dict) -> str:
    return ""


def _describe(tool: str, args: dict) -> str:
    """A short human line for a tool call, for nameplates and the feed."""
    if tool == "web_search":
        return f"searching: {str(args.get('query', ''))[:60]}"
    if tool == "fetch_page":
        return f"reading result {args.get('id', '')}"
    if tool == "write_memory":
        return f"noting: {str(args.get('title', ''))[:50]}"
    if tool == "read_memory":
        return "reading the team's notes"
    if tool == "write_section":
        return f"writing {args.get('section', 'a section')}"
    if tool in ("read_draft", "read_live"):
        return f"reading the {'live world' if tool == 'read_live' else 'draft'} {args.get('section', '')}".strip()
    if tool == "plan_tasks":
        return "planning the work"
    if tool == "send_message":
        return f"messaging {args.get('to', 'a teammate')}"
    if tool == "ask_user":
        return f"asking you: {str(args.get('question', ''))[:60]}"
    if tool in ("check_draft", "review_draft"):
        return "reviewing the draft"
    if tool == "request_fix":
        return f"sending {args.get('section', 'a section')} back"
    return tool


def replay_build(store, source_world: str) -> tuple[str, "Foreman"]:
    """A foreman that rebuilds a recorded build with no model, no web and no user.

    The new world gets the same goal. Model replies, search results and pages
    come from the recording, and decisions are answered as they were. Start it
    with ``foreman.submit(goal)`` and the same draft comes out.
    """
    from tinyworld.llm.router import LLMConfig
    from tinyworld.studio.replay import ReplaySearch, StudioReplayLLM

    source = Studio(store, source_world)
    if source.data.goal is None:
        raise ValueError("the source world has no recorded goal")
    world = store.create_world(source.data.goal.text, datetime(2000, 1, 1, 8))
    studio = Studio(store, world)
    llm = StructuredLLM(StudioReplayLLM(store, source_world), LLMConfig(), None)
    answers = {
        d.question: d.answer for d in source.data.decisions if d.status == "answered"
    }
    foreman = Foreman(studio, llm, ReplaySearch(store, source_world), answers=answers)
    return world, foreman
