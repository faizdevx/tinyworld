"""Shared server state: the store, the LLM stack, genesis jobs and branch runners."""

import asyncio
import json
import os
from dataclasses import dataclass, field

from tinyworld.api.runner import BranchRunner
from tinyworld.core.session import WorldSession
from tinyworld.core.store import Store
from tinyworld.fixtures import berlin, prepared
from tinyworld.genesis.bible import BibleStore, Finding
from tinyworld.genesis.pipeline import GenesisPipeline
from tinyworld.genesis.research import NullSearch, SearchProvider
from tinyworld.gm.adjudicator import Adjudicator
from tinyworld.gm.master import GameMaster
from tinyworld.llm.embed import Embedder, HashEmbedder
from tinyworld.llm.fake import FakeLLM
from tinyworld.llm.offline import offline_llm
from tinyworld.llm.router import LLMConfig
from tinyworld.llm.structured import StructuredLLM
from tinyworld.llm.trace import Tracer
from tinyworld.llm.types import LLMClient


def chosen_provider() -> str | None:
    """"anthropic", "gemini" or None.

    ``TINYWORLD_PROVIDER`` decides when set; otherwise whichever key is present,
    Anthropic first.
    """
    wanted = os.environ.get("TINYWORLD_PROVIDER", "").strip().lower()
    if wanted in ("anthropic", "gemini", "openrouter", "local"):
        return wanted
    if os.environ.get("LOCAL_BASE_URL"):
        return "local"
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return "anthropic"
    if os.environ.get("OPENROUTER_API_KEY"):
        return "openrouter"
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        return "gemini"
    return None


def make_client(provider: str | None) -> LLMClient | None:
    try:
        if provider == "anthropic":
            from tinyworld.llm.client import AnthropicClient

            return AnthropicClient()
        if provider == "gemini":
            from tinyworld.llm.gemini import GeminiClient

            return GeminiClient()
        if provider == "openrouter":
            from tinyworld.llm.openrouter import OpenRouterClient

            return OpenRouterClient()
        if provider == "local":
            from tinyworld.llm.openai_compat import OpenAICompatClient

            return OpenAICompatClient()
    except Exception:
        return None
    return None


def default_client() -> LLMClient | None:
    """A client for the configured provider, or None when there is no key."""
    return make_client(chosen_provider())


def default_search(online: bool) -> SearchProvider:
    if not online:
        return NullSearch()
    try:
        from tinyworld.genesis.research import WikipediaSearch
        from tinyworld.genesis.web import DuckDuckGoSearch, MultiSearch

        providers: dict = {"wikipedia": WikipediaSearch()}
        if os.environ.get("TINYWORLD_WEB_SEARCH", "on").lower() not in ("off", "0", "false"):
            providers["web"] = DuckDuckGoSearch()
        return MultiSearch(providers)
    except Exception:
        return NullSearch()


@dataclass
class GenesisJob:
    world_id: str
    stage: str = "queued"
    running: bool = False
    log: list[dict] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    error: str = ""
    subscribers: set = field(default_factory=set)
    task: asyncio.Task | None = None

    def view(self) -> dict:
        return {
            "world_id": self.world_id,
            "stage": self.stage,
            "running": self.running,
            "log": self.log[-40:],
            "questions": self.questions,
            "findings": [f.model_dump() for f in self.findings],
            "error": self.error,
        }

    def publish(self) -> None:
        message = json.dumps({"type": "genesis", "genesis": self.view()})
        for queue in list(self.subscribers):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                self.subscribers.discard(queue)


class Hub:
    """Everything the API needs. Without a model it runs in offline demo mode:
    a rule-driven stand-in acts for the agents and genesis returns a canned bible.
    """

    def __init__(
        self,
        store: Store | None = None,
        client: LLMClient | None = None,
        config: LLMConfig | None = None,
        embedder: Embedder | None = None,
        search: SearchProvider | None = None,
        *,
        offline_fallback: bool = True,
    ) -> None:
        self.store = store or Store()
        provider = chosen_provider()
        self.client = client if client is not None else make_client(provider)
        self.config = config or LLMConfig.load(
            provider=provider if provider in ("gemini", "openrouter", "local") else "anthropic"
        )
        self.offline_fallback = offline_fallback
        self.embedder = embedder or HashEmbedder()
        self.tracer = Tracer(self.store, self.config)
        self.llm = (
            StructuredLLM(self.client, self.config, self.tracer)
            if self.client is not None
            else None
        )
        self.search = search or default_search(self.client is not None)
        self.bibles = BibleStore(self.store)
        self.genesis_jobs: dict[str, GenesisJob] = {}
        self._sessions: dict[str, WorldSession] = {}
        self._runners: dict[str, BranchRunner] = {}

    @property
    def has_model(self) -> bool:
        return self.llm is not None

    @property
    def offline(self) -> bool:
        return self.llm is None and self.offline_fallback

    # -- sessions and runners -------------------------------------------

    def session(self, branch_id: str) -> WorldSession:
        if branch_id not in self._sessions:
            self._sessions[branch_id] = WorldSession(self.store, branch_id)
        return self._sessions[branch_id]

    def adopt(self, session: WorldSession) -> WorldSession:
        self._sessions[session.branch_id] = session
        return session

    def world_digest(self, world_id: str) -> str:
        bible = self.bibles.load(world_id)
        return bible.world_digest() or self.store.world(world_id)["premise"]

    def llm_for(self, session: WorldSession) -> StructuredLLM | None:
        if self.llm is not None:
            return self.llm
        if not self.offline_fallback:
            return None
        return StructuredLLM(
            offline_llm(lambda: session.state, seed=session.world_id),
            self.config,
            self.tracer,
        )

    def runner(self, branch_id: str) -> BranchRunner:
        if branch_id not in self._runners:
            session = self.session(branch_id)
            self._runners[branch_id] = BranchRunner(
                session,
                self.llm_for(session),
                world_digest=self.world_digest(session.world_id),
                embedder=self.embedder,
                offline=self.offline,
            )
        return self._runners[branch_id]

    def game_master(self, branch_id: str, world_digest: str = "") -> GameMaster:
        llm = self.llm_for(self.session(branch_id))
        adjudicator = Adjudicator(llm, world_digest=world_digest) if llm else None
        world_id = self.store.branch(branch_id)["world_id"]
        return GameMaster(adjudicator, seed=world_id)

    # -- genesis --------------------------------------------------------

    def genesis_llm(self, world_id: str | None = None) -> StructuredLLM | None:
        if self.llm is not None:
            return self.llm
        if not self.offline_fallback:
            return None
        module = berlin
        if world_id is not None:
            key, module, matched = prepared.pick(self.store.world(world_id)["premise"])
            self.store.meta_set(world_id, "prepared_world", key)
            self.store.meta_set(world_id, "prepared_match", "1" if matched else "0")
        return StructuredLLM(
            FakeLLM(module.genesis_handlers()), self.config, self.tracer
        )

    def prepared_of(self, world_id: str) -> dict | None:
        """Which prepared world stands in for this one, or None if built by a model."""
        if self.store.meta_get(world_id, "canned_genesis") != "1":
            return None
        key = self.store.meta_get(world_id, "prepared_world") or "berlin"
        module = prepared.by_key(key) or berlin
        return {
            "key": key,
            "label": prepared.label_of(module),
            "matched": self.store.meta_get(world_id, "prepared_match") != "0",
        }

    async def connect(self, provider: str, key: str, base_url: str | None = None) -> None:
        """Use a model from now on. The key is kept in this process only.

        Nothing is written to disk. The key is tried with one tiny call first;
        a provider that rejects it raises LLMFatal and nothing changes.
        """
        from pydantic import BaseModel

        from tinyworld.llm.types import CallContext

        names = {
            "openrouter": "OPENROUTER_API_KEY",
            "gemini": "GEMINI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "local": "LOCAL_API_KEY",
        }
        if provider not in names:
            raise ValueError(f"unknown provider: {provider}")
        key = key.strip()
        previous_url = os.environ.get("LOCAL_BASE_URL")
        if provider == "local":
            # A local server often takes no key; what it needs is an address.
            if not (base_url or "").strip():
                raise ValueError("the address of the model server is needed")
            os.environ["LOCAL_BASE_URL"] = base_url.strip()
        elif not key:
            raise ValueError("a key is needed")
        variable = names[provider]
        previous = os.environ.get(variable)
        os.environ[variable] = key

        def restore() -> None:
            if previous is None:
                os.environ.pop(variable, None)
            else:
                os.environ[variable] = previous
            if provider == "local":
                if previous_url is None:
                    os.environ.pop("LOCAL_BASE_URL", None)
                else:
                    os.environ["LOCAL_BASE_URL"] = previous_url

        try:
            client = make_client(provider)
            if client is None:
                raise ValueError(f"{provider} support is not installed")
            config = LLMConfig.load(
                provider=provider if provider in ("gemini", "openrouter", "local") else "anthropic"
            )
            tracer = Tracer(self.store, config)
            llm = StructuredLLM(client, config, None, max_repairs=0)

            class Ping(BaseModel):
                ok: bool = True

            reply = await llm.call(
                "memory.ping", Ping, system="Reply with ok true.", user="ping",
                context=CallContext("probe"), fallback=Ping(ok=False), max_tokens=20,
            )
            if not reply.ok:
                raise ValueError(f"the model did not answer: {reply.error[:200]}")
        except Exception:
            restore()
            raise
        self.client, self.config, self.tracer = client, config, tracer
        self.llm = StructuredLLM(client, config, tracer)
        self.search = default_search(True)
        # Runners made until now hold the offline stand-in.
        for runner in list(self._runners.values()):
            await runner.pause()
        self._runners = {}

    def pipeline(self, job: GenesisJob | None = None, world_id: str | None = None) -> GenesisPipeline:
        llm = self.genesis_llm(world_id)
        if llm is None:
            raise RuntimeError("no model is configured")

        def progress(stage: str, detail: str) -> None:
            if job is not None:
                job.stage = stage
                job.log.append({"stage": stage, "detail": detail})
                job.publish()

        return GenesisPipeline(self.store, llm, search=self.search, on_progress=progress)

    def genesis_job(self, world_id: str) -> GenesisJob:
        if world_id not in self.genesis_jobs:
            job = GenesisJob(world_id)
            # A world reloaded from disk is past genesis if it has a digest.
            if self.bibles.get(world_id, "digest") is not None:
                job.stage = "done"
                job.findings = self.bibles.load(world_id).critique.findings
            self.genesis_jobs[world_id] = job
        return self.genesis_jobs[world_id]

    async def run_genesis(self, world_id: str, stage: str | None = None) -> None:
        job = self.genesis_job(world_id)
        if self.llm is None:
            # Remembered with the world: its bible is a prepared example, and
            # must keep saying so after the server is restarted with a key.
            self.store.meta_set(world_id, "canned_genesis", "1")
        job.running, job.error, job.questions = True, "", []
        job.publish()
        try:
            pipeline = self.pipeline(job, world_id)
            if stage is None:
                status = await pipeline.run(world_id)
                job.questions = status.questions
                job.findings = status.findings
                job.stage = status.stage
            else:
                await pipeline.run_stage(world_id, stage)
                job.findings = self.bibles.load(world_id).critique.findings
                job.stage = "done"
        except Exception as exc:  # shown to the user rather than lost in a task
            job.error = f"{type(exc).__name__}: {exc}"
            job.stage = "error"
        finally:
            job.running = False
            job.publish()

    def start_genesis(self, world_id: str, stage: str | None = None) -> GenesisJob:
        job = self.genesis_job(world_id)
        if not job.running:
            job.running = True
            job.task = asyncio.create_task(self.run_genesis(world_id, stage))
        return job
