"""DuckDuckGo HTML results page (html.duckduckgo.com) - fallback search engine."""

from urllib.parse import parse_qs, unquote, urlparse

from selectolax.lexbor import LexborHTMLParser

NAME = "duckduckgo"
MATCH = [r"^https://html\.duckduckgo\.com/html"]


def parse(html: str, url: str) -> dict:
    tree = LexborHTMLParser(html)
    results = []
    for node in tree.css(".result"):
        if "result--ad" in (node.attributes.get("class") or ""):
            continue
        a = node.css_first("a.result__a")
        if a is None:
            continue
        href = a.attributes.get("href") or ""
        if "uddg=" in href:  # //duckduckgo.com/l/?uddg=<encoded target>
            href = unquote(parse_qs(urlparse(href).query).get("uddg", [href])[0])
        snippet = node.css_first(".result__snippet")
        results.append({
            "title": a.text(separator=" ", strip=True),
            "url": href,
            "snippet": snippet.text(separator=" ", strip=True) if snippet else "",
        })
    query = parse_qs(urlparse(url).query).get("q", [""])[0]
    return {"query": query, "results": results}
