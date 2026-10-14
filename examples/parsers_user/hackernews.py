"""Hacker News story lists (front page, /newest, /ask, /show ...). Example parser: copy it to parsers_user/."""
import re

from selectolax.lexbor import LexborHTMLParser

NAME = "hackernews"
MATCH = [r"^https://news\.ycombinator\.com/(news|newest|front|ask|show|jobs)?(\?.*)?$"]


def parse(html: str, url: str) -> dict:
    tree = LexborHTMLParser(html)
    stories = []
    for row in tree.css("tr.athing"):
        link = row.css_first(".titleline > a")
        if not link:
            continue
        sub = row.next  # the subtext row follows each story row (whitespace text nodes in between)
        while sub is not None and sub.tag != "tr":
            sub = sub.next
        meta = sub.css_first(".subtext") if sub else None
        score = meta.css_first(".score") if meta else None
        comments = [a for a in (meta.css("a") if meta else []) if "comment" in a.text()]
        stories.append({
            "id": row.attributes.get("id"),
            "title": link.text(strip=True),
            "url": link.attributes.get("href"),
            "points": int(re.sub(r"\D", "", score.text()) or 0) if score else None,
            "comments": int(re.sub(r"\D", "", comments[0].text()) or 0) if comments else 0,
        })
    return {"stories": stories}
