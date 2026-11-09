# WebPilot: site parsers, notes and scripts

Read this before writing a parser, site notes or a script for a site (usually during the end-of-session
[reflection](reflect.md)). The core guide is [agent.md](agent.md). `<webpilot>` is the WebPilot folder, the parent
of this `docs/` folder.

## Parsers

A parser turns a site's HTML into compact JSON, so you do not have to read the whole page again. `extract` uses one
automatically whenever the URL matches. Parsers also match iframes: when the page itself has none, the first iframe
with one is parsed (`"frame"` and `"page_url"` in the result).

**When to write one:** the same site is read two or more times, or `reflect-data` suggests it.

**Where:** `<webpilot>/parsers_user/<name>.py`. It is found automatically and takes precedence over the built-in
parsers (`src/webpilot/parsers/`: google, duckduckgo; their fixtures in `tests/fixtures/`).

`parsers_user/` is local to each user and is not versioned (it is in `.gitignore`): fixtures are saved pages, and
notes and scripts reflect the user's own browsing. To start one, copy the example:
`cp -r examples/parsers_user parsers_user` (a Hacker News parser with its fixture, `NOTES.md` and
`scripts/hn_top.py`, which then runs as `webpilot script hn_top`).

**Template:**

```python
"""Product page on loja.example.com."""
from selectolax.lexbor import LexborHTMLParser

NAME = "loja_example"
MATCH = [r"^https://(www\.)?loja\.example\.com/p/"]   # regexes against the URL

def parse(html: str, url: str) -> dict:
    tree = LexborHTMLParser(html)
    def txt(sel):
        n = tree.css_first(sel)
        return n.text(separator=" ", strip=True) if n else None
    return {
        "title": txt("h1"),
        "price": txt("[data-testid=price]"),
        "items": [li.text(strip=True) for li in tree.css("ul.specs li")],
    }
```

**Steps:**

1. On the target page, look at the structure: `webpilot snapshot`, or `webpilot html -S <container> -o tmp.html`
   and read the file.
2. Save a fixture with `webpilot parser fixture <NAME>`. This writes `parsers_user/fixtures/<NAME>/*.html` with the
   URL on the first line. For content inside an iframe, add `--frame <text in its URL>`; once the parser exists,
   the iframe its `MATCH` selects is saved automatically.
3. Write the parser. Prefer stable selectors: `id`, `data-*`, `aria-*` and semantic tags. Avoid random CSS class
   names.
4. Test it with `webpilot parser test <NAME> --show` (`uv run --project <webpilot> pytest` also tests every
   fixture).
5. Use it with `webpilot extract`.

**Rules:** parsers are pure. They take HTML and return a dict or list, with no network access and no browser.
Return `{}` or `[]` when nothing is found; `reflect-data` flags that as a possible layout change.
`webpilot parser list` shows the parsers, their patterns, fixtures and load errors.

**Repeated flows** (quizzes, wizards): a parser can also return the targets to act on (`"next": "text=Next"`,
`"answer": "#answer_2"`), so each step is `extract` + `click <target> --wait-text <next>` with no snapshot.

## Site notes

Write site notes (workflows, quirks, where to click, which `--selector` to read) in `parsers_user/NOTES.md`, one
`##` heading per domain. `webpilot script` lists the notes files; agents read only the section of the site they
are on. Keep what was confirmed apart from what was guessed: mark a guess `hypothesis:`.

## Scripts

A flow that will be run again (a loop, API calls with the browser session) goes in
`parsers_user/scripts/<name>.py`, run with `webpilot script <name> [args]`. It uses the Python API
([python-api.md](python-api.md)).

- The first line of its docstring says what it does (`webpilot script` shows it), and argparse `help=` describes
  each argument (`webpilot script <name> --help` shows them). The note only points at the script, so the arguments
  are described in one place.
- Files starting with `_` are helpers a script can import; they are not listed.
- A bad argument, or a page or API that is missing, must exit non-zero with a message saying what failed, never
  with empty output and exit 0.

## Lookup order

`WEBPILOT_PARSERS_DIR` (when set), then `parsers_user/` in the WebPilot clone, for parsers, `scripts/` and
`NOTES.md` alike, from any working directory. A parser or script found first wins over one of the same name later;
every `NOTES.md` found counts. Fixtures are read only from the clone's `parsers_user/fixtures/`.
