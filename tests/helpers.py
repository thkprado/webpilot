"""Shared by the unit tests and the end-to-end tests: a free port, a daemon running in a thread, snapshot refs."""

from __future__ import annotations

import asyncio
import json
import os
import re
import socket
import struct
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from webpilot.client import Browser
from webpilot.server import Daemon


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextmanager
def running_daemon(token: str, port: int) -> Iterator[Daemon]:
    """A daemon on 127.0.0.1:port in a background thread, listening when this yields."""
    d = Daemon(token, port)
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_until_complete, args=(d.run(),), daemon=True)
    thread.start()
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.1).close()
            break
        except OSError:
            threading.Event().wait(0.05)
    try:
        yield d
    finally:
        loop.call_soon_threadsafe(d.stop_event.set)
        thread.join(5)


def ref(snapshot_text: str, kind: str, name: str) -> str:
    """The ref (e12, or f3e12 inside an iframe) of `[ref kind "name" ...]` in a snapshot; fails the test if absent."""
    m = re.search(rf"\[((?:f\d+)?e\d+) {re.escape(kind)} \"{re.escape(name)}\"", snapshot_text)
    assert m, f"no {kind} {name!r} in snapshot:\n{snapshot_text}"
    return m.group(1)


# window.__log of the e2e test pages, once it has at least n entries (events posted by iframes arrive a moment later).
PAGE_LOG = """(n) => new Promise((done) => {
  const poll = () => (window.__log.length >= n ? done(window.__log) : setTimeout(poll, 20));
  poll();
})"""


def page_log(b, n: int = 0) -> list:
    """What the test page recorded in window.__log, waiting (up to 5 s) until it has n entries."""
    return b.eval(PAGE_LOG, args=[n], timeout=5)


# A small red canvas exported as a PNG data URL, as pages export charts.
CANVAS = """(() => {
  const c = Object.assign(document.createElement("canvas"), { width: 30, height: 20 });
  const g = c.getContext("2d");
  g.fillStyle = "red";
  g.fillRect(0, 0, 30, 20);
  return c.toDataURL();
})()"""


def png_size(data: bytes) -> tuple[int, int]:
    """(width, height) of a PNG; fails the test if `data` is not one."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n", data[:8]
    return struct.unpack(">II", data[16:24])


@contextmanager
def own_browser(home: Path, cfg: dict) -> Iterator[Browser]:
    """A Browser on a temporary browser of its own (config dir `home` holding `cfg`, its own daemon and port),
    for tests that need another config than the shared e2e browser."""
    from webpilot import config, temp_browser

    (home / "config.json").write_text(json.dumps(cfg), "utf-8")
    port = free_port()
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("WEBPILOT_DIR", str(home))
        mp.setenv("WEBPILOT_PORT", str(port))
        token = config.load()["token"]
        with running_daemon(token, port):
            try:
                temp_browser.start(headless=os.environ.get("WEBPILOT_E2E_HEADED") != "1")
                with Browser("temp", autostart=False) as b:
                    deadline = time.monotonic() + 60
                    while "temp" not in b.status()["extensions"]:
                        assert time.monotonic() < deadline, f"browser with {cfg} did not connect; see {home}"
                        time.sleep(0.2)
                    yield b
            finally:
                temp_browser.stop()
