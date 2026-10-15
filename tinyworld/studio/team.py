"""The foreman: a visible team of agents that builds a world, with you in the loop.

A goal (a premise) becomes a task graph. Agents pick up ready tasks and work
them with tools: search the web, read notes, write sections of the world bible,
review each other's work, and ask you when a call is genuinely yours. All of it
goes to a *draft*. Nothing becomes the world until you press Merge.

The foreman owns the scheduling and the rules; the agents own the thinking.
A viewer is only a window onto ``Studio.bus``.
"""

import asyncio
import json
from datetime import datetime

from pydantic import ValidationError

from tinyworld.genesis import critic
from tinyworld.genesis.bible import (
    ARTIFACTS, SECTION_BRIEFS, SECTIONS, Bible, BibleStore, Critique, Finding,
)
from tinyworld.genesis.research import SearchHit, SearchProvider
from tinyworld.llm.structured import StructuredLLM
from tinyworld.llm.types import CallContext
from tinyworld.studio.protocol import (
    MERGE_OPTIONS, Agent, AgentState, Decision, Station, Task,
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
    "write_section": ("writing", "drafting"),
    "plan_tasks": ("thinking", "wall"),
    "ask_user": ("waiting_user", "podium"),
    "check_draft": ("reviewing", "review"),
    "review_draft": ("reviewing", "review"),
    "request_fix": ("reviewing", "review"),
}
WRITABLE = ["premise", "divergence", *SECTIONS, "digest"]
MAX_ATTEMPTS = 2
MAX_FIX_ROUNDS = 2


def standard_plan(research_topics: list[str]) -> list[dict]:
    """The usual shape of a world build, as plan_tasks entries (deps by index)."""
    tasks: list[dict] = []
    for topic in research_topics:
        tasks.append({"title": f"Research: {topic}", "kind": "research"})
    n = len(tasks)
    research = list(range(n))
    tasks.append({"title": "What changes: the divergence", "kind": "section",
                  "section": "divergence", "deps": research})
    div = len(tasks) - 1
    index: dict[str, int] = {}
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
        now=datetime.now,
    ) -> None:
        self.studio = studio
        self.llm = llm
        self.search = search
        self.max_parallel = max_parallel
        self.step_cap = step_cap
        self.auto_answer = auto_answer
        self._now = now
        self._active: dict[str, asyncio.Task] = {}
        self._hits: dict[str, SearchHit] = {}
        self._runner: asyncio.Task | None = None
        self._fix_rounds = 0
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

    def submit(self, goal_text: str) -> None:
        """Start a new build from a premise."""
        if self._runner is not None and not self._runner.done():
            raise RuntimeError("the team is already working on a goal")
        self.studio.set_goal(goal_text)
        graph = self.studio.graph
        task = graph.create(
            "Plan the world", kind="plan", created_by="user", priority=10,
            description=f"The premise to build a world from:\n{goal_text}",
        )
        self.studio.task_changed(task.id)
        self.studio.say(f"New goal: {goal_text}", None, "system")
        self.start()

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

    # -- scheduling -----------------------------------------------------

    def _owner_for(self, task: Task) -> str | None:
        """The agent who should take this task, if one is free."""
        busy = {
            self.studio.graph.get(tid).assignee for tid in self._active
        }
        if task.kind == "research":
            candidates = ["iris", "ash"]
        elif task.kind == "plan":
            candidates = ["marlow"]
        elif task.kind == "review":
            candidates = ["vera"]
        elif task.kind == "digest":
            candidates = ["marlow"]
        else:
            candidates = [OWNER.get(task.section or "", "marlow")]
        for agent_id in candidates:
            try:
                agent = self.studio.agent(agent_id)
            except KeyError:
                continue
            if agent.active and agent_id not in busy:
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

    async def run(self) -> None:
        graph = self.studio.graph
        self.studio.update_goal(status="running")
        while True:
            self._dispatch()
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

    async def _work(self, task_id: str, agent_id: str) -> None:
        studio = self.studio
        task = studio.graph.get(task_id)
        agent = studio.agent(agent_id)
        self._set(agent_id, "thinking", "wall", task.title, task_id)
        studio.say(f"takes on: {task.title}", agent_id, "task")
        steps = 0

        def on_step(index: int, tool: str, args: dict) -> None:
            nonlocal steps
            steps = index
            state, station = TOOL_STATE.get(tool, ("thinking", "wall"))
            self._set(agent_id, state, station, _describe(tool, args), task_id)
            studio.set_agent(agent_id, steps=index)
            studio.say(_describe(tool, args), agent_id, "tool")

        session = AgentSession(
            self.llm, world_id=self.world_id, agent_id=agent_id, name=agent.name,
            role=agent.title or agent.role, tools=self._tools(task, agent),
            max_steps=self.step_cap, on_step=on_step,
            llm_role="studio.lead" if agent.role == "lead" else "studio.agent",
        )
        try:
            result = await session.run(self._task_text(task), self._world_note())
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            result = SessionResult("failed", error=f"{type(exc).__name__}: {exc}")
        self._close(task_id, agent_id, result)

    def _close(self, task_id: str, agent_id: str, result: SessionResult) -> None:
        studio = self.studio
        graph = studio.graph
        task = graph.get(task_id)
        ok = result.status == "finished" and self._produced(task)
        if ok:
            if task.kind == "plan" and len(graph.all()) == 1:
                self._plan(standard_plan(self._topics()), "marlow")
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
            else:
                graph.move(task_id, "blocked", attempts=attempts, blocked_reason=reason)
                studio.say(f"stuck on {task.title!r}: {reason}", agent_id, "task")
            self._set(agent_id, "error" if attempts >= MAX_ATTEMPTS else "idle",
                      "lounge", reason[:80])
        studio.task_changed(task_id)

    def _produced(self, task: Task) -> bool:
        """Did a task that should leave something behind actually leave it?"""
        if task.kind in ("section", "digest") and task.section:
            return task.section in self.studio.data.draft
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
        if task.kind == "research":
            extra = "\nFind facts about everyday life, institutions, economy and technology."
        return f"{head}\nGoal: {goal}\n{body}{extra}".strip()

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

    # -- tools ----------------------------------------------------------

    def _tools(self, task: Task, agent: Agent) -> list[Tool]:
        studio = self.studio
        agent_id = agent.id

        async def web_search(args: dict) -> str:
            query = str(args.get("query", "")).strip()
            if not query:
                return "give a query"
            hits = await self.search.search(query, 4)
            if not hits:
                return "no results"
            lines = []
            for hit in hits:
                key = f"r{len(self._hits) + 1}"
                self._hits[key] = hit
                lines.append(f"{key}: {hit.title} - {hit.url}\n    {hit.snippet[:160]}")
            return "\n".join(lines)

        async def fetch_page(args: dict) -> str:
            ref = str(args.get("id", "")).strip()
            hit = self._hits.get(ref)
            if hit is None:
                return f"unknown result {ref!r}; use an id from web_search"
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

        async def write_section(args: dict) -> str:
            section = str(args.get("section", task.section or "")).strip()
            if section not in WRITABLE:
                return f"{section!r} is not a section. Sections: {', '.join(WRITABLE)}"
            content = args.get("content")
            if not isinstance(content, dict):
                return "content must be a JSON object matching the section"
            try:
                valid = ARTIFACTS[section].model_validate(content)
            except ValidationError as exc:
                problems = "; ".join(
                    f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}"
                    for e in exc.errors()[:6]
                )
                return f"{section} was not saved. Fix: {problems}"
            studio.data.draft[section] = valid.model_dump(mode="json")
            studio.emit("draft.upsert", section=section)
            studio.save()
            return f"{section} saved to the draft"

        async def plan_tasks(args: dict) -> str:
            tasks = args.get("tasks")
            if not isinstance(tasks, list) or not tasks:
                return "give a list of tasks: [{title, kind, section?, deps?}]"
            clean = [t for t in tasks if isinstance(t, dict)]
            ids = self._plan(clean, agent_id)
            return f"created {len(ids)} tasks"

        async def ask_user(args: dict) -> str:
            question = str(args.get("question", "")).strip()
            if not question:
                return "give a question"
            options = [str(o) for o in (args.get("options") or [])][:4]
            decision = Decision(
                id="", agent_id=agent_id, kind="question", question=question,
                options=options, context=str(args.get("context", ""))[:500],
                task_id=task.id,
            )
            future = studio.ask(decision)
            self._set(agent_id, "waiting_user", "podium", question[:80], task.id)
            if self.auto_answer:
                studio.answer(decision.id, options[0] if options else "", "go with your judgement")
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
                self.llm, bible, CallContext(self.world_id, 0, agent_id)
            )
            if not found:
                return "the reviewer found nothing"
            return "\n".join(
                f"- [{'BLOCKING' if f.blocking else 'note'}] ({f.kind}, {f.section}) {f.text}"
                for f in found
            )

        async def request_fix(args: dict) -> str:
            section = str(args.get("section", "")).strip()
            note = str(args.get("note", "")).strip()
            if section not in SECTIONS or not note:
                return f"give a section from {', '.join(SECTIONS)} and a note"
            if self._fix_rounds >= MAX_FIX_ROUNDS * len(SECTIONS):
                return "enough rounds of fixes; leave the rest as notes"
            self._fix_rounds += 1
            fix = studio.graph.create(
                f"Fix {section}: {note[:60]}", kind="section", section=section,
                created_by=agent_id,
                description=f"The reviewer asks for this change to {section}:\n{note}\n"
                f"Read the draft first, then write the corrected section.",
                priority=5,
            )
            studio.task_changed(fix.id)
            return f"asked {OWNER.get(section, 'marlow')} to fix {section}"

        finish = Tool("finish", "finish(summary): the task is done; say what you did", _noop)
        common = [
            Tool("read_memory", "read_memory(query): notes the team has written", read_memory),
            Tool("ask_user", "ask_user(question, options): ask the human; use sparingly", ask_user),
            finish,
        ]
        kind = task.kind
        if kind == "research":
            return [
                Tool("web_search", "web_search(query): search the web and Wikipedia", web_search),
                Tool("fetch_page", "fetch_page(id): read a result from web_search", fetch_page),
                Tool("write_memory", "write_memory(title, body): save a note with its source", write_memory),
                *common,
            ]
        if kind == "review":
            return [
                Tool("check_draft", "check_draft(): mechanical problems in the draft", check_draft),
                Tool("review_draft", "review_draft(): a careful read of the whole draft", review_draft),
                Tool("request_fix", "request_fix(section, note): send a section back to be fixed", request_fix),
                Tool("read_draft", "read_draft(section): a section of the draft", read_draft),
                finish,
            ]
        writing = [
            Tool("read_draft", "read_draft(section): a section of the draft", read_draft),
            Tool("write_section",
                 "write_section(section, content): save a section; content is a JSON "
                 "object that must match the section's shape", write_section),
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

    def _draft_bible(self) -> Bible:
        data = {k: v for k, v in self.studio.data.draft.items() if k in ARTIFACTS}
        try:
            return Bible.model_validate(data)
        except ValidationError:
            return Bible()

    def draft_view(self) -> dict:
        bible = self._draft_bible()
        return {
            "sections": sorted(self.studio.data.draft),
            "draft": self.studio.data.draft,
            "findings": [f.model_dump() for f in critic.check(bible)],
            "merged_version": self.studio.data.merged_version,
        }

    async def _merge_stage(self) -> None:
        studio = self.studio
        studio.update_goal(status="review")
        bible = self._draft_bible()
        findings = critic.check(bible)
        blocking = [f for f in findings if f.blocking]
        summary = (
            f"Draft world: {len(bible.geography.places)} places, "
            f"{len(bible.figures.figures)} people, {len(bible.factions.factions)} factions. "
            + (f"{len(blocking)} blocking problem(s) remain." if blocking else "No blocking problems.")
        )
        decision = Decision(
            id="", agent_id="marlow", kind="merge",
            question="Merge this draft as the world?", options=list(MERGE_OPTIONS),
            context=summary,
        )
        future = studio.ask(decision)
        self._set("marlow", "waiting_user", "podium", "waiting for your decision")
        if self.auto_answer:
            studio.answer(decision.id, "Merge")
        answered = await future
        self._set("marlow", "idle", "lounge", "")
        if answered.answer == "Merge":
            self.apply_merge(findings)
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
            studio.say("The draft was rejected. Nothing was merged.", "marlow", "system")

    def apply_merge(self, findings: list[Finding] | None = None) -> int:
        """Write the draft into the world's bible as a new version. The only way in."""
        bibles = BibleStore(self.store)
        world = self.world_id
        if bibles.get(world, "digest") is not None:
            bibles.new_version(world)
        for section, content in self.studio.data.draft.items():
            bibles.put(world, section, ARTIFACTS[section].model_validate(content))
        bible = self._draft_bible()
        bibles.put(world, "critique", Critique(findings=findings or critic.check(bible)))
        start = bible.premise.start_date
        try:
            when = datetime.fromisoformat(start).replace(hour=8)
        except ValueError:
            when = None
        events = self.store.query(
            "SELECT 1 FROM branches WHERE world_id=?", (world,)
        )
        if when is not None and not events:
            self.store.execute(
                "UPDATE worlds SET start_time=? WHERE id=?", (when.isoformat(), world)
            )
        version = bibles.version(world)
        self.studio.data.merged_version = version
        self.studio.save()
        return version


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
    if tool == "read_draft":
        return f"reading the draft {args.get('section', '')}".strip()
    if tool == "plan_tasks":
        return "planning the work"
    if tool == "ask_user":
        return f"asking you: {str(args.get('question', ''))[:60]}"
    if tool in ("check_draft", "review_draft"):
        return "reviewing the draft"
    if tool == "request_fix":
        return f"sending {args.get('section', 'a section')} back"
    return tool
