"""Tasks with dependencies. The rules here are what keep a team from tangling.

- dependencies must exist; no self-dependency; no cycles
- a task starts only when every dependency is done, and it has an assignee
- a task closes through ``finish`` or ``fail``; ``cancelled`` is terminal until retried
"""

from datetime import datetime

from tinyworld.studio.protocol import Task, TaskKind, TaskStatus

TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    "todo": {"doing", "blocked", "cancelled", "done"},
    "doing": {"review", "blocked", "todo", "done", "cancelled"},
    "review": {"done", "doing", "blocked", "todo", "cancelled"},
    "blocked": {"todo", "doing", "cancelled", "review"},
    "done": {"todo"},
    "cancelled": {"todo"},
}
TERMINAL = {"done", "cancelled"}


class TaskError(ValueError):
    pass


class TaskGraph:
    def __init__(self, tasks: list[Task] | None = None, *, now=datetime.now) -> None:
        self.tasks: dict[str, Task] = {t.id: t for t in (tasks or [])}
        self._now = now
        self._counter = len(self.tasks)

    # -- reading --------------------------------------------------------

    def get(self, task_id: str) -> Task:
        task = self.tasks.get(task_id)
        if task is None:
            raise TaskError(f"no task {task_id}")
        return task

    def all(self) -> list[Task]:
        return list(self.tasks.values())

    def ready(self) -> list[Task]:
        """Tasks that may start now: todo, with every dependency done."""
        return sorted(
            (
                t for t in self.tasks.values()
                if t.status == "todo"
                and all(self.tasks[d].status == "done" for d in t.deps)
            ),
            key=lambda t: (-t.priority, t.created_at or datetime.min, t.id),
        )

    def finished(self) -> bool:
        return bool(self.tasks) and all(t.status in TERMINAL for t in self.tasks.values())

    def progress(self) -> float:
        live = [t for t in self.tasks.values() if t.status != "cancelled"]
        if not live:
            return 0.0
        return sum(1 for t in live if t.status == "done") / len(live)

    # -- changing -------------------------------------------------------

    def create(
        self,
        title: str,
        *,
        kind: TaskKind = "custom",
        deps: list[str] | None = None,
        section: str | None = None,
        description: str = "",
        priority: int = 0,
        created_by: str = "user",
    ) -> Task:
        title = title.strip()
        if not title:
            raise TaskError("a task needs a title")
        deps = list(dict.fromkeys(deps or []))
        for dep in deps:
            if dep not in self.tasks:
                raise TaskError(f"unknown dependency {dep}")
        self._counter += 1
        now = self._now()
        task = Task(
            id=f"t{self._counter}", title=title, kind=kind, deps=deps, section=section,
            description=description, priority=priority, created_by=created_by,
            created_at=now, updated_at=now,
        )
        self.tasks[task.id] = task
        return task

    def set_deps(self, task_id: str, deps: list[str]) -> Task:
        task = self.get(task_id)
        deps = list(dict.fromkeys(deps))
        for dep in deps:
            if dep not in self.tasks:
                raise TaskError(f"unknown dependency {dep}")
            if dep == task_id or self._reaches(dep, task_id):
                raise TaskError(f"{dep} would make {task_id} wait on itself")
        task.deps = deps
        task.updated_at = self._now()
        return task

    def _reaches(self, start: str, goal: str) -> bool:
        seen: set[str] = set()
        stack = [start]
        while stack:
            node = stack.pop()
            if node == goal:
                return True
            if node in seen or node not in self.tasks:
                continue
            seen.add(node)
            stack.extend(self.tasks[node].deps)
        return False

    def move(self, task_id: str, status: TaskStatus, **fields) -> Task:
        task = self.get(task_id)
        if status != task.status and status not in TRANSITIONS[task.status]:
            raise TaskError(f"{task.title!r} cannot go from {task.status} to {status}")
        if status == "doing":
            unmet = [d for d in task.deps if self.tasks[d].status != "done"]
            if unmet:
                raise TaskError(f"{task.title!r} waits on {', '.join(unmet)}")
            if not (fields.get("assignee") or task.assignee):
                raise TaskError(f"{task.title!r} has nobody assigned")
        for key, value in fields.items():
            setattr(task, key, value)
        task.status = status
        task.updated_at = self._now()
        return task

    def release_running(self) -> list[Task]:
        """After a restart nothing is really running: put started tasks back."""
        back = []
        for task in self.tasks.values():
            if task.status in ("doing", "review"):
                task.status = "todo"
                task.assignee = None
                task.updated_at = self._now()
                back.append(task)
        return back
