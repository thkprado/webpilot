"""End-to-end fixtures: a thread daemon, a headless temporary browser with the built extension, local pages.

Run with `uv run pytest -m e2e` after `npm run build` in extension/. WEBPILOT_E2E_HEADED=1 shows the browser.
The daemon listens on a free port with the token of a throwaway config, so the extension of the user's own
browser (default port, other token) never connects to it, and every test uses the temporary browser.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sys
import threading
import time
from dataclasses import dataclass
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from helpers import free_port, running_daemon

from webpilot import config, temp_browser
from webpilot.client import Browser, WebPilotError

PAGES = Path(__file__).parent / "pages"
COMBOBOX = Path(__file__).parents[1] / "pages" / "combobox"  # served under /combobox/ (needs its npm build)
CONNECT_TIMEOUT = 60  # first run may install Playwright's Chromium


@dataclass
class Env:
    home: Path
    port: int
    token: str


@dataclass
class Site:
    base: str  # http://127.0.0.1:PORT
    other: str  # same pages from another port: another origin, for cross-origin frames

    def url(self, path: str) -> str:
        return f"{self.base}/{path.lstrip('/')}"

    def other_url(self, path: str) -> str:
        return f"{self.other}/{path.lstrip('/')}"


@dataclass
class Temp:
    initial_tabs: set[int]  # tabs open at start; every other tab is closed after each test


class Handler(SimpleHTTPRequestHandler):
    """Static files from tests/e2e/pages (and tests/pages/combobox under /combobox/) plus a few endpoints
    for fetch, cookies and redirects."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PAGES), **kwargs)

    def log_message(self, *args) -> None:
        pass

    def translate_path(self, path: str) -> str:
        if path.startswith("/combobox/"):
            self.directory = str(COMBOBOX)
            path = path[len("/combobox"):]
        return super().translate_path(path)

    def _json(self, data, status: int = 200, headers: dict[str, str] | None = None) -> None:
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")  # readable from the other origin (redirect tests)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _echo(self) -> None:
        """/api/echo: the request as JSON (method, path, headers, body, cookies)."""
        size = int(self.headers.get("Content-Length") or 0)
        cookies = SimpleCookie(self.headers.get("Cookie", ""))
        self._json({
            "method": self.command,
            "path": self.path,
            "headers": dict(self.headers),
            "body": self.rfile.read(size).decode("utf-8", "replace"),
            "cookies": {k: m.value for k, m in cookies.items()},
        })

    def do_GET(self) -> None:
        url = urlsplit(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        if url.path == "/api/echo":
            self._echo()
        elif url.path == "/api/slow":  # /api/slow?ms=2000
            time.sleep(int(q.get("ms", "1000")) / 1000)
            self._json({"slept_ms": int(q.get("ms", "1000"))})
        elif url.path == "/set-cookie":  # /set-cookie?name=sid&value=abc
            name, value = q.get("name", "sid"), q.get("value", "1")
            self._json({"set": {name: value}}, headers={"Set-Cookie": f"{name}={value}; Path=/"})
        elif url.path == "/redirect":  # /redirect?to=URL
            self.send_response(302)
            self.send_header("Location", q.get("to", "/"))
            self.send_header("Content-Length", "0")
            self.end_headers()
        else:
            super().do_GET()

    def _write(self) -> None:
        if urlsplit(self.path).path == "/api/echo":
            self._echo()
        else:
            self._json({"error": "only /api/echo accepts this method"}, status=405)

    do_POST = do_PUT = do_PATCH = do_DELETE = _write


@pytest.fixture(scope="session")
def e2e_env(tmp_path_factory) -> Env:
    """Isolated config dir (token, temp-browser state, session log) and a daemon on a free port."""
    dist = config.extension_dist()
    if not (dist / "manifest.json").exists():
        pytest.skip(f"extension not built: {dist} (run `npm install && npm run build` in extension/)")
    home = tmp_path_factory.mktemp("webpilot")
    port = free_port()
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("WEBPILOT_DIR", str(home))
        mp.setenv("WEBPILOT_PORT", str(port))
        mp.setenv("WEBPILOT_SESSION", "e2e")
        for name in ("WEBPILOT_MODE", "WEBPILOT_PROFILE", "WEBPILOT_HEADLESS"):
            mp.delenv(name, raising=False)
        token = config.load()["token"]
        logger = logging.getLogger("webpilot.daemon")
        handler = logging.FileHandler(home / "daemon.log", encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        level = logger.level
        logger.setLevel(logging.INFO)
        try:
            with running_daemon(token, port):
                yield Env(home, port, token)
        finally:
            logger.removeHandler(handler)
            logger.setLevel(level)
            handler.close()


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address) -> None:
        if not isinstance(sys.exc_info()[1], ConnectionError):  # the browser dropped a connection: not news
            super().handle_error(request, client_address)


def _serve() -> ThreadingHTTPServer:
    server = Server(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.fixture(scope="session")
def site() -> Site:
    """tests/e2e/pages on two local ports (two origins)."""
    main, other = _serve(), _serve()
    try:
        yield Site(f"http://127.0.0.1:{main.server_port}", f"http://127.0.0.1:{other.server_port}")
    finally:
        for server in (main, other):
            server.shutdown()
            server.server_close()


@pytest.fixture(scope="session")
def temp(e2e_env) -> Temp:
    """The temporary browser (headless unless WEBPILOT_E2E_HEADED=1), started once for the whole run."""
    try:
        temp_browser.start(headless=os.environ.get("WEBPILOT_E2E_HEADED") != "1")
        with Browser("temp", autostart=False, log=False) as b:
            deadline = time.monotonic() + CONNECT_TIMEOUT
            while "temp" not in b.status()["extensions"]:
                if time.monotonic() > deadline:
                    raise RuntimeError(f"temporary browser did not connect in {CONNECT_TIMEOUT}s; "
                                       f"see {e2e_env.home / 'daemon.log'}")
                time.sleep(0.2)
            initial = {t["id"] for t in b.tabs()}
        yield Temp(initial)
    finally:
        temp_browser.stop()


@pytest.fixture
def b(temp, tmp_path) -> Browser:
    """The temporary browser on a fresh tab; tabs opened by the test are closed afterwards."""
    browser = Browser("temp", autostart=False)
    browser.new_tab()
    yield browser
    try:
        for t in browser.tabs():
            if t["id"] not in temp.initial_tabs:
                browser.close_tab(t["id"])
    except WebPilotError:
        pass
    browser.close()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """On a failure: a screenshot of the test's tab and copies of the daemon and session logs."""
    outcome = yield
    rep = outcome.get_result()
    browser, out, env = (item.funcargs.get(k) for k in ("b", "tmp_path", "e2e_env"))
    if rep.when != "call" or not rep.failed or out is None or env is None:
        return
    saved = []
    if isinstance(browser, Browser):
        try:
            saved.append(browser.screenshot(out / "failure.png"))
        except Exception as e:  # noqa: BLE001 - the browser may be what failed
            saved.append(f"(no screenshot: {e})")
    for src in [env.home / "daemon.log", *sorted((env.home / "sessions").glob("*.jsonl"))]:
        if src.exists():
            saved.append(shutil.copy(src, out / src.name))
    rep.sections.append(("e2e failure artifacts", "\n".join(str(p) for p in saved)))
