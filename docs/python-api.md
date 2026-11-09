# WebPilot: Python API and site APIs

Read this before writing a script that drives the browser, or before calling a site's JSON API with the user's
session. The core guide is [agent.md](agent.md); its rules apply to scripts too.

## Python API

For loops and scripts, the API is faster than many CLI calls because it keeps one connection open:

```python
from webpilot import Browser

with Browser() as b:                    # Browser("temp") for the temporary browser; Browser(profile="work")
    b.goto("https://news.ycombinator.com")
    data = b.extract()                  # {"parser": ..., "data": ...} or {"snapshot": ...}
    snap = b.snapshot(interactive=True)["text"]
    b.click("text=More")
    results = b.search("python uv", n=5)["results"]
```

Run scripts with `uv run --project <webpilot> python script.py` (`<webpilot>` is the WebPilot folder, the parent of
this `docs/` folder).

- Methods: `goto, back, forward, reload, snapshot, html, text, click, type, select, press, submit, scroll, wait, eval,
  fetch, screenshot, captcha, extract, search, tabs, new_tab, use_tab, close_tab, info, status`.
- `click`/`type`/`select`/`press`/`submit` take `timeout=`, `wait_text=`, `wait_selector=` and `wait_timeout=`;
  their result has `waited: {"found", "ms"}`.
- `wait(selector=None, text=None, timeout=10, gone=False)` returns `{"found", "ms"}` and does not raise on a
  timeout: check `found`.
- `eval(expression, timeout=60, args=None)` awaits promises for up to `timeout` seconds. Pass data as `args` (a list
  of JSON values), never pasted into the code: `expression` must then be a function and is called with them, and
  only their number and size go to the session log. Without `args`, `expression` is an expression, not a function
  (`args=[]` calls a function with none).

  ```python
  count = b.eval("document.querySelectorAll('.item').length")          # an expression, no args
  names = b.eval("(sel) => [...document.querySelectorAll(sel)].map(e => e.textContent)", args=[".item .name"])
  ```
- `fetch(url, method="GET", headers=None, data=None, json=None, timeout=120, allow_write=False, raw=False)` returns
  `{"status", "statusText", "url", "headers", "body"}`; `body` is parsed JSON (unless `raw`), text, or bytes for
  binary content. It does not raise on HTTP errors (the CLI exits 1): check `status`. `allow_write=True` (methods other than GET/HEAD) only after the user
  confirmed that request.

A script that will be run again belongs in `parsers_user/scripts/` (see [parsers.md](parsers.md)).

## Site APIs with the browser session

When a site the user is logged into has a JSON API (dashboards, admin panels), call it with `fetch` instead of
reading pages: open the site once, then use relative URLs (they resolve against the current tab's page; another
origin works only if it allows CORS). Example with Grafana querying Loki through its datasource proxy:

```python
from urllib.parse import urlencode
from webpilot import Browser

with Browser() as b:
    b.goto("https://grafana.example.com/")
    ds = b.fetch("/api/datasources")["body"]          # [{"uid", "type", "name", ...}]
    loki = next(d["uid"] for d in ds if d["type"] == "loki")
    q = urlencode({"query": '{app="api"} |~ "conex.o recusada"', "limit": 5000,
                   "start": "2026-10-05T00:00:00Z", "end": "2026-10-05T06:00:00Z"})
    res = b.fetch(f"/api/datasources/proxy/uid/{loki}/loki/api/v1/query_range?{q}", timeout=300)
    streams = res["body"]["data"]["result"]
```

From the CLI: `webpilot fetch /api/datasources` (prints `status`, `headers` and `body`, exits 1 on HTTP errors).
Loki limits worth knowing:

- `limit` above `max_entries_limit_per_query` (usually 5000) is rejected: split long ranges into smaller windows.
- A query returns at most 500 series: narrow the label selector or aggregate.
- Log lines written as JSON carry accents escaped (`ç`), so a regex with `ç`/`ã` never matches: use `.` in
  their place (`conex.o`).
