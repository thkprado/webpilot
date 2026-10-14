"""Web search through the browser session, parsed by the site parsers."""

from __future__ import annotations

import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING
from urllib.parse import quote_plus

if TYPE_CHECKING:
    from .client import Browser

REDIRECT_PREFIXES = ("https://www.google.com/goto?",)

ENGINES = {
    "google": lambda q, n, lang: f"https://www.google.com/search?q={quote_plus(q)}&num={max(n, 10)}"
    + (f"&hl={lang}" if lang else ""),
    "ddg": lambda q, n, lang: f"https://html.duckduckgo.com/html/?q={quote_plus(q)}"
    + (f"&kl={lang}" if lang else ""),
}


def search(browser: Browser, query: str, n: int = 10, engine: str = "google", lang: str | None = None,
           new_tab: bool = False) -> dict:
    from .client import WebPilotError

    if engine not in ENGINES:
        raise WebPilotError(f"unknown engine {engine!r}; choose from {', '.join(ENGINES)}")
    nav = browser.goto(ENGINES[engine](query, n, lang), new_tab=new_tab)
    if engine == "google" and "/sorry/" in (nav.get("url") or ""):
        captcha = nav.get("captcha") or {}
        if not captcha.get("solved"):
            raise WebPilotError(
                "Google showed its 'unusual traffic' page"
                + (" with a visual challenge: ask the user to solve it in the browser" if captcha.get("challenge") else "")
                + ". Retry later or use --engine ddg."
            )
        browser.wait(selector="#search", timeout=15)
    page = browser.extract()
    if page["parser"] is None:
        raise WebPilotError(f"no parser matched {page['url']}")
    results = page["data"].get("results", [])[:n]
    resolve_redirects(results)
    return {"engine": engine, "query": query, "url": page["url"], "results": results}


def _resolve(url: str) -> str:
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None

    opener = urllib.request.build_opener(NoRedirect)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with opener.open(req, timeout=5) as resp:
            return resp.headers.get("Location") or url
    except urllib.error.HTTPError as e:
        return e.headers.get("Location") or url
    except OSError:
        return url


def resolve_redirects(results: list[dict]) -> None:
    """Replaces Google /goto redirect links with their targets (a 302 that needs no cookies)."""
    todo = [r for r in results if r.get("url", "").startswith(REDIRECT_PREFIXES)]
    if not todo:
        return
    with ThreadPoolExecutor(max_workers=8) as pool:
        for r, target in zip(todo, pool.map(lambda r: _resolve(r["url"]), todo)):
            r["url"] = target
