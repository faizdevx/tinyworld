"""Web search and page fetch for research agents. Keyless, and careful.

Everything fetched is untrusted. It is returned as plain text with markup,
scripts and styles removed, and it only ever reaches a model as quoted
material to take notes from. URLs are limited to public http and https hosts,
so a search result cannot point the fetcher at the local machine or network.
"""

import asyncio
import ipaddress
import re
import socket
from html.parser import HTMLParser
from urllib.parse import parse_qs, unquote, urlparse

from tinyworld.genesis.research import SearchHit, SearchProvider

MAX_BYTES = 1_500_000
MAX_TEXT = 200_000
USER_AGENT = "tinyworld-research/4.0 (world-building research; +https://github.com/faizdevx/tinyworld)"


def public_url(url: str) -> bool:
    """True for an http(s) URL whose host is not local, private or reserved."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    host = parsed.hostname
    if host in ("localhost",) or host.endswith((".local", ".internal", ".localhost")):
        return False
    try:
        addresses = {ipaddress.ip_address(host)}
    except ValueError:
        try:
            addresses = {
                ipaddress.ip_address(info[4][0])
                for info in socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
            }
        except (OSError, ValueError):
            return False
    return bool(addresses) and not any(
        a.is_private or a.is_loopback or a.is_link_local or a.is_reserved
        or a.is_multicast or a.is_unspecified
        for a in addresses
    )


class _Text(HTMLParser):
    _SKIP = {"script", "style", "noscript", "svg", "head", "nav", "footer", "form", "iframe"}
    _BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs) -> None:
        if tag in self._SKIP:
            self._skip += 1
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag) -> None:
        if tag in self._SKIP and self._skip:
            self._skip -= 1
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_data(self, data) -> None:
        if not self._skip and data.strip():
            self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _Text()
    try:
        parser.feed(html)
    except Exception:
        pass
    text = "".join(parser.parts)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()[:MAX_TEXT]


_RESULT = re.compile(
    r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>'
    r'(?:.*?class="[^"]*result__snippet[^"]*"[^>]*>(?P<snippet>.*?)</a>)?',
    re.DOTALL,
)
_TAG = re.compile(r"<[^>]+>")


def _clean(fragment: str | None) -> str:
    import html as html_module

    return html_module.unescape(_TAG.sub("", fragment or "")).strip()


def _target(href: str) -> str:
    """DuckDuckGo wraps results in a redirect. Return the real address."""
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        return unquote(target)
    return href


class DuckDuckGoSearch:
    """Keyless web search through DuckDuckGo's HTML endpoint."""

    ENDPOINT = "https://html.duckduckgo.com/html/"

    def __init__(self, client=None) -> None:
        import httpx

        self._client = client or httpx.AsyncClient(
            timeout=20.0, follow_redirects=True, headers={"User-Agent": USER_AGENT}
        )

    async def search(self, query: str, limit: int = 3) -> list[SearchHit]:
        response = await self._client.post(self.ENDPOINT, data={"q": query})
        response.raise_for_status()
        hits: list[SearchHit] = []
        for found in _RESULT.finditer(response.text):
            url = _target(found.group("href"))
            if not public_url(url) or any(h.url == url for h in hits):
                continue
            hits.append(
                SearchHit(
                    url=url, title=_clean(found.group("title")),
                    snippet=_clean(found.group("snippet")), provider="web",
                )
            )
            if len(hits) >= limit:
                break
        return hits

    async def fetch(self, hit: SearchHit) -> str:
        if not public_url(hit.url):
            return ""
        response = await self._client.get(hit.url)
        response.raise_for_status()
        kind = response.headers.get("content-type", "")
        if "html" not in kind and "text" not in kind:
            return ""
        return html_to_text(response.text[:MAX_BYTES])


class MultiSearch:
    """Several providers behind one: search them together, fetch from the right one."""

    def __init__(self, providers: dict[str, SearchProvider]) -> None:
        if not providers:
            raise ValueError("at least one search provider is needed")
        self.providers = providers

    async def search(self, query: str, limit: int = 3) -> list[SearchHit]:
        async def one(name: str, provider: SearchProvider) -> list[SearchHit]:
            try:
                hits = await provider.search(query, limit)
            except Exception:
                return []  # one provider being down must not stop the others
            for hit in hits:
                hit.provider = hit.provider or name
            return hits

        results = await asyncio.gather(*(one(n, p) for n, p in self.providers.items()))
        merged: list[SearchHit] = []
        seen: set[str] = set()
        # Interleave so no single provider crowds the others out.
        for rank in range(limit):
            for hits in results:
                if rank < len(hits) and hits[rank].url not in seen:
                    seen.add(hits[rank].url)
                    merged.append(hits[rank])
        return merged

    async def fetch(self, hit: SearchHit) -> str:
        provider = self.providers.get(hit.provider) or next(iter(self.providers.values()))
        return await provider.fetch(hit)
