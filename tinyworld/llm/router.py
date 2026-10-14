"""Role → tier → model routing. The only module that names models."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Price:
    """US dollars per million tokens."""

    input: float
    output: float
    cache_read: float
    cache_write: float


@dataclass
class Route:
    role: str
    tier: str
    model: str
    effort: str | None


DEFAULT_TIERS = {
    "strong": "claude-opus-5-5",
    "standard": "claude-sonnet-5-5",
    "cheap": "claude-haiku-5-5",
}

# Chosen from what a new key can call: gemini-2.5-pro and 2.5-flash-lite are
# closed to new users, and pro models have no free-tier quota. On a paid key,
# set GEMINI_MODEL_STRONG to a pro model.
GEMINI_TIERS = {
    "strong": "gemini-3.5-flash",
    "standard": "gemini-2.5-flash",
    "cheap": "gemini-3.5-flash-lite",
}

# Any OpenRouter model id works. These are inexpensive and follow JSON
# instructions well; set OPENROUTER_MODEL_STRONG/_STANDARD/_CHEAP to change them.
OPENROUTER_TIERS = {
    "strong": "google/gemini-3.6-flash",
    "standard": "google/gemini-3.5-flash-lite",
    "cheap": "google/gemini-3.5-flash-lite",
}

DEFAULT_EFFORT = {"strong": "high", "standard": "medium", "cheap": "low"}

# Longest matching prefix wins. "*" is the default.
DEFAULT_ROLES = {
    "genesis.": "strong",
    "critic": "strong",
    "god.": "strong",
    "gm.conflict": "strong",
    "agent.act": "standard",
    "agent.act.tier1": "cheap",
    "agent.scene": "standard",
    "agent.reflect": "standard",
    "agent.persona": "standard",
    "gm.adjudicate": "standard",
    "chronicler": "standard",
    "eval.": "standard",
    "memory.": "cheap",
    "perception.": "cheap",
    "tier2.": "cheap",
    "*": "standard",
}

# Cache write is priced at 1.25x input. Cache read prices for the strong and
# standard tiers are published; the cheap tier's is assumed to be 0.1x input.
DEFAULT_PRICES = {
    "claude-opus-5-5": Price(4.00, 20.00, 0.20, 5.00),
    "claude-sonnet-5-5": Price(2.00, 10.00, 0.20, 2.50),
    "claude-haiku-5-5": Price(0.10, 0.50, 0.01, 0.125),
}


@dataclass
class LLMConfig:
    tiers: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_TIERS))
    effort: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_EFFORT))
    roles: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_ROLES))
    prices: dict[str, Price] = field(default_factory=lambda: dict(DEFAULT_PRICES))

    @classmethod
    def gemini(cls) -> "LLMConfig":
        """Tiers on Gemini models. Override with GEMINI_MODEL_STRONG, _STANDARD, _CHEAP.

        No prices are set: they change, and a wrong one is worse than none.
        Costs read as zero (and budgets never trip) until prices are given in
        the file named by TINYWORLD_LLM_CONFIG.
        """
        tiers = {
            "strong": os.environ.get("GEMINI_MODEL_STRONG", GEMINI_TIERS["strong"]),
            "standard": os.environ.get("GEMINI_MODEL_STANDARD", GEMINI_TIERS["standard"]),
            "cheap": os.environ.get("GEMINI_MODEL_CHEAP", GEMINI_TIERS["cheap"]),
        }
        return cls(tiers=tiers, prices={})

    @classmethod
    def openrouter(cls) -> "LLMConfig":
        """Tiers on OpenRouter models. Costs come from OpenRouter's own usage report."""
        tiers = {
            tier: os.environ.get(f"OPENROUTER_MODEL_{tier.upper()}", default)
            for tier, default in OPENROUTER_TIERS.items()
        }
        return cls(tiers=tiers, prices={})

    @classmethod
    def load(
        cls, path: str | Path | None = None, *, provider: str = "anthropic"
    ) -> "LLMConfig":
        """Provider defaults, overridden by a JSON file (``TINYWORLD_LLM_CONFIG`` or ``path``)."""
        config = (
            cls.gemini() if provider == "gemini"
            else cls.openrouter() if provider == "openrouter"
            else cls()
        )
        path = path or os.environ.get("TINYWORLD_LLM_CONFIG")
        if path and Path(path).exists():
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            config.tiers.update(data.get("tiers", {}))
            config.effort.update(data.get("effort", {}))
            config.roles.update(data.get("roles", {}))
            for model, price in data.get("prices", {}).items():
                config.prices[model] = Price(**price)
        return config

    def tier_for(self, role: str) -> str:
        best = ""
        for prefix in self.roles:
            if prefix != "*" and role.startswith(prefix) and len(prefix) > len(best):
                best = prefix
        return self.roles[best] if best else self.roles.get("*", "standard")

    def route(self, role: str) -> Route:
        tier = self.tier_for(role)
        return Route(role, tier, self.tiers[tier], self.effort.get(tier))

    def cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
    ) -> float:
        price = self.prices.get(model)
        if price is None:
            return 0.0
        return (
            input_tokens * price.input
            + output_tokens * price.output
            + cache_read_tokens * price.cache_read
            + cache_write_tokens * price.cache_write
        ) / 1_000_000
