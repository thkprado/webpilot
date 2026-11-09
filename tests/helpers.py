"""Shared by the unit tests and the end-to-end tests: a free port, a daemon running in a thread, snapshot refs."""

from __future__ import annotations

import asyncio
import re
import socket
import struct
import threading
from collections.abc import Iterator
from contextlib import contextmanager

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
