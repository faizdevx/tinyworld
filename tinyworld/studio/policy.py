"""What the team may do without asking, and how much it may spend doing it.

Tools fall into three classes:

- **safe**: they only touch the draft or the team's own notes. Always allowed.
- **ask**: they reach outside (fetching a page from a site). Allowed for a domain
  the user has said "always allow" for, otherwise the user is asked, and the
  prompt says exactly what "Always allow" covers.
- **deny**: not offered to agents at all.

Budgets are hard limits per goal: model spend, steps, pages fetched. When one is
reached the team pauses and asks the user whether to go on. Nothing here is
advice to the model; the foreman enforces it.
"""

from dataclasses import dataclass
from urllib.parse import urlparse

SAFE = frozenset({
    "read_memory", "write_memory", "read_draft", "read_live", "write_section",
    "plan_tasks", "check_draft", "review_draft", "request_fix", "send_message",
    "finish", "ask_user", "web_search",
})
ASK = frozenset({"fetch_page"})

# Hosts the scripted team and Wikipedia use. Everything else asks.
DEFAULT_ALLOWED = ("wikipedia.org", "wikimedia.org", "sim")


@dataclass
class Limits:
    max_steps: int = 600
    max_fetches: int = 60
    max_searches: int = 60


def domain_of(url: str) -> str:
    """The registrable-ish host: ``en.wikipedia.org`` and ``wikipedia.org`` match."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return parsed.scheme  # the scripted team's "sim://" pages, for instance
    host = (parsed.hostname or "").lower()
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def tool_class(name: str) -> str:
    if name in SAFE:
        return "safe"
    if name in ASK:
        return "ask"
    return "deny"


def allowed(domain: str, allowed_domains: list[str]) -> bool:
    return domain in DEFAULT_ALLOWED or domain in allowed_domains


WEB_OPTIONS = ["Allow for this build", "Ask for each site", "No web pages"]
WEB_QUESTION = (
    "May the team read web pages for this build? They only read public pages "
    "(nothing is sent, nothing is signed in to). Wikipedia is always allowed."
)


def permission_text(domain: str) -> str:
    """What the user is being asked, including the reach of 'Always allow'."""
    return (
        f"May the team read pages from {domain}? "
        f"'Always allow' covers every page on {domain} for this studio, and nothing else."
    )
