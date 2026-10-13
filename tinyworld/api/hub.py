"""Shared server state: the store, the LLM stack and one session per branch."""

import os

from tinyworld.core.session import WorldSession
from tinyworld.core.store import Store
from tinyworld.gm.adjudicator import Adjudicator
from tinyworld.gm.master import GameMaster
from tinyworld.llm.embed import Embedder, HashEmbedder
from tinyworld.llm.router import LLMConfig
from tinyworld.llm.structured import StructuredLLM
from tinyworld.llm.trace import Tracer
from tinyworld.llm.types import LLMClient


def default_client() -> LLMClient | None:
    """An Anthropic client when credentials are configured, else None."""
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        return None
    try:
        from tinyworld.llm.client import AnthropicClient

        return AnthropicClient()
    except Exception:
        return None


class Hub:
    def __init__(
        self,
        store: Store | None = None,
        client: LLMClient | None = None,
        config: LLMConfig | None = None,
        embedder: Embedder | None = None,
    ) -> None:
        self.store = store or Store()
        self.config = config or LLMConfig.load()
        self.client = client if client is not None else default_client()
        self.embedder = embedder or HashEmbedder()
        self.tracer = Tracer(self.store, self.config)
        self.llm = (
            StructuredLLM(self.client, self.config, self.tracer)
            if self.client is not None
            else None
        )
        self._sessions: dict[str, WorldSession] = {}

    @property
    def has_model(self) -> bool:
        return self.llm is not None

    def session(self, branch_id: str) -> WorldSession:
        if branch_id not in self._sessions:
            self._sessions[branch_id] = WorldSession(self.store, branch_id)
        return self._sessions[branch_id]

    def adopt(self, session: WorldSession) -> WorldSession:
        self._sessions[session.branch_id] = session
        return session

    def game_master(self, branch_id: str, world_digest: str = "") -> GameMaster:
        adjudicator = (
            Adjudicator(self.llm, world_digest=world_digest) if self.llm else None
        )
        world_id = self.store.branch(branch_id)["world_id"]
        return GameMaster(adjudicator, seed=world_id)
