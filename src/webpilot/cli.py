"""`webpilot` command line. Structured results are printed as JSON; snapshots as plain text."""

from __future__ import annotations

import base64
import json
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import typer

from . import config, reflect, registry, session_log, skills, temp_browser
from .client import EXTENSION_WAIT, Browser, Connection, WebPilotError

app = typer.Typer(no_args_is_help=True, add_completion=False, rich_markup_mode=None,
                  help="Drive your real browser (Chrome, Edge or another Chromium-based browser + WebPilot extension) or a temporary one.")
tab_app = typer.Typer(no_args_is_help=True, help="Manage tabs.")
temp_app = typer.Typer(no_args_is_help=True, help="Temporary browser (Playwright Chromium, throwaway profile).")
parser_app = typer.Typer(no_args_is_help=True, help="Site parsers.")
profile_app = typer.Typer(no_args_is_help=True, help="Browser profiles that have the extension.")
skill_app = typer.Typer(no_args_is_help=True, help="The webpilot skill for coding agents (Claude Code, Codex, Antigravity, pi, Copilot CLI).")
app.add_typer(tab_app, name="tab")
app.add_typer(temp_app, name="temp")
app.add_typer(parser_app, name="parser")
app.add_typer(profile_app, name="profile")
app.add_typer(skill_app, name="skill")

opts: dict = {"mode": None, "tab": None, "profile": None}


@app.callback()
def main(
    temp: bool = typer.Option(False, "--temp", help="Use the temporary browser instead of the real one."),
    tab: Optional[int] = typer.Option(None, "--tab", help="Act on this tab id instead of the current agent tab."),
    profile: Optional[str] = typer.Option(None, "--profile", "-p",
                                          help="Browser profile to drive when several have the extension."),
):
    opts["mode"] = "temp" if temp else None
    opts["tab"] = tab
    opts["profile"] = profile


def browser() -> Browser:
    return Browser(mode=opts["mode"], tab=opts["tab"], profile=opts["profile"])


def out(obj) -> None:
    print(obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False, indent=2))


def print_snapshot(snap: dict) -> None:
    print(f"# {snap.get('title', '')}\n{snap.get('url', '')}\n")
    print(snap["text"])
    if snap.get("truncated"):
        print("\n[truncated: use --max, --selector or --interactive]")


# ------------------------------------------------------------------ setup & daemon

@app.command()
def setup():
    """Create the token and write extension/dist/config.json for the real browser."""
    cfg = config.load()
    dist = config.extension_dist()
    if not (dist / "manifest.json").exists():
        raise WebPilotError(f"extension not built: run `npm install && npm run build` in {dist.parent}")
    path = config.write_extension_config(dist, cfg, "real")
    out(f"Wrote {path}\n\nLoad the extension once:\n"
        f"  1. Open your browser's extensions page (chrome://extensions, edge://extensions, ...)\n"
        f"     and enable Developer mode.\n"
        f"  2. Click 'Load unpacked' and select: {dist}\n"
        f"  3. Run `webpilot status` - the extension badge shows ON when connected.")


@app.command()
def serve():
    """Run the daemon in the foreground (normally started automatically)."""
    from .server import main as serve_main

    cfg = config.load()
    serve_main(cfg["token"], cfg["port"])


@app.command()
def status():
    """Show daemon and extension connection status."""
    cfg = config.load()
    try:
        conn = Connection(cfg, autostart=False)
    except WebPilotError as e:
        out({"daemon": False, "error": str(e)})
        return
    st = conn.request("daemon.status")
    conn.close()
    temp = temp_browser._state_path()
    out({"daemon": True, **st, "temp_browser": json.loads(temp.read_text("utf-8")) if temp.exists() else None})


@app.command()
def stop():
    """Stop the daemon and the temporary browser (which may be headless and otherwise left running unseen)."""
    temp = temp_browser.stop()
    try:
        conn = Connection(config.load(), autostart=False)
    except WebPilotError:
        out({"stopped": False, "reason": "not running", "temp_browser_stopped": temp})
        return
    out({**conn.request("daemon.stop"), "temp_browser_stopped": temp})


# ------------------------------------------------------------------ profiles

@profile_app.command("list")
def profile_list():
    """List the connected browser profiles, with the active tab of each to tell them apart."""
    with Browser(log=False) as b:
        def connected() -> dict:
            return b.status()["extensions"].get("real", {})

        profiles = connected()
        if not profiles:
            # Daemon just started or extensions asleep: wait for the first, then for the others' retry (<= 5 s).
            deadline = time.monotonic() + EXTENSION_WAIT["real"]
            while not profiles and time.monotonic() < deadline:
                time.sleep(0.5)
                profiles = connected()
            if profiles:
                time.sleep(6)
                profiles = connected()
        rows = []
        for name, info in sorted(profiles.items()):
            b.profile = name
            try:
                active = b.call("ping").get("activeTab")
            except WebPilotError as e:
                active = {"error": str(e)}
            rows.append({"profile": name, "version": info.get("version"), "active_tab": active})
    out(rows)


@profile_app.command("rename")
def profile_rename(old: str, new: str):
    """Rename a profile (letters, digits, - and _). The name is stored in that profile's extension."""
    with Browser(profile=old) as b:
        if new in b.status()["extensions"].get("real", {}):
            raise WebPilotError(f"profile name {new!r} is already in use")
        out(b.call("profile.set", name=new))


# ------------------------------------------------------------------ tabs

@app.command()
def tabs():
    """List all tabs (agent=True for tabs in the WebPilot group, current=True for the active agent tab)."""
    out(browser().tabs())


@tab_app.command("new")
def tab_new(url: Optional[str] = typer.Argument(None)):
    """Open a new agent tab (optionally at URL) and make it current."""
    out(browser().new_tab(url))


@tab_app.command("use")
def tab_use(tab_id: int):
    """Make an existing tab (e.g. one the user opened) the current agent tab."""
    out(browser().use_tab(tab_id))


@tab_app.command("close")
def tab_close(tab_id: Optional[int] = typer.Argument(None)):
    """Close a tab (default: the current agent tab)."""
    out(browser().close_tab(tab_id))


@tab_app.command("info")
def tab_info():
    """URL and title of the current agent tab."""
    out(browser().info())


# ------------------------------------------------------------------ navigation & reading

@app.command()
def goto(
    url: str,
    new_tab: bool = typer.Option(False, "--new-tab", help="Open in a new agent tab."),
    snapshot: bool = typer.Option(False, "--snapshot", "-s", help="Print a snapshot after loading."),
    max_chars: int = typer.Option(15000, "--max"),
):
    """Navigate and wait for the page to load. Captcha checkboxes are clicked automatically."""
    b = browser()
    res = b.goto(url, new_tab=new_tab)
    out(res)
    if snapshot:
        print()
        print_snapshot(b.snapshot(max_chars=max_chars))


@app.command()
def back():
    """History back."""
    out(browser().back())


@app.command()
def forward():
    """History forward."""
    out(browser().forward())


@app.command()
def reload():
    """Reload the page."""
    out(browser().reload())


@app.command()
def snapshot(
    selector: Optional[str] = typer.Option(None, "--selector", "-S", help="Only this CSS subtree."),
    interactive: bool = typer.Option(False, "--interactive", "-i", help="Only interactive elements."),
    max_chars: int = typer.Option(15000, "--max"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Compact page text with refs like [e12 button "Send"] usable by click/type."""
    snap = browser().snapshot(selector, max_chars, interactive)
    out(snap) if as_json else print_snapshot(snap)


@app.command()
def html(
    selector: Optional[str] = typer.Option(None, "--selector", "-S"),
    output: Optional[str] = typer.Option(None, "--out", "-o", help="Write to file instead of stdout."),
):
    """Raw outerHTML of the page or of a selector."""
    # Saved to a file, the HTML is not read by the agent: reflect-data does not count it as a read.
    res = browser().html(selector, _log={"purpose": "save"} if output else None)
    if output:
        with open(output, "w", encoding="utf-8") as f:
            f.write(res["html"])
        out({"url": res["url"], "saved": output, "chars": len(res["html"])})
    else:
        print(res["html"])


@app.command()
def text(
    selector: Optional[str] = typer.Option(None, "--selector", "-S"),
    max_chars: int = typer.Option(50000, "--max"),
):
    """Visible text (innerText) of the page or of a selector."""
    res = browser().text(selector, max_chars)
    print(res["text"])


@app.command()
def screenshot(
    output: Optional[str] = typer.Option(None, "--out", "-o"),
    full: bool = typer.Option(False, "--full", help="Whole page instead of the viewport."),
):
    """Save a PNG screenshot and print its path."""
    print(browser().screenshot(output, full))


def read_value(value: str) -> str:
    """`--arg` values: `@FILE` reads a file, `@-` reads stdin, `@@...` is a literal starting with `@`."""
    if value.startswith("@@"):
        return value[1:]
    if value == "@-":
        return sys.stdin.read()
    if value.startswith("@"):
        with open(value[1:], encoding="utf-8") as f:
            return f.read()
    return value


@app.command("eval")
def eval_(
    expression: str,
    timeout: float = typer.Option(60, "--timeout", help="Seconds to wait for the result (promises are awaited)."),
    arg: list[str] = typer.Option([], "--arg", help="Call EXPRESSION (a function) with this string; repeatable. "
                                                    "@FILE reads a file, @- stdin."),
    args_json: Optional[str] = typer.Option(None, "--args-json",
                                            help="Call EXPRESSION (a function) with the values of this JSON array "
                                                 "(or @FILE)."),
    output: Optional[str] = typer.Option(None, "--out", "-o",
                                         help="Write the result to a file: a base64 data URL is decoded, other "
                                              "strings are written as text, other values as JSON."),
):
    """Evaluate JavaScript in the page (CSP-proof; promises are awaited). Prints the JSON result.

    With --arg or --args-json, EXPRESSION must be a function, called with those values; they are sent as
    data, so long or quoted text needs no escaping: eval "(t) => t.length" --arg @notes.md
    With --out, the result goes to a file: eval "document.querySelector('canvas').toDataURL()" -o chart.png"""
    if arg and args_json is not None:
        raise typer.BadParameter("use --arg or --args-json, not both", param_hint="--args-json")
    values: Optional[list] = None
    if args_json is not None:
        values = json.loads(read_value(args_json))
        if not isinstance(values, list):
            raise typer.BadParameter("must be a JSON array", param_hint="--args-json")
    elif arg:
        values = [read_value(a) for a in arg]
    # Saved to a file, the result is not read by the agent (like `html -o`).
    res = browser().eval(expression, timeout=timeout, args=values, _log={"purpose": "save"} if output else None)
    if not output:
        out(res)
        return
    data_url = re.fullmatch(r"data:([^,]*?);base64,(.*)", res, re.S) if isinstance(res, str) else None
    if data_url:
        content = base64.b64decode(data_url[2])
    else:
        content = (res if isinstance(res, str) else json.dumps(res, ensure_ascii=False, indent=2)).encode("utf-8")
    with open(output, "wb") as f:
        f.write(content)
    saved = {"saved": output, "bytes": len(content)}
    if data_url:
        saved["type"] = data_url[1].split(";")[0] or "text/plain"
    out(saved)


@app.command()
def fetch(
    url: str = typer.Argument(..., help="Absolute, or relative to the current tab's page."),
    method: str = typer.Option("GET", "--method", "-X"),
    header: list[str] = typer.Option([], "--header", "-H", help='"Name: value"; repeatable.'),
    data: Optional[str] = typer.Option(None, "--data", "-d", help="Request body."),
    json_: Optional[str] = typer.Option(None, "--json", help="JSON request body (sets Content-Type)."),
    timeout: float = typer.Option(120, "--timeout"),
    output: Optional[str] = typer.Option(None, "--out", "-o", help="Write the body to a file."),
    raw: bool = typer.Option(False, "--raw", help="Print only the body, as received."),
    allow_write: bool = typer.Option(False, "--allow-write",
                                     help="Allow methods other than GET/HEAD (only after the user confirmed)."),
):
    """HTTP request from the current tab's page, with its cookies and session. Prints status, headers and
    body (parsed when JSON); exits 1 on HTTP errors."""
    if re.match(r"[A-Za-z]:[/\\]", url):
        raise WebPilotError(f"{url} is a Windows path: Git Bash rewrote the relative URL. "
                            "Prefix the command with MSYS_NO_PATHCONV=1, or pass the full URL.")
    headers = {}
    for h in header:
        name, sep, value = h.partition(":")
        if not sep or not name.strip():
            raise typer.BadParameter(f"expected 'Name: value', got {h!r}", param_hint="--header")
        headers[name.strip()] = value.strip()
    body = json.loads(json_) if json_ is not None else None
    # Saved to a file, the body is not read by the agent (like `html -o`).
    res = browser().fetch(url, method, headers, data, body, timeout, allow_write, raw=bool(output or raw),
                          _log={"purpose": "save"} if output else None)
    content = res["body"]
    if output:
        if not isinstance(content, bytes):
            content = (content or "").encode("utf-8")
        with open(output, "wb") as f:
            f.write(content)
        out({"url": res["url"], "status": res["status"], "saved": output, "bytes": len(content)})
    elif raw:
        if isinstance(content, bytes):
            sys.stdout.buffer.write(content)
        else:
            print(content or "", end="")
    else:
        if isinstance(content, bytes):
            res["body"] = f"<{len(content)} bytes of binary data: use -o FILE>"
        out(res)
    if res["status"] >= 400:
        raise WebPilotError(f"HTTP {res['status']} {res.get('statusText') or ''}".strip())


# ------------------------------------------------------------------ interaction

WAIT_TEXT = typer.Option(None, "--wait-text", "-t", help="Afterwards, wait until this text is on the page.")
WAIT_FOR = typer.Option(None, "--wait-for", help="Afterwards, wait until this CSS selector is visible.")
WAIT_TIMEOUT = typer.Option(10, "--wait-timeout", help="Seconds for --wait-text/--wait-for.")
TARGET_TIMEOUT = typer.Option(5, "--timeout", help="Seconds to wait for the target to appear and be enabled.")
SNAP = typer.Option(False, "--snapshot", "-s", help="Print a snapshot afterwards.")


def act_done(b: Browser, res: dict, snapshot: bool, max_chars: int = 15000) -> None:
    """Print an action's result (+ snapshot); exit 1 if the --wait-text/--wait-for condition never came."""
    out(res)
    if snapshot:
        print()
        print_snapshot(b.snapshot(max_chars=max_chars))
    if res.get("waited", {}).get("found") is False:
        raise WebPilotError("the --wait-text/--wait-for condition did not appear")


@app.command()
def click(
    target: str = typer.Argument(..., help="Ref (e12), CSS selector, or text=Label (text=Next|Próximo|› tries each)"),
    trusted: bool = typer.Option(False, "--trusted", help="Real mouse event via the debugger API."),
    timeout: float = TARGET_TIMEOUT,
    wait_text: Optional[str] = WAIT_TEXT,
    wait_for: Optional[str] = WAIT_FOR,
    wait_timeout: float = WAIT_TIMEOUT,
    snapshot: bool = SNAP,
):
    """Click an element, then wait for the page to settle (navigation or AJAX)."""
    b = browser()
    act_done(b, b.click(target, trusted, timeout=timeout, wait_text=wait_text, wait_selector=wait_for,
                        wait_timeout=wait_timeout), snapshot)


@app.command("type")
def type_(
    target: str,
    value: str,
    append: bool = typer.Option(False, "--append", help="Keep existing content."),
    submit: bool = typer.Option(False, "--submit", help="Press Enter afterwards."),
    trusted: bool = typer.Option(False, "--trusted", help="Real keyboard input via the debugger API."),
    timeout: float = TARGET_TIMEOUT,
    wait_text: Optional[str] = WAIT_TEXT,
    wait_for: Optional[str] = WAIT_FOR,
    wait_timeout: float = WAIT_TIMEOUT,
    snapshot: bool = SNAP,
):
    """Fill an input/textarea/contenteditable, or pick a <select> option by text."""
    b = browser()
    act_done(b, b.type(target, value, clear=not append, submit=submit, trusted=trusted, timeout=timeout,
                       wait_text=wait_text, wait_selector=wait_for, wait_timeout=wait_timeout), snapshot)


@app.command()
def select(
    target: str = typer.Argument(..., help="The combobox (role=combobox) or <select>, or an element around it."),
    text: str = typer.Argument(..., help="Option text: an exact match (ignoring case) beats the shortest one containing it."),
    timeout: float = TARGET_TIMEOUT,
    wait_text: Optional[str] = WAIT_TEXT,
    wait_for: Optional[str] = WAIT_FOR,
    wait_timeout: float = WAIT_TIMEOUT,
    snapshot: bool = SNAP,
):
    """Choose an option in a custom dropdown (react-select and the like) or a <select>, in one command."""
    b = browser()
    act_done(b, b.select(target, text, timeout=timeout, wait_text=wait_text, wait_selector=wait_for,
                         wait_timeout=wait_timeout), snapshot)


@app.command()
def press(
    key: str = typer.Argument(..., help="Enter, Tab, Escape, ArrowDown, PageDown, a, Control+a ..."),
    wait_text: Optional[str] = WAIT_TEXT,
    wait_for: Optional[str] = WAIT_FOR,
    wait_timeout: float = WAIT_TIMEOUT,
    snapshot: bool = SNAP,
):
    """Press a key in the current tab."""
    b = browser()
    act_done(b, b.press(key, wait_text=wait_text, wait_selector=wait_for, wait_timeout=wait_timeout), snapshot)


@app.command()
def submit(
    target: Optional[str] = typer.Argument(None, help="Element inside the form, or its submit button (default: focused/first form)."),
    timeout: float = TARGET_TIMEOUT,
    wait_text: Optional[str] = WAIT_TEXT,
    wait_for: Optional[str] = WAIT_FOR,
    wait_timeout: float = WAIT_TIMEOUT,
    snapshot: bool = SNAP,
):
    """Submit a form like its submit button would (runs the page's handlers), then wait for the page to settle."""
    b = browser()
    act_done(b, b.submit(target, timeout=timeout, wait_text=wait_text, wait_selector=wait_for,
                         wait_timeout=wait_timeout), snapshot)


@app.command()
def scroll(to: str = typer.Argument("down", help="down | up | top | bottom | ref | selector"),
           amount: Optional[int] = typer.Option(None, "--px")):
    """Scroll the page or bring an element into view."""
    out(browser().scroll(to, amount))


@app.command()
def wait(
    selector: Optional[str] = typer.Option(None, "--selector", "-S"),
    text_: Optional[str] = typer.Option(None, "--text", "-t"),
    timeout: float = typer.Option(10, "--timeout"),
    gone: bool = typer.Option(False, "--gone", help="Wait until it disappears instead."),
):
    """Wait for a selector to be visible and/or text to appear (or, with --gone, to disappear)."""
    if not selector and not text_:
        raise WebPilotError("give --selector and/or --text")
    out(browser().wait(selector, text_, timeout, gone))


@app.command()
def captcha():
    """Click a visible 'I'm not a robot' checkbox. Visual challenges are left to the user."""
    out(browser().captcha())


# ------------------------------------------------------------------ parsers & search

@app.command()
def extract(url: Optional[str] = typer.Argument(None, help="Navigate here first (default: current tab)."),
            max_chars: int = typer.Option(15000, "--max")):
    """Structured JSON from a matching site parser, else a snapshot plus a hint to write one."""
    out(browser().extract(url, max_chars))


@app.command()
def search(
    query: str,
    n: int = typer.Option(10, "-n", help="Number of results."),
    engine: str = typer.Option("google", "--engine", "-e", help="google | ddg"),
    lang: Optional[str] = typer.Option(None, "--lang", help="Interface language, e.g. pt-BR"),
    new_tab: bool = typer.Option(False, "--new-tab"),
):
    """Web search in the browser session; prints title/url/snippet JSON."""
    out(browser().search(query, n=n, engine=engine, lang=lang, new_tab=new_tab))


@parser_app.command("list")
def parser_list():
    """List parsers, their URL patterns and fixtures."""
    parsers, errors = registry.load_all()
    out({
        "parsers": [
            {"name": p.name, "file": str(p.path), "match": [r.pattern for r in p.patterns],
             "fixtures": len(registry.fixture_files(p.name))}
            for p in parsers
        ],
        "load_errors": [{"file": str(f), "error": e} for f, e in errors],
    })


@parser_app.command("fixture")
def parser_fixture(
    name: str,
    frame: Optional[str] = typer.Option(None, "--frame", help="Save the iframe whose URL contains this text."),
):
    """Save the current tab's HTML as a test fixture for parser NAME.

    For content inside an iframe, pass --frame, or write the parser first: the frame its MATCH
    patterns select is then saved instead of the page around it.
    """
    page = browser().html(frames=True, _log={"purpose": "fixture"})
    frames = page.get("frames") or []
    if frame:
        page = next((f for f in frames if frame in f["url"]), None)
        if page is None:
            raise typer.BadParameter(f"no iframe URL contains {frame!r}; frames: {[f['url'] for f in frames]}")
    elif (parser := registry.get(name)) and not parser.matches(page["url"]):
        page = next((f for f in frames if parser.matches(f["url"])), page)
    d = registry.fixtures_dir(name)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{time.strftime('%Y%m%d-%H%M%S')}.html"
    path.write_text(f"<!-- url: {page['url']} -->\n{page['html']}", "utf-8")
    out({"saved": str(path), "url": page["url"], "chars": len(page["html"])})


@parser_app.command("test")
def parser_test(name: Optional[str] = typer.Argument(None, help="Parser name (default: all with fixtures)."),
                show: bool = typer.Option(False, "--show", help="Print the full parsed output.")):
    """Run parsers against their saved fixtures."""
    parsers, errors = registry.load_all()
    for f, e in errors:
        print(f"LOAD ERROR {f}: {e}")
    failed = bool(errors)
    for p in parsers:
        if name and name not in (p.name, p.path.stem):
            continue
        fixtures = registry.fixture_files(p.name)
        if name and not fixtures:
            print(f"{p.name}: no fixtures (run `webpilot parser fixture {p.name}` on a matching page)")
        for fx in fixtures:
            url, page_html = registry.read_fixture(fx)
            try:
                data = p.parse(page_html, url)
            except Exception as e:  # noqa: BLE001
                failed = True
                print(f"FAIL {p.name} {fx.name}: {type(e).__name__}: {e}")
                continue
            summary = {k: (len(v) if isinstance(v, (list, dict)) else v) for k, v in data.items()} \
                if isinstance(data, dict) else {"items": len(data)}
            status = "OK  " if data else "EMPTY"
            failed |= not data
            print(f"{status} {p.name} {fx.name}: {json.dumps(summary, ensure_ascii=False)}")
            if show:
                out(data)
    raise typer.Exit(1 if failed else 0)


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True,
                                "allow_interspersed_args": False})
def script(ctx: typer.Context, name: Optional[str] = typer.Argument(None, help="Script name (no .py).")):
    """Run a local script; everything after its name (--help too) is passed to it. No name: list scripts and notes.

    Scripts are found in scripts/ of WEBPILOT_PARSERS_DIR, then of parsers_user/ (the first one wins by name).
    """
    import runpy

    if (env := registry.env_dir()) and not env.is_dir():
        print(f"warning: WEBPILOT_PARSERS_DIR is not a folder: {env}", file=sys.stderr)
    searched = "\n".join(f"  {d}" for d in registry.script_dirs(existing=False))
    if not name:
        list_scripts(searched)
        return
    path = registry.find_script(name)
    if path is None:
        raise WebPilotError(f"script not found: {name}. Searched:\n{searched}\nRun `webpilot script` to list them.")
    argv, sys_path = sys.argv, sys.path[:]
    sys.argv = [str(path), *ctx.args]
    sys.path.insert(0, str(path.parent))  # as `python script.py` does, so a script can import a sibling _helper.py
    try:
        runpy.run_path(str(path), run_name="__main__")  # its SystemExit (argparse: --help 0, bad argument 2) is ours
    finally:
        sys.argv, sys.path[:] = argv, sys_path


def list_scripts(searched: str) -> None:
    found, shadowed, errors = registry.scripts()
    by_dir: dict[Path, list[str]] = {}
    for s in found:
        by_dir.setdefault(s.path.parent, []).append(f"  {s.name:24} {s.doc}".rstrip())
    for path, by in shadowed:
        by_dir.setdefault(path.parent, []).append(f"  {path.stem:24} (shadowed by {by})")
    for d, lines in by_dir.items():
        print(f"{d}:\n" + "\n".join(lines))
    if not found and not shadowed and not errors:
        root = registry.PROJECT_ROOT
        hint = f"Copy {root / 'examples' / 'parsers_user' / 'scripts' / 'hn_top.py'} into one of them to start."
        if not (root / "parsers_user").is_dir():
            hint = f"To start from the example, run in {root}: cp -r examples/parsers_user parsers_user"
        print(f"No scripts. Searched:\n{searched}\n{hint}")
    notes = registry.notes_files()
    if notes:
        print("\nSite notes (read the site's ## section before a flow):\n" + "\n".join(f"  {n}" for n in notes))
    for path, e in errors:
        print(f"error: {path}: {e}", file=sys.stderr)
    if errors:
        raise typer.Exit(1)


# ------------------------------------------------------------------ agent skill

HARNESS_ARG = typer.Argument(None, help=f"Harness(es): {', '.join(skills.HARNESSES)} (agy = antigravity).")
ALL_OPT = typer.Option(False, "--all", help="Every harness found on this machine (install) or that has the skill (uninstall).")
PROJECT_OPT = typer.Option(False, "--project", help="The current folder's project skills folder instead of the global one.")


def pick_harnesses(names: Optional[list[str]], all_: bool, candidates: list, default) -> list:
    """Harnesses named on the command line, all candidates with --all, or the ones the user picks when asked."""
    if names:
        try:
            return list(dict.fromkeys(skills.resolve(n) for n in names))
        except ValueError as e:
            raise typer.BadParameter(str(e)) from None
    if all_:
        return candidates
    if not sys.stdin.isatty():
        raise typer.BadParameter(f"name the harness(es) ({', '.join(skills.HARNESSES)}) or pass --all")
    return [h for h in candidates if typer.confirm(f"{h.label}?", default=default(h))]


@skill_app.command("list")
def skill_list(project: bool = PROJECT_OPT):
    """Show each harness, whether it is on this machine, and the state of its webpilot skill."""
    home, root = Path.home(), Path.cwd() if project else None
    out([{"harness": h.name, "label": h.label, "detected": skills.detected(h, home),
          "path": str(skills.skill_file(h, home, root)), "state": skills.state(h, home, root)}
         for h in skills.HARNESSES.values()])


@skill_app.command("install")
def skill_install(harness: Optional[list[str]] = HARNESS_ARG, all_: bool = ALL_OPT, project: bool = PROJECT_OPT,
                  force: bool = typer.Option(False, "--force", help="Replace a webpilot skill not written by this command.")):
    """Install (or update) the webpilot skill. No harness given: asks for each one."""
    home, root = Path.home(), Path.cwd() if project else None
    everything = list(skills.HARNESSES.values())
    chosen = pick_harnesses(harness, all_, [h for h in everything if skills.detected(h, home)] if all_ else everything,
                            lambda h: skills.detected(h, home))
    done, skipped = [], []
    for h in chosen:
        try:
            done.append({"harness": h.name, "path": str(skills.install(h, home, root, force))})
        except FileExistsError as e:
            skipped.append({"harness": h.name, "reason": str(e)})
    out({"installed": done, "skipped": skipped,
         "note": "Start a new session in each agent to load the skill (Claude Code: also /webpilot)."})
    if skipped:
        raise typer.Exit(1)


@skill_app.command("uninstall")
def skill_uninstall(harness: Optional[list[str]] = HARNESS_ARG, all_: bool = ALL_OPT, project: bool = PROJECT_OPT,
                    force: bool = typer.Option(False, "--force", help="Also remove a webpilot skill not written by this command.")):
    """Remove the webpilot skill. No harness given: asks for each one that has it."""
    home, root = Path.home(), Path.cwd() if project else None
    present = [h for h in skills.HARNESSES.values() if skills.state(h, home, root) != "absent"]
    removed, skipped = [], []
    for h in pick_harnesses(harness, all_, present, lambda h: True):
        st = skills.state(h, home, root)
        if st == "foreign" and not force:
            skipped.append({"harness": h.name, "reason": f"{skills.skill_file(h, home, root)} was not written by "
                                                         "webpilot; pass --force to remove it"})
        elif path := skills.uninstall(h, home, root, force):
            removed.append({"harness": h.name, "path": str(path)})
        else:
            skipped.append({"harness": h.name, "reason": "not installed"})
    out({"removed": removed, "skipped": skipped})


# ------------------------------------------------------------------ temp browser

@temp_app.command("start")
def temp_start(headless: bool = typer.Option(False, "--headless")):
    """Start a fresh temporary browser and wait for its extension to connect."""
    temp_browser.start(headless)
    conn = Connection(config.load())
    st = conn.request("daemon.status")
    deadline = time.monotonic() + 60
    while "temp" not in st["extensions"] and time.monotonic() < deadline:
        time.sleep(0.5)
        st = conn.request("daemon.status")
    if "temp" not in st["extensions"]:
        raise WebPilotError("temporary browser started but its extension did not connect")
    out({"started": True, "headless": headless})


@temp_app.command("stop")
def temp_stop():
    """Close the temporary browser and delete its profile."""
    out({"stopped": temp_browser.stop()})


# ------------------------------------------------------------------ reflection

@app.command("reflect-data")
def reflect_data(
    session: Optional[list[str]] = typer.Option(None, "--session", help="Session name(s); default: today."),
    days: int = typer.Option(0, "--days", help="Include the previous N days too."),
    as_json: bool = typer.Option(False, "--json"),
):
    """Summarise logged browsing (domains, raw reads, parser use, errors) with optimisation suggestions."""
    names = list(session or [])
    if not names:
        names = [(date.today() - timedelta(days=i)).isoformat() for i in range(days, -1, -1)]
        names = [n for n in names if n in session_log.available()] or [session_log.session_name()]
    report = reflect.analyze(session_log.read(names))
    out(report) if as_json else print(reflect.to_markdown(report, names))


@app.command("log")
def log_(n: int = typer.Option(20, "-n")):
    """Show the last N logged actions of the current session."""
    for e in session_log.read([session_log.session_name()])[-n:]:
        print(json.dumps(e, ensure_ascii=False))


def run() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    try:
        app()
    except WebPilotError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    run()
