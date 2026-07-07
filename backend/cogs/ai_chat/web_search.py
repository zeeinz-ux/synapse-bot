import re
import time
import aiohttp
from bs4 import BeautifulSoup
from typing import Optional

from ...utils.intent_router import IntentType

DUCKDUCKGO_HTML = "https://html.duckduckgo.com/html/"
DUCKDUCKGO_API = "https://api.duckduckgo.com/"
SEARCH_TIMEOUT = 15
_MAX_RESULTS = 5
_MAX_CACHE_AGE = 120
_cache: dict[str, tuple[float, str]] = {}

_SEARCH_TRIGGER_KEYWORDS = [
    "info", "berita", "update", "terbaru", "terkini",
    "sekarang", "saat ini", "hari ini", "tahun ini",
    "2025", "2026", "2027", "realtime", "real-time", "live",
    "skor", "score", "hasil", "result", "peringkat", "rank",
    "juara", "champion", "pemenang", "winner",
    "siapa", "apa itu", "apa sih", "gimana", "bagaimana",
    "kapan", "dimana", "di mana", "kenapa",
]


def needs_web_search(user_message: str, intent: IntentType) -> bool:
    if intent == IntentType.SEARCH:
        return True
    text = user_message.lower().strip()
    if any(kw in text for kw in _SEARCH_TRIGGER_KEYWORDS):
        return True
    return False


def _parse_ddg_html(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    items = []

    for result in soup.select(".result"):
        title_el = result.select_one(".result__title a")
        snippet_el = result.select_one(".result__snippet")
        url_el = result.select_one(".result__url")

        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        snippet = snippet_el.get_text(strip=True) if snippet_el else ""
        url = url_el.get_text(strip=True) if url_el else ""

        if title and snippet:
            items.append({"title": title, "snippet": snippet, "url": url})
            if len(items) >= _MAX_RESULTS:
                break

    if not items:
        for result in soup.select(".results_links_deep"):
            title_el = result.select_one(".result__title a")
            snippet_el = result.select_one(".result__snippet")
            if title_el:
                title = title_el.get_text(strip=True)
                snippet = snippet_el.get_text(strip=True) if snippet_el else ""
                items.append({"title": title, "snippet": snippet, "url": ""})
                if len(items) >= _MAX_RESULTS:
                    break

    if not items:
        for link in soup.select("a.result-link"):
            title = link.get_text(strip=True)
            parent = link.find_parent()
            snippet_el = parent.find(class_="result-snippet") if parent else None
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""
            if title:
                items.append({"title": title, "snippet": snippet, "url": ""})
                if len(items) >= _MAX_RESULTS:
                    break

    return items


def _format_items(items: list[dict]) -> str:
    parts = []
    for i, item in enumerate(items, 1):
        text = f"{i}. {item['title']}"
        if item.get("snippet"):
            text += f"\n   {item['snippet']}"
        if item.get("url"):
            text += f"\n   {item['url']}"
        parts.append(text)
    return "\n\n".join(parts)


async def search_web(query: str, session: Optional[aiohttp.ClientSession] = None) -> str:
    now = time.time()

    cached = _cache.get(query)
    if cached and (now - cached[0]) < _MAX_CACHE_AGE:
        return cached[1]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    close_session = False
    if session is None:
        session = aiohttp.ClientSession()
        close_session = True

    try:
        params = {"q": query}
        async with session.get(DUCKDUCKGO_HTML, params=params, headers=headers, timeout=SEARCH_TIMEOUT) as resp:
            if resp.status != 200:
                return ""
            html = await resp.text()

        items = _parse_ddg_html(html)
        formatted = _format_items(items) if items else ""

        _cache[query] = (now, formatted)
        if len(_cache) > 100:
            _cache.clear()

        return formatted

    except Exception:
        return ""

    finally:
        if close_session:
            await session.close()
