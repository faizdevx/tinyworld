"""A scripted team, so the studio runs with no model.

It is the same idea as AgentCraft's sim backend: every part of the interface
and every rule can be exercised, demoed and screenshotted for free. The script
plays each role plausibly using a prepared world's content. It is not a model
and does not read the premise; which prepared world it uses is chosen from the
premise's words.

It speaks the same protocol as a real model: a ``Step`` JSON per turn.
"""

import json
import re

from tinyworld.fixtures import prepared
from tinyworld.genesis.research import StaticSearch
from tinyworld.genesis.bible import SECTIONS
from tinyworld.llm.types import LLMRequest, LLMResult

_USED = re.compile(r"you used (\w+)\(")
_SECTION = re.compile(r"SECTION: (\w+)")
_KIND = re.compile(r"KIND: (\w+)")
_GOAL = re.compile(r"Goal: (.+)")


def _step(tool: str, **args) -> LLMResult:
    return LLMResult(
        text=json.dumps({"thought": "", "tool": tool, "args": args}), model="script"
    )


class ScriptedTeam:
    """An LLMClient whose replies follow a fixed script for each role of task."""

    constrained = False

    def __init__(self, ask: bool = True, delay: float = 0.0) -> None:
        self.ask = ask
        # A pause per step, so a person watching the studio can follow it.
        self.delay = delay
        self.calls = 0

    async def complete(self, request: LLMRequest, model: str, effort: str | None) -> LLMResult:
        self.calls += 1
        if self.delay:
            import asyncio

            await asyncio.sleep(self.delay)
        if request.role in ("studio.agent", "studio.lead"):
            return self._agent(request)
        if request.role == "critic":
            return LLMResult(text='{"findings": []}', model="script")
        return LLMResult(text="{}", model="script")

    def _agent(self, request: LLMRequest) -> LLMResult:
        user = request.user
        used = _USED.findall(user)
        kind = (_KIND.search(user) or [None, "custom"])[1]
        section = (_SECTION.search(user) or [None, None])[1]
        goal = (_GOAL.search(user) or [None, ""])[1]
        _, world, _ = prepared.pick(goal)

        if kind == "plan":
            if "define_premise" not in used and "write_section" not in used:
                return _step("write_section", section="premise", content=world.PREMISE)
            if self.ask and "ask_user" not in used:
                return _step(
                    "ask_user",
                    question="Keep real, living public figures off the stage?",
                    options=["Yes, invent everyone", "Allow historical figures"],
                )
            if "plan_tasks" not in used:
                from tinyworld.studio.team import standard_plan

                return _step(
                    "plan_tasks",
                    tasks=standard_plan(
                        ["everyday life and economy", "politics and institutions",
                         "technology and what is missing"]
                    ),
                )
            return _step("finish", summary="planned the build")

        if kind == "research":
            if "web_search" not in used:
                topic = user.split("KIND:")[0].split("Research:")[-1].strip()[:60]
                return _step("web_search", query=topic or "the setting")
            if "fetch_page" not in used:
                return _step("fetch_page", id="r1")
            if "write_memory" not in used:
                return _step(
                    "write_memory", title=f"Notes {len(user) % 97}",
                    body=getattr(world, "DIGEST", {}).get("overview", "notes")[:400]
                    + " (source: the page above)",
                )
            return _step("finish", summary="notes saved")

        if kind in ("section", "digest") and section:
            if "write_section" not in used:
                if section == "divergence":
                    content = world.DIVERGENCE
                elif section == "digest":
                    content = world.DIGEST
                else:
                    content = world.SECTIONS[section]
                return _step("write_section", section=section, content=content)
            return _step("finish", summary=f"wrote {section}")

        if kind == "review":
            if "check_draft" not in used:
                return _step("check_draft")
            if "review_draft" not in used:
                return _step("review_draft")
            return _step("finish", summary="the draft holds together")

        return _step("finish", summary="nothing to do")


def scripted_search(goal: str) -> StaticSearch:
    """A tiny offline 'web': one page drawn from the prepared world's overview."""
    _, world, _ = prepared.pick(goal)
    digest = getattr(world, "DIGEST", {}).get("overview", "")
    pages = {
        "sim://setting": (
            "The setting at a glance",
            digest + "\n" + " ".join(t["text"] for t in getattr(world, "DIGEST", {}).get("topics", [])),
        ),
        "sim://sections": ("What a world needs", " ".join(SECTIONS)),
    }
    return StaticSearch(pages)
