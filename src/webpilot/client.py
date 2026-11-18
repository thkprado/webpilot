"""Synchronous Python API. Every CLI command is a thin wrapper around these methods.

    from webpilot import Browser
    with Browser() as b:                 # real browser; Browser("temp") for the temporary one,
                                         # Browser(profile="work") to pick a browser profile
        b.goto("https://example.com")
        print(b.snapshot()["text"])
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import socket
import subprocess
import sys
import time
import uuid
import warnings
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from websockets.exceptions import ConnectionClosed, InvalidHandshake
from websockets.sync.client import ClientConnection, connect

from . import agent as agents
from . import config, registry, session_log, temp_browser

# How long to wait for the extension to (re)connect: the MV3 service worker may be asleep
# and is woken by a 30s alarm; a freshly started temporary browser needs a few seconds.
EXTENSION_WAIT = {"real": 40.0, "temp": 60.0}


class WebPilotError(RuntimeError):
    pass


class WebPilotWarning(UserWarning):
    """Something to know about a command that succeeded, such as a confirm that eval dismissed."""


def daemon_command() -> list[str]:
    """`-P` keeps the caller's folder off sys.path, so a json.py or types.py there is not imported."""
    return [sys.executable, "-P", "-m", "webpilot", "serve"]


def start_daemon() -> None:
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    with open(config.home() / "daemon.log", "ab") as log:  # the daemon keeps its own copy of the handle
        subprocess.Popen(
            daemon_command(),
            cwd=config.home(),  # nor hold the caller's folder open (Windows cannot delete it)
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=flags,
            start_new_session=sys.platform != "win32",
            close_fds=True,
        )


def _request_body(headers: dict[str, str] | None, data: str | None, json_value: Any) -> tuple[dict, str | None]:
    """Headers and body for Browser.fetch: `json_value` is serialized and labelled application/json."""
    headers = dict(headers or {})
    if json_value is None:
        return headers, data
    if data is not None:
        raise WebPilotError("give data or json, not both")
    if not any(k.lower() == "content-type" for k in headers):
        headers["Content-Type"] = "application/json"
    return headers, json.dumps(json_value)


def _response_body(res: dict, raw: bool) -> dict:
    """Browser.fetch result: binary bodies become bytes, JSON bodies are parsed unless raw."""
    if "bodyBase64" in res:
        res["body"] = base64.b64decode(res.pop("bodyBase64"))
    elif not raw and "json" in (res.get("headers") or {}).get("content-type", "") and res.get("body"):
        try:
            res["body"] = json.loads(res["body"])
        except ValueError:
            pass  # labelled JSON but is not: keep the text
    return res


# Largest total upload: the files travel base64-encoded inside one JSON message, then as a script argument.
# upload --trusted sends paths instead (the browser reads the files), with no limit.
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def _upload_files(paths: tuple[str | Path, ...], trusted: bool = False) -> list[dict]:
    """The files for Browser.upload: read and base64-encoded, or with trusted their absolute paths and sizes;
    fails before any request when one is missing or, without trusted, they are too large together."""
    if not paths:
        raise WebPilotError("give at least one file to upload")
    files = [Path(p).expanduser() for p in paths]
    for f in files:
        if not f.is_file():
            raise WebPilotError(f"file not found: {f}")
    if trusted:
        return [{"name": f.name, "path": str(f.resolve()), "bytes": f.stat().st_size} for f in files]
    total = sum(f.stat().st_size for f in files)
    if total > MAX_UPLOAD_BYTES:
        raise WebPilotError(f"files too large to upload: {total / 2**20:.1f} MB, the limit is "
                            f"{MAX_UPLOAD_BYTES / 2**20:.0f} MB; with --trusted (trusted=True) the browser reads "
                            f"them from disk, without a limit")
    return [{"name": f.name, "type": mimetypes.guess_type(f.name)[0] or "application/octet-stream",
             "lastModified": round(f.stat().st_mtime * 1000), "data": base64.b64encode(f.read_bytes()).decode("ascii")}
            for f in files]


def _out_chars(value: Any) -> int:
    """Size of a command's output for the session log: text as is, other values as JSON."""
    if value is None:
        return 0
    if isinstance(value, (str, bytes)):
        return len(value)
    return len(json.dumps(value, ensure_ascii=False, default=str))


def _tcp(port: int) -> socket.socket:
    """A TCP connection to the daemon's port, for websockets' `connect(sock=...)`. The short timeout is how a
    stopped daemon is noticed: on Windows a refused connection to 127.0.0.1 takes 2 s to fail otherwise."""
    sock = socket.create_connection(("127.0.0.1", port), timeout=0.2)
    sock.settimeout(None)
    return sock


class Connection:
    """One WebSocket session with the daemon (started automatically if not running)."""

    def __init__(self, cfg: dict, autostart: bool = True):
        self.cfg = cfg
        self._stack = ExitStack()
        self.ws = self._open(autostart)

    def _open(self, autostart: bool) -> ClientConnection:
        uri = f"ws://127.0.0.1:{self.cfg['port']}"
        deadline = None
        while True:
            try:
                ws = self._stack.enter_context(connect(uri, sock=_tcp(self.cfg["port"]), max_size=None,
                                                       open_timeout=3, ping_interval=None))
                break
            except (OSError, InvalidHandshake, TimeoutError) as e:
                if not autostart:
                    raise WebPilotError(f"daemon not running on {uri} (`webpilot serve`)") from e
                if deadline is None:
                    start_daemon()
                    deadline = time.monotonic() + 15
                elif time.monotonic() > deadline:
                    raise WebPilotError(f"could not start daemon; see {config.home() / 'daemon.log'}") from e
                time.sleep(0.1)
        ws.send(json.dumps({"type": "hello", "role": "client", "token": self.cfg["token"]}))
        try:
            welcome = json.loads(ws.recv(timeout=5))
        except (ConnectionClosed, TimeoutError) as e:
            raise WebPilotError("daemon rejected the connection (token mismatch? restart it: `webpilot stop`)") from e
        if welcome.get("type") != "welcome":
            raise WebPilotError(f"unexpected daemon reply: {welcome}")
        return ws

    def request(self, cmd: str, args: dict | None = None, *, mode: str = "real", profile: str | None = None,
                timeout: float = 60, wait: float = 0, agent: str | None = None) -> Any:
        rid = uuid.uuid4().hex
        msg = {"id": rid, "cmd": cmd, "args": args or {}, "mode": mode, "profile": profile, "timeout": timeout,
               "wait": wait, "agent": agent}
        try:
            self.ws.send(json.dumps(msg))
            while True:
                reply = json.loads(self.ws.recv(timeout=timeout + wait + 10))
                if reply.get("id") == rid:
                    break
        except (ConnectionClosed, TimeoutError) as e:
            raise WebPilotError(f"lost connection to daemon during {cmd}") from e
        if not reply.get("ok"):
            raise WebPilotError(reply.get("error") or "unknown error")
        return reply.get("result")

    def close(self) -> None:
        self._stack.close()


class Browser:
    def __init__(self, mode: str | None = None, tab: int | None = None, *, profile: str | None = None,
                 agent: str | None = None, autostart: bool = True, log: bool = True):
        self.mode = mode or os.environ.get("WEBPILOT_MODE") or "real"
        if self.mode not in ("real", "temp"):
            raise WebPilotError(f"mode must be 'real' or 'temp', not {self.mode!r}")
        self.tab = tab
        self.autostart = autostart
        self.log = log
        self.cfg = config.load()
        # Which browser profile to drive when several have the extension; None = the only one connected.
        self.profile = profile or os.environ.get("WEBPILOT_PROFILE") or self.cfg.get("profile") or None
        if self.mode == "temp":
            self.profile = None
        # Whose current tab the commands without a tab id act on: each agent has its own (see agent.py).
        # None detects it; "" uses the browser's shared current tab.
        self.agent = agents.agent_key() if agent is None else (agent or None)
        self._conn: Connection | None = None
        self.last_dialogs: list[dict] = []  # answered during the last eval

    # ------------------------------------------------------------ plumbing

    @property
    def conn(self) -> Connection:
        if self._conn is None:
            self._conn = Connection(self.cfg, self.autostart)
            if self.mode == "temp" and self.autostart and "temp" not in self.status()["extensions"]:
                temp_browser.start(headless=os.environ.get("WEBPILOT_HEADLESS") == "1")
        return self._conn

    def status(self) -> dict:
        return self.conn.request("daemon.status")

    def call(self, cmd: str, *, _timeout: float = 60, _log: dict | None = None, **args) -> Any:
        args = {k: v for k, v in args.items() if v is not None}
        if self.tab is not None:
            args.setdefault("tabId", self.tab)
        start = time.perf_counter()
        result, error = None, None
        try:
            result = self.conn.request(cmd, args, mode=self.mode, profile=self.profile, timeout=_timeout,
                                       wait=EXTENSION_WAIT[self.mode], agent=self.agent)
            return result
        except WebPilotError as e:
            error = str(e)
            raise
        finally:
            if self.log:
                entry = {
                    "mode": self.mode,
                    "cmd": cmd,
                    "args": args,
                    "ok": error is None,
                    "ms": round((time.perf_counter() - start) * 1000),
                }
                if self.profile:
                    entry["profile"] = self.profile
                if error:
                    entry["error"] = error[:300]
                if cmd == "eval":
                    # result["value"] is whatever the page's code returned, not a command result: fields
                    # such as `url` or `body` in it are data. Only its size is logged.
                    if error is None and isinstance(result, dict):
                        value = result.get("value")
                        entry["out_chars"] = _out_chars(value)
                        if isinstance(value, str) and value.startswith("data:"):  # the type only, never the content
                            entry["data_url"] = value[5:105].split(",", 1)[0].split(";")[0] or "text/plain"
                        if result.get("dialogs"):  # the types only, as for actions
                            entry["dialogs"] = [d.get("type") for d in result["dialogs"]]
                elif isinstance(result, dict):
                    if result.get("url"):
                        entry["url"] = result["url"]
                    entry["out_chars"] = _out_chars(result.get("text") or result.get("html") or result.get("body")
                                                    or result.get("bodyBase64"))
                    if cmd == "fetch":
                        entry["status"] = result.get("status")
                    if result.get("found") is False or (result.get("waited") or {}).get("found") is False:
                        entry["wait_missed"] = True  # `wait`, or an action's --wait-text/--wait-for, timed out
                    if result.get("busy"):  # the page never went quiet after an action
                        entry["busy"] = result["busy"]
                    if result.get("dialogs"):  # the types only: messages may carry personal data
                        entry["dialogs"] = [d.get("type") for d in result["dialogs"]]
                    if result.get("frameUrl"):  # the action ran inside an iframe (domain only, like frames)
                        entry["frame_domain"] = session_log.domain(result["frameUrl"])
                    if result.get("frames"):  # domains only: frame URLs may carry session ids
                        entry["frames"] = [{"domain": session_log.domain(f.get("url")), "chars": f.get("chars") or len(f.get("html") or "")}
                                           for f in result["frames"]]
                entry.update(_log or {})
                self._record(**entry)

    def _record(self, **entry) -> None:
        if self.agent:  # tells interleaved runs of several agents apart in reflect-data
            entry["agent"] = self.agent
        session_log.record(**entry)

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> Browser:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ------------------------------------------------------------ tabs & navigation

    def tabs(self) -> list[dict]:
        return self.call("tabs.list")

    def new_tab(self, url: str | None = None) -> dict:
        return self.call("tab.new", url=url)

    def use_tab(self, tab_id: int) -> dict:
        self.tab = None
        return self.call("tab.use", tabId=tab_id)

    def close_tab(self, tab_id: int | None = None) -> dict:
        return self.call("tab.close", tabId=tab_id)

    def info(self) -> dict:
        return self.call("tab.info")

    def goto(self, url: str, new_tab: bool = False) -> dict:
        if "://" not in url and not url.startswith(("about:", "data:")):
            url = "https://" + url
        return self.call("goto", url=url, newTab=new_tab or None)

    def back(self) -> dict:
        return self.call("back")

    def forward(self) -> dict:
        return self.call("forward")

    def reload(self) -> dict:
        return self.call("reload")

    # ------------------------------------------------------------ reading

    def snapshot(self, selector: str | None = None, max_chars: int = 15000, interactive: bool = False) -> dict:
        return self.call("snapshot", selector=selector, maxChars=max_chars, interactive=interactive or None)

    def html(self, selector: str | None = None, frames: bool = False, _log: dict | None = None) -> dict:
        """outerHTML of the page or a selector; frames=True adds the iframes' documents as result["frames"]."""
        return self.call("html", _log=_log, selector=selector, frames=frames or None)

    def text(self, selector: str | None = None, max_chars: int = 50000) -> dict:
        return self.call("text", selector=selector, maxChars=max_chars)

    def screenshot(self, path: str | Path | None = None, full: bool = False, target: str | None = None) -> Path:
        """Saves a PNG of the viewport, the whole page (full=True) or one element (target, with 8 px around it,
        scrolled into view) and returns its path (default: ~/.webpilot/screenshots/<time>.png)."""
        result = self.call("screenshot", full=full or None, target=target)
        if path is None:
            shots = config.home() / "screenshots"
            shots.mkdir(exist_ok=True)
            path = shots / f"{time.strftime('%Y%m%d-%H%M%S')}.png"
        path = Path(path)
        path.write_bytes(base64.b64decode(result["data"]))
        return path.resolve()

    def eval(self, expression: str, timeout: float = 60, args: list | tuple | None = None,
             dialog: str | None = None, prompt_text: str | None = None, _log: dict | None = None) -> Any:
        """Evaluate JavaScript in the page; promises are awaited for up to `timeout` seconds.

        With `args`, `expression` must be a function, and it is called with those values:
        `eval("(text) => (document.querySelector('textarea').value = text)", args=[body])`.
        The values travel as JSON, separately from the code, so they need no escaping.

        alert/confirm/prompt opened meanwhile are answered as in actions (`dialog`, `prompt_text`) and kept in
        `self.last_dialogs`; a dismissed confirm or prompt also warns (WebPilotWarning) with the hint."""
        res = self._eval(expression, timeout, args, dialog, prompt_text, _log)
        if res.get("hint"):
            warnings.warn(res["hint"], WebPilotWarning, stacklevel=2)
        return res["value"]

    def _eval(self, expression: str, timeout: float, args: list | tuple | None, dialog: str | None,
              prompt_text: str | None, _log: dict | None) -> dict:
        """eval's whole result: {"value", "dialogs"?, "hint"?}."""
        if dialog not in (None, "accept", "dismiss"):
            raise WebPilotError(f"dialog must be 'accept' or 'dismiss', not {dialog!r}")
        res = self.call("eval", _timeout=timeout, _log=_log, expression=expression,
                        args=list(args) if args is not None else None, dialog=dialog, promptText=prompt_text)
        if not isinstance(res, dict) or "value" not in res:
            raise WebPilotError("the browser extension is older than this WebPilot: reload it on the browser's "
                                "extensions page")
        self.last_dialogs = res.get("dialogs") or []
        return res

    def fetch(self, url: str, method: str = "GET", headers: dict[str, str] | None = None, data: str | None = None,
              json: Any = None, timeout: float = 120, allow_write: bool = False, raw: bool = False,
              _log: dict | None = None) -> dict:
        """HTTP request from the current tab's page, with its cookies and session; relative URLs resolve
        against the tab. Returns {"status", "statusText", "url", "headers", "body"}: body is parsed JSON
        when the response is JSON (unless raw), text, or bytes for binary content. Methods other than
        GET/HEAD need allow_write=True (only after the user confirmed)."""
        headers, body = _request_body(headers, data, json)
        res = self.call("fetch", _timeout=timeout + 5, _log=_log, url=url, method=method.upper(), headers=headers or None,
                        body=body, timeoutMs=round(timeout * 1000), allowWrite=allow_write or None)
        return _response_body(res, raw)

    def requests(self, new: bool = False, all: bool = False, filter: str | None = None, max: int = 50) -> dict:
        """The fetch and XHR calls the current page made (all=True: images, scripts and the rest too), from the
        browser's Resource Timing: {"url", "requests": [{"url", "status", "ms", "bytes", "contentType", "n",
        "frame"}], "omitted", "hint"}, oldest first. new=True: only those after the last action or navigation;
        filter: a URL substring; max: the newest kept (the rest counted in "omitted"). The same URL repeated is
        one entry with its count `n`. No method, headers or bodies: `fetch` one URL to see its answer."""
        return self.call("requests", new=new or None, all=all or None, filter=filter, max=max)

    # ------------------------------------------------------------ interaction

    # Actions wait up to `timeout` seconds for their target, then for the page to settle (load + quiet DOM).
    # wait_text / wait_selector additionally wait (up to wait_timeout) for the next state; see result["waited"].
    # Dialogs the page opens meanwhile (alert, confirm, prompt) are answered at once and listed in
    # result["dialogs"]: dismissed by default; dialog="accept" accepts them (only for what the user agreed to),
    # and prompt_text is what an accepted prompt() gets (default: the prompt's own default value).

    def _act(self, cmd: str, timeout: float | None, wait_text: str | None, wait_selector: str | None,
             wait_timeout: float, dialog: str | None, prompt_text: str | None, _targets: int = 1, **args) -> dict:
        if dialog not in (None, "accept", "dismiss"):
            raise WebPilotError(f"dialog must be 'accept' or 'dismiss', not {dialog!r}")
        waiting = wait_text is not None or wait_selector is not None
        # Each target may be waited for, plus a few seconds to fill it (fill: a dropdown's options may load late).
        per_target = (timeout or 5) + (6 if cmd == "fill" else 0)
        return self.call(cmd, _timeout=60 + per_target * _targets + (wait_timeout if waiting else 0), timeout=timeout,
                         waitText=wait_text, waitSelector=wait_selector,
                         waitTimeout=wait_timeout if waiting else None, dialog=dialog, promptText=prompt_text, **args)

    def click(self, target: str, trusted: bool = False, *, timeout: float | None = None, wait_text: str | None = None,
              wait_selector: str | None = None, wait_timeout: float = 10, dialog: str | None = None,
              prompt_text: str | None = None) -> dict:
        """target: snapshot ref (e12), CSS selector, or text=Label (text=Next|Próximo tries each label)."""
        return self._act("click", timeout, wait_text, wait_selector, wait_timeout, dialog, prompt_text,
                         target=target, trusted=trusted or None)

    def type(self, target: str, text: str, *, clear: bool = True, submit: bool = False, trusted: bool = False,
             timeout: float | None = None, wait_text: str | None = None, wait_selector: str | None = None,
             wait_timeout: float = 10, dialog: str | None = None, prompt_text: str | None = None) -> dict:
        return self._act("type", timeout, wait_text, wait_selector, wait_timeout, dialog, prompt_text,
                         target=target, text=text, clear=clear, submit=submit or None, trusted=trusted or None)

    def select(self, target: str, text: str, *, timeout: float | None = None, wait_text: str | None = None,
               wait_selector: str | None = None, wait_timeout: float = 10, dialog: str | None = None,
               prompt_text: str | None = None) -> dict:
        """Chooses the option matching `text` in a custom dropdown (role=combobox, such as react-select) or a
        <select>, in one command. target: the combobox or an element around it. The result has "option"
        (its text) and "value" (what the field shows); not choosing raises WebPilotError."""
        return self._act("select", timeout, wait_text, wait_selector, wait_timeout, dialog, prompt_text,
                         target=target, text=text)

    def fill(self, fields: dict[str, str | bool], *, submit: bool = False, timeout: float | None = None,
             wait_text: str | None = None, wait_selector: str | None = None, wait_timeout: float = 10,
             dialog: str | None = None, prompt_text: str | None = None) -> dict:
        """Fills several fields in one command, in order: {target: value}. Text fields are typed into (replacing
        their content), a <select> or combobox gets the option matching the value (as `select`), a checkbox, radio or
        switch is checked with True (or "true") and unchecked with False, clicked only when its state differs.
        Each target is waited for, so a field that appears after an earlier one is filled works. Stops at the
        first field that fails (WebPilotError naming it and those filled before it). The result has "filled"
        ([{target, field, value or checked}]); submit=True then submits the last field's form ("submitted")."""
        if not fields:
            raise WebPilotError("no fields to fill")
        pairs = [{"target": t, "value": ("true" if v else "false") if isinstance(v, bool) else str(v)}
                 for t, v in fields.items()]
        return self._act("fill", timeout, wait_text, wait_selector, wait_timeout, dialog, prompt_text,
                         _targets=len(pairs), fields=pairs, submit=submit or None)

    def press(self, key: str, *, wait_text: str | None = None, wait_selector: str | None = None,
              wait_timeout: float = 10, dialog: str | None = None, prompt_text: str | None = None) -> dict:
        """Key name or combo: Enter, Tab, Escape, ArrowDown, a, Control+a..."""
        return self._act("press", None, wait_text, wait_selector, wait_timeout, dialog, prompt_text, key=key)

    def submit(self, target: str | None = None, *, timeout: float | None = None, wait_text: str | None = None,
               wait_selector: str | None = None, wait_timeout: float = 10, dialog: str | None = None,
               prompt_text: str | None = None) -> dict:
        """Submits the form containing target (or the focused / first visible form), running the page's handlers."""
        return self._act("submit", timeout, wait_text, wait_selector, wait_timeout, dialog, prompt_text, target=target)

    def upload(self, target: str, *paths: str | Path, drop: bool = False, trusted: bool = False,
               timeout: float | None = None, wait_text: str | None = None, wait_selector: str | None = None,
               wait_timeout: float = 10, dialog: str | None = None, prompt_text: str | None = None) -> dict:
        """Gives local files to a file input, as choosing them in the file picker would. target: the
        input[type=file], its label, the button that opens it or an element around it (the input may be hidden);
        a button whose page makes the input when clicked is clicked (the result then has "clicked"). With
        drop=True, the drop zone the files are dropped on instead. Up to 50 MB in all; trusted=True has the
        browser read the files from disk through the debugger, without a limit (not with drop). The result has
        "files" ({name, bytes})."""
        if trusted and drop:
            raise WebPilotError("upload --trusted cannot drop files: drop them without --trusted")
        files = _upload_files(paths, trusted)
        try:
            return self._act("upload", timeout, wait_text, wait_selector, wait_timeout, dialog, prompt_text,
                             target=target, files=files, drop=drop or None, trusted=trusted or None)
        except WebPilotError as e:
            if trusted and "correctly encoded" in str(e):  # an extension from before upload --trusted
                raise WebPilotError("the browser's WebPilot extension is older than this client and cannot "
                                    "upload --trusted: reload it on the browser's extensions page") from e
            raise

    def hover(self, target: str, trusted: bool = False, *, timeout: float | None = None, wait_text: str | None = None,
              wait_selector: str | None = None, wait_timeout: float = 10, dialog: str | None = None,
              prompt_text: str | None = None) -> dict:
        """Moves the pointer onto target, for menus and tooltips that open on hover. Without trusted, the mouse
        events are fired by script (menus opened by JavaScript); trusted=True moves the real pointer through the
        debugger, which menus opened by CSS :hover need (they change no DOM, so read the page afterwards)."""
        return self._act("hover", timeout, wait_text, wait_selector, wait_timeout, dialog, prompt_text,
                         target=target, trusted=trusted or None)

    def scroll(self, to: str = "down", amount: int | None = None) -> dict:
        return self.call("scroll", to=to, amount=amount)

    def wait(self, selector: str | None = None, text: str | None = None, timeout: float = 10, gone: bool = False) -> dict:
        """Waits until a CSS selector is visible and/or the text appears on the page (gone=True: disappears)."""
        return self.call("wait", _timeout=timeout + 10, selector=selector, text=text, timeout=timeout, gone=gone or None)

    def captcha(self) -> dict:
        return self.call("captcha", _timeout=30)

    # ------------------------------------------------------------ parsers & search

    def extract(self, url: str | None = None, max_chars: int = 15000) -> dict:
        """Structured data via a site parser if one matches, else a snapshot plus a hint."""
        if url:
            self.goto(url)
        page = self.html(frames=True, _log={"purpose": "extract"})
        parser = registry.find(page["url"])
        top = page
        if parser is None:  # embedded content (quiz, widget) may have a parser of its own
            for frame in page.get("frames") or []:
                if (parser := registry.find(frame["url"])) is not None:
                    page = frame
                    break
        if parser is None:
            snap = self.snapshot(max_chars=max_chars)
            self._record(cmd="extract", args={}, ok=True, url=page["url"], parser=None, out_chars=len(snap["text"]), ms=0)
            return {
                "url": page["url"],
                "title": page["title"],
                "parser": None,
                "hint": "No parser for this site. If you will read it again, write one (see docs/parsers.md in the WebPilot folder).",
                "snapshot": snap["text"],
            }
        start = time.perf_counter()
        try:
            data = parser.parse(page["html"], page["url"])
        except Exception as e:
            self._record(cmd="extract", args={}, ok=False, url=page["url"], parser=parser.name,
                         error=f"{type(e).__name__}: {e}"[:300], ms=round((time.perf_counter() - start) * 1000))
            raise WebPilotError(f"parser {parser.name} failed: {type(e).__name__}: {e}") from e
        size = len(json.dumps(data, ensure_ascii=False))
        self._record(cmd="extract", args={}, ok=True, url=page["url"], parser=parser.name, out_chars=size,
                     empty=not data, ms=round((time.perf_counter() - start) * 1000))
        result = {"url": page["url"], "title": page["title"], "parser": parser.name, "data": data}
        if page is not top:
            result.update(frame=page["frame"], page_url=top["url"])
        return result

    def search(self, query: str, n: int = 10, engine: str = "google", lang: str | None = None, new_tab: bool = False) -> dict:
        from .search import search

        return search(self, query, n=n, engine=engine, lang=lang, new_tab=new_tab)
