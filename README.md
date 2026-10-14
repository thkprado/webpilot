# WebPilot

**English** · [Português](README.pt-BR.md)

Lets coding agents (Claude Code, Codex, Gemini CLI/Antigravity, pi, Cursor, or anything with a shell) drive a browser:

- **real**: your own Edge/Chrome, with your sessions and logins, through the WebPilot extension.
- **temp**: a temporary Chromium with a throwaway profile (`--temp`).

Agent tabs in the real browser go into a purple tab group named **WebPilot**. **Agents: this file is all you need. Read it fully before using the browser.**

---

## 1. Setup (once, by the user)

### Let your AI set it up

Do you use an AI coding assistant (Claude Code, Codex, Gemini CLI/Antigravity, Cursor, ...)? Paste this into it:

```text
Set up WebPilot on this machine for me: https://github.com/thkprado/webpilot - follow docs/AI_SETUP.md in that repository.
```

It checks your tools (Git, Python, uv, Node.js, Edge/Chrome), clones and builds the extension, configures the daemon and
verifies it. The only thing it cannot do is click in your browser: it gives you the exact steps to load the extension
(step "Load unpacked" below). It asks before touching any of your agent instruction files. The steps it follows are in
[docs/AI_SETUP.md](docs/AI_SETUP.md).

### Or do it yourself

`<webpilot>` stands for the folder where you cloned this repository, for example `C:\src\webpilot` or `~/src/webpilot`.

```powershell
cd <webpilot>                                           # the folder where you cloned this repository
cd extension; npm install; npm run build; cd ..       # build the extension into extension/dist
uv sync
uv run webpilot setup                                   # create token + extension/dist/config.json
uv tool install --editable .                            # optional: `webpilot` available in any folder
```

In Edge, open `edge://extensions`, turn on **Developer mode**, click **Load unpacked** and pick `extension/dist`. The extension icon shows a badge:

| Badge | Meaning |
|---|---|
| `ON` | connected to the daemon |
| `OFF` | daemon not running (it starts on the first `webpilot` command) |
| `CFG` | run `webpilot setup` again |
| `DUP` | another connected profile already uses this profile name; rename one (below) |

Click the icon for a popup with the connection state and this profile's name.

**Several Edge profiles.** Load `extension/dist` the same way in each profile; they all share one daemon. Each profile gets a random name (`profile-1a2b`). To rename it, click the extension icon in that profile and edit the name in the popup, or use `webpilot profile list` (shows the active tab of each) and `webpilot profile rename profile-1a2b work`. With one profile connected nothing changes. With several, commands need `--profile NAME` (or `-p`), `WEBPILOT_PROFILE=NAME`, or `"profile": "NAME"` in `~/.webpilot/config.json` as the default; otherwise they fail and list the connected names.

The daemon (`webpilot serve`) starts automatically in the background. It listens only on `127.0.0.1`, requires the token from `~/.webpilot/config.json`, and rejects connections from web pages.

Without `uv tool install`, use `uv run --project <webpilot> webpilot ...`.

### Making WebPilot known to other agents

Agents only use WebPilot if their instructions mention it. Run `uv tool install --editable .` first (so `webpilot` works in any folder; check with `webpilot status`), then paste this snippet into each harness's instruction file, replacing `<webpilot>` with the absolute path of your WebPilot folder. It only points here, so this README stays the single source of truth:

```markdown
## Browser (WebPilot)
To browse the web, read pages, search, or interact with sites, use the `webpilot` CLI.
It drives the user's real Edge (logged-in sessions) or a temporary browser (`--temp`).
Before first use in a session, read <webpilot>/README.md fully (sections 2+).
Real browser = the user's real accounts: never buy, send, delete, or change settings without asking.
```

| Harness | Global (all projects) | Per project |
|---|---|---|
| Claude Code | `~/.claude/CLAUDE.md` | `CLAUDE.md` |
| Codex CLI | `~/.codex/AGENTS.md` | `AGENTS.md` |
| Gemini CLI / Antigravity | `~/.gemini/GEMINI.md` | `GEMINI.md` or `AGENTS.md` |
| pi | `~/.pi/agent/AGENTS.md` | `AGENTS.md` |
| Cursor | Settings → Rules → User Rules | `AGENTS.md` or `.cursor/rules/webpilot.mdc` |
| Anything else with a shell | its system prompt / rules file | `AGENTS.md` |

Harnesses that support Agent Skills (Claude Code `~/.claude/skills/`, Codex `~/.codex/skills/`) can get a `webpilot/SKILL.md` instead, with frontmatter `name: webpilot` and `description: Drive a web browser (real Edge or temporary). Use when browsing, searching or interacting with websites.` plus the same body. A skill loads only when relevant instead of in every session.

Without `uv tool install`, replace `webpilot` in the snippet with `uv run --project <webpilot> webpilot`.

## 2. Agent quick reference

```bash
webpilot goto https://site.com -s        # navigate + print snapshot (-s)
webpilot snapshot                        # page text with refs: [e12 button "Send"]
webpilot snapshot -i                     # only interactive elements (short)
webpilot snapshot -S "main"              # only one CSS subtree
webpilot click e12                       # click by ref | CSS selector | text=Label | text=Next|Próximo|›
webpilot click e12 -s                    # ...then print a snapshot of the resulting page
webpilot click e12 --wait-text "Step 2"  # ...then wait for the next state (--wait-for SELECTOR also works)
webpilot submit [e7] -s                  # submit the form around e7 (or the focused/first form)
webpilot type e7 "hello" --submit        # fill and press Enter
webpilot type "select#country" "Brazil"  # choose a <select> option by text
webpilot select e16 "billing"            # choose in a custom dropdown (role=combobox, react-select) or a <select>
webpilot press Escape                    # keys: Enter Tab Escape ArrowDown PageDown a Control+a ...
webpilot scroll down | up | top | bottom | e40
webpilot wait --text "Order confirmed" --timeout 20
webpilot wait --text "Loading" --gone    # wait until it disappears
webpilot extract [URL]                   # site parser JSON, or snapshot + hint if there is no parser
webpilot search "query" -n 5             # Google (default) | -e ddg ; prints title/url/snippet JSON
webpilot text -S article                 # plain innerText
webpilot html -S "#content" -o page.html # raw HTML (large! prefer snapshot/extract)
webpilot eval "document.title"           # JS in the page; returns JSON
webpilot eval "fetch('/api/x').then(r=>r.json())" --timeout 300   # promises are awaited (default 60 s)
webpilot eval "(t) => (document.querySelector('#body').value = t).length" --arg @notes.md   # data as arguments
webpilot fetch /api/items [-H "K: V"] [--timeout 120] [-o file] [--raw]   # HTTP with the tab's session; JSON out
webpilot screenshot [-o file.png] [--full]   # prints the path; open the image to look at it
webpilot tabs | tab new [URL] | tab use ID | tab close [ID] | tab info
webpilot back | forward | reload
webpilot captcha                         # click an "I'm not a robot" checkbox (always on request)
webpilot --temp <command>                # use the temporary browser (starts automatically)
webpilot --tab ID <command>              # act on a specific tab once
webpilot -p NAME <command>               # use this Edge profile (only needed when several are connected)
webpilot profile list                    # connected profiles and the active tab of each
webpilot status                          # daemon / extension status
```

Structured results are printed as JSON. Snapshots are printed as text. Errors go to stderr with exit code 1.

### Recommended workflow

1. Reach the page with `goto URL -s`, or with `search "..."` followed by `goto`.
2. If you only need data, use `extract`. When a parser exists it returns compact JSON. Parsers also match iframes: when the page itself has none, the first iframe with one is parsed (`"frame"` and `"page_url"` in the result). On repeated flows (quizzes, wizards), a parser can return the targets to act on (`#answer_2`, `text=Next`), so each step is `extract` + `click <target> --wait-text <next>` with no snapshot.
3. If you need to interact, run `snapshot -i` to see the refs, then `click`/`type` with them. Refs (`e12`) stay valid until the page navigates; after a navigation, take a new snapshot. If the page re-renders an element (AJAX), its ref is found again by kind and label (`"reresolved": true` in the result).
   **Iframes** (embedded quizzes, forms, widgets, even from other domains) are shown inline between `[iframe ...]` and `[/iframe]`, and their refs carry the frame: `f11e3`. Use them like any ref. CSS selectors and `text=` targets (which also match `aria-label`), `html -S`/`text -S`, and `wait --text`/`--wait-text` look inside iframes when the main page has no match. `eval` runs only in the main page.
4. Actions (`click`, `type`, `select`, `press`, `submit`) wait up to `--timeout` (5 s) for the target to appear and be enabled. Afterwards they wait for the page to settle: page load, no XHR/fetch in flight, and no DOM changes for 0.5 s. `"changed": false` means the page did not react; `"busy": "dom"` (or `"network"`) means the page never went quiet and the wait gave up. On step-by-step flows (quizzes, wizards), use `click ... -s` or `submit -s` to act and read the next step in one command. Add `--wait-text`/`--wait-for` when the next step has a known marker; the command exits 1 if the marker never appears. With a marker, pages that never go quiet (a running clock) cost 1.5 s per action instead of 5 s; for a checkbox, its own `:checked` state works as the marker (`--wait-for "#opt:checked"`).
5. **Custom dropdowns** (`role=combobox`, such as react-select): the snapshot shows them as `[e16 combobox "How can we help?" value="I have an account or billing issue" expanded=false]`, with the value the field shows. In an open list, options are marked ` selected` (the current value) and ` active` (the one the arrow keys are on). `select <ref> <text>` chooses in one command. It types the text to filter when the field is searchable, moves to the option with the arrow keys and presses Enter, all with synthetic events, then checks what the field shows (`"option"` and `"value"` in the result). It exits 1 when no option matches (the error lists them) or the field does not show the option afterwards. Clicking the input, then an option, or pressing keys across several commands breaks if the menu closes in between (it closes when the browser window loses focus). When you do `click` an option of a combobox, the result says whether the field now shows it: `"selected": true`, or `"selected": false` with the field's `"value"` and a `"hint"` with the `select` command to run instead.
6. For long pages, narrow the read with `snapshot -S <selector>` or `--max N` instead of reading everything.
7. Visual checks: `screenshot`, then open the PNG.
8. **Data into `eval`: pass it as arguments, never paste it into the code.** Text spliced into a JS string breaks on quotes, backticks and line breaks, and an escape lost along the way (`\\n` that arrives as a real line break) is a syntax error. Instead, make the expression a function and pass the values: `eval "(t) => ..." --arg TEXT` (repeatable; `--arg @FILE` reads a file, `@-` stdin, `@@x` is the literal `@x`), `--args-json '[...]'` for other JSON values, or `eval(fn, args=[...])` in Python. The values travel as JSON, separately from the code. Syntax errors report the line, the column and an excerpt with a caret, line breaks shown as `⏎`:
   ```text
   error: SyntaxError: Invalid or unexpected token at line 2, column 24:
     …#release_body');⏎  return t.value.split('⏎')[0]; })()
                                              ^
   ```

### Rules for agents

- **Real browser = the user's real accounts.** Do not buy anything, send messages, delete data, change settings or accept terms without explicit confirmation from the user.
- Only operate the user's other tabs (`tab use`) when asked. New tabs go into the WebPilot group.
- **Browser profiles are separate accounts**, possibly of different people. If a command fails with "several browser profiles are connected", ask the user which profile to use (`webpilot profile list` shows the names); never pick one yourself. Once told, pass `-p NAME` on every command (or `Browser(profile=NAME)`) and do not switch profiles without being asked.
- Captcha: `goto` does not touch captchas unless the user enabled `"auto_captcha": true` in `~/.webpilot/config.json` (off by default); then it clicks "I'm not a robot" checkboxes automatically (result in the `captcha` field). `webpilot captcha` clicks one on request. If `challenge: true` appears, **stop and ask the user** to solve it in the browser, then continue. Never try to solve image challenges.
- Logins: in the real browser the user's sessions already exist. If a login is needed, ask the user to sign in; do not type passwords unless the user provides them for that purpose.
- `fetch` calls a site's API with the user's session, from the current tab's page (relative URLs resolve against it; another origin works only if it allows CORS). It prints `status`, `headers` and `body` (parsed when JSON) and exits 1 on HTTP errors. Methods other than GET/HEAD are refused unless you pass `--allow-write`, which you may only do after the user confirmed that request.
- Prefer `click`/`type` without `--trusted`. Use `--trusted` (real mouse/keyboard input via the debugger API) only when the page ignores the synthetic click. It shows the "debugging this browser" bar for about 20 s. Real input is lost when the browser window is minimized or covered by other windows, so `click --trusted`, `type --trusted`/`--submit` and `press` fail first with an error saying so (the agent's tab may be in the background of a visible window).

### Python API

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

Methods: `goto, back, forward, reload, snapshot, html, text, click, type, select, press, submit, scroll, wait, eval, fetch, screenshot, captcha, extract, search, tabs, new_tab, use_tab, close_tab, info, status`. `click`/`type`/`select`/`press`/`submit` take `timeout=`, `wait_text=`, `wait_selector=` and `wait_timeout=`. `eval(expression, timeout=60, args=None)` awaits promises for up to `timeout` seconds; with `args` (a list of JSON values), `expression` must be a function and is called with them, and only their number and size go to the session log. `fetch(url, method="GET", headers=None, data=None, json=None, timeout=120, allow_write=False, raw=False)` returns `{"status", "statusText", "url", "headers", "body"}`; `body` is parsed JSON (unless `raw`), text, or bytes for binary content.

Run scripts with `uv run --project <webpilot> python script.py`.

### Site APIs with the browser session

When a site the user is logged into has a JSON API (dashboards, admin panels), call it with `fetch` instead of reading pages: open the site once, then use relative URLs. Example with Grafana querying Loki through its datasource proxy:

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

From the CLI: `webpilot fetch /api/datasources`. Loki limits worth knowing:

- `limit` above `max_entries_limit_per_query` (usually 5000) is rejected: split long ranges into smaller windows.
- A query returns at most 500 series: narrow the label selector or aggregate.
- Log lines written as JSON carry accents escaped (`ç`), so a regex with `ç`/`ã` never matches: use `.` in their place (`conex.o`).

## 3. Site parsers (do this for sites you visit often)

A parser turns a site's HTML into compact JSON, so you do not have to read the whole page again. `extract` uses one automatically whenever the URL matches.

**When to write one:** the same site is read two or more times, or `reflect-data` suggests it.

**Where:** `parsers_user/<name>.py`. It is found automatically and takes precedence over the built-in parsers. Built-in parsers live in `src/webpilot/parsers/` (google, duckduckgo), with their fixtures in `tests/fixtures/`.

`parsers_user/` is local to each user and is not versioned (it is in `.gitignore`): fixtures are saved pages, and notes and scripts reflect your own browsing. To start one, copy the example: `cp -r examples/parsers_user parsers_user` (a Hacker News parser with its fixture, `NOTES.md` and `scripts/hn_top.py`).

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

1. On the target page, look at the structure: `webpilot snapshot`, or `webpilot html -S <container> -o tmp.html` and read the file.
2. Save a fixture with `webpilot parser fixture <NAME>`. This writes `parsers_user/fixtures/<NAME>/*.html` with the URL on the first line. For content inside an iframe, add `--frame <text in its URL>`; once the parser exists, the iframe its `MATCH` selects is saved automatically.
3. Write the parser. Prefer stable selectors: `id`, `data-*`, `aria-*` and semantic tags. Avoid random CSS class names.
4. Test it with `webpilot parser test <NAME> --show` (`uv run pytest` also tests every fixture).
5. Use it with `webpilot extract`.

Rules: parsers are pure. They take HTML and return a dict or list, with no network access and no browser. Return `{}` or `[]` when nothing is found; `reflect-data` flags that as a possible layout change. `webpilot parser list` shows the parsers, their patterns, fixtures and load errors.

Write site notes (workflows, quirks, where to click) in `parsers_user/NOTES.md`.

## 4. Reflection (end of session)

Every action is logged in `~/.webpilot/sessions/<date>.jsonl`. Typed text is not logged, only its length.

```bash
webpilot reflect-data              # today's session; --days 7, --session NAME, --json
```

It reports domains read without a parser, repeated interactive flows (snapshots taken only to find refs before clicking; iframe content counts for the iframe's domain), parser failures, empty parser results, large outputs, repeated errors and slow commands, each with a suggestion. The full procedure is in `docs/reflect.md`. In Claude Code, use `/reflect` in this project.

## 5. Reference

| Item | Location |
|---|---|
| Config/token | `~/.webpilot/config.json` (`port`, `auto_captcha` (default `false`), `blocked_domains`, `profile`); rerun `webpilot setup` after editing it |
| Daemon log | `~/.webpilot/daemon.log` |
| Screenshots | `~/.webpilot/screenshots/` |
| Temporary browser | Chromium from Playwright; profile in `%TEMP%\webpilot-temp-*`, deleted by `webpilot temp stop` (or `webpilot stop`, which also stops the daemon); `webpilot temp start --headless` for headless. It starts with Chromium's occlusion detection off, so a window covered by others still takes real input; a minimized one does not |

- `blocked_domains` (for example `["mybank.example.com"]`) prevents the agent from navigating to or operating on those domains in the real browser.
- Environment variables: `WEBPILOT_MODE=temp`, `WEBPILOT_SESSION=name`, `WEBPILOT_PROFILE=name`, `WEBPILOT_HEADLESS=1`, `WEBPILOT_PORT`, `WEBPILOT_DIR`, `WEBPILOT_PARSERS_DIR`.

### Troubleshooting

| Error | What to do |
|---|---|
| "extension (real browser) is not connected" | Edge must be open with the extension loaded; check the badge and `webpilot status`. After it was idle, the first connection can take up to 30 s. |
| "several browser profiles are connected" | Ask the user which profile to use, then add `-p NAME`. The user can set a default with `"profile"` in `~/.webpilot/config.json`. |
| "browser profile 'X' is not connected" | That profile's Edge window is closed or its extension is off; the error lists the connected names. |
| "could not run script in this tab" | Restricted page (`edge://`, the extension store, PDF). Navigate to a normal page. |
| `fetch`: "open the site first" | `fetch` runs from the current tab's page: `goto` the site, then repeat. |
| `fetch`: "C:/Program Files/Git/... is a Windows path" | Git Bash rewrote the relative URL. Prefix the command with `MSYS_NO_PATHCONV=1`, or pass the full URL. |
| "ref eN not found" / "ref eN (...) is gone" | The page navigated or the element disappeared; run `snapshot` again. |
| Action returned `"changed": false` | The click did nothing: try `--trusted`, `submit`, or another element. |
| Dropdown option clicked (`"changed": true`, `"selected": false`) or chosen with keys, but nothing was chosen | Use `select <combobox ref> <text>` (the `hint` in the result has it): one command, so the menu cannot close in between. "not a combobox": target the input with `role=combobox` (or an element around it). "no list of options opened": the field is not a listbox-style dropdown; try `click`, then `snapshot -i`. |
| "ref eN (option ...) is gone" after opening a dropdown | The menu closed between commands (it closes when the browser window loses focus). Use `select <combobox ref> <text>`. |
| "the browser window is minimized or covered, so real input would be lost" | From `--trusted`, `type --submit` or `press`. Ask the user to bring the browser window to the front, or use `click`/`type` without `--trusted`, `submit` instead of `--submit`, or `select`. |
| Snapshot after an action still shows "Loading..." | Add `--wait-text`/`--wait-for` with something from the next state, or `wait --text "Loading" --gone`. |
| Google showed "unusual traffic" | Ask the user to solve the captcha, or use `search -e ddg`. |
| Extension console: "WebSocket connection to 'ws://127.0.0.1:8765/' failed: ... ERR_CONNECTION_REFUSED" | Normal while the daemon is not running: the extension retries every few seconds so it connects as soon as the daemon starts. To silence it, turn the extension off in `edge://extensions` and back on before using WebPilot. |
| You changed the extension code | Run `npm run build` in `extension/`, then click reload on the card in `edge://extensions`. |

## 6. Architecture

```
agent ──shell──> webpilot CLI / Python lib ──WebSocket──> daemon (127.0.0.1:8765)
                                                             │  token + extension origin only
                                    ┌────────────────────────┴──────────────────┐
                           extension in Edge (real)                 extension in Chromium (temp)
                           chrome.scripting / chrome.debugger       same code, mode=temp
```

- `extension/src/background.ts`: WebSocket bridge, tabs, navigation, trusted input (CDP via `chrome.debugger`), captcha.
- `extension/src/page.ts`: injected into the page; snapshot with refs, click/type/select, captcha detection.
- `extension/src/popup.ts` + `popup.html`: toolbar popup with the connection state and the profile name.
- `src/webpilot/`: `server.py` (daemon), `client.py` (API), `cli.py`, `registry.py` (parsers), `search.py`, `session_log.py`, `reflect.py`, `temp_browser.py`.

## 7. Security and responsible use

WebPilot gives a program (and the AI agent behind it) control of a browser, so treat it like remote access to your machine:

- In **real** mode the agent acts with your logged-in sessions: email, banking, work tools. Use `blocked_domains` for sites it must never touch, and prefer `--temp` (throwaway profile) when you do not need your accounts.
- The extension requests broad permissions (`<all_urls>`, `debugger`, `scripting`, `webRequest`, `tabs`). Load it only from a build you made yourself from this source, in a browser profile you control.
- The local daemon listens on `127.0.0.1` only and requires the token in `~/.webpilot/config.json`. Keep that file private; anyone who can read it can drive your browser.
- Session logs in `~/.webpilot/sessions/` record URLs and commands (typed text is only logged by length). Saved parser fixtures can contain page content; never commit pages from a logged-in browser.
- You are responsible for following the terms of service of the sites you automate. WebPilot does not solve image captchas, and the automatic checkbox click is opt-in.
- Software is provided "as is", without warranty (see `LICENSE`). Review what an agent is about to do before allowing purchases, messages, deletions or setting changes.

Report vulnerabilities as described in `SECURITY.md`.

## License

[MIT](LICENSE)