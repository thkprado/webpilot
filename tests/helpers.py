"""Shared by the unit tests and the end-to-end tests: a free port and a daemon running in a thread."""

from __future__ import annotations

import asyncio
import socket
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
