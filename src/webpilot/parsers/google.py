"""Google search results page."""

from urllib.parse import parse_qs, urlparse

from selectolax.lexbor import LexborHTMLParser

NAME = "google"
MATCH = [r"^https://www\.google\.[a-z.]+/search\?"]

SNIPPET_SELECTORS = ["[data-sncf]", ".VwiC3b", '[style*="-webkit-line-clamp"]']


def _result_container(node, root):
    """Highest ancestor that still contains a single result title."""
    container = node
    parent = node.parent
    while parent is not None and parent is not root and len(parent.css("h3")) == 1:
        container = parent
        parent = parent.parent
    return container


def _snippet(container, title: str) -> str:
    for sel in SNIPPET_SELECTORS:
        for node in container.css(sel):
            text = node.text(separator=" ", strip=True)
            if text and text != title and len(text) > 30:
                return text
    text = container.text(separator=" ", strip=True).replace(title, "", 1).strip()
    return text[:300]


def parse(html: str, url: str) -> dict:
    tree = LexborHTMLParser(html)
    root = tree.css_first("#rso") or tree.css_first("#search") or tree.body
    query = parse_qs(urlparse(url).query).get("q", [""])[0]
    results, seen = [], set()
    if root is None:
        return {"query": query, "results": results}
    for h3 in root.css("h3"):
        a = h3.parent
        while a is not None and a.tag != "a":
            a = a.parent
        if a is None:
            continue
        href = a.attributes.get("href") or ""
        if href.startswith("/url?"):
            href = parse_qs(urlparse(href).query).get("q", [href])[0]
        elif href.startswith("/goto?"):
            # Opaque redirect token (2026 layout); search.py resolves it to the real URL.
            href = "https://www.google.com" + href
        elif not href.startswith("http") or urlparse(href).netloc.endswith("google.com"):
            continue
        if href in seen:
            continue
        seen.add(href)
        title = h3.text(separator=" ", strip=True)
        container = _result_container(a, root)
        cite = container.css_first("cite")
        site = cite.text(separator="", strip=True).split("›")[0].strip() if cite else ""
        if not site.startswith("http"):
            site = ""
        results.append({"title": title, "url": href, "site": site, "snippet": _snippet(container, title)})
    return {"query": query, "results": results}
