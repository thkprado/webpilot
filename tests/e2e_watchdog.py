"""Stops an end-to-end run that gets out of hand, without anyone having to type a command.

The run is aborted (temporary browsers and every process started by the run killed, exit code 3) when:
- more python processes descend from the run than its workers need (a worker that starts workers of its own
  once filled a machine: keyboard and network stopped responding before anything else ran out), or
- one test has been running for more than WEBPILOT_E2E_TEST_LIMIT seconds (default 90; includes its fixtures,
  so the first test also pays the browser start), or
- the whole run has taken more than WEBPILOT_E2E_RUN_LIMIT seconds (default 300), or
- free memory falls below WEBPILOT_E2E_MIN_FREE (fraction of physical memory and of the commit limit,
  default 0.15).

It is a thread in the pytest process that reports results (the controller, with xdist), which sees every
test start and finish. The reason is printed and written to <basetemp>/watchdog.txt.
"""

from __future__ import annotations

import ctypes
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

POLL = 0.5


def _env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def free_memory() -> tuple[float, float]:
    """(free physical memory, free commit) as fractions of their totals; (1, 1) when unknown."""
    if sys.platform == "win32":
        class Status(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
                (n, ctypes.c_ulonglong) for n in ("phys", "phys_free", "commit", "commit_free", "virt", "virt_free", "ext")
            ]

        s = Status(length=ctypes.sizeof(Status))
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s)):
            return 1.0, 1.0
        return s.phys_free / s.phys, s.commit_free / s.commit
    try:
        info = {k: int(v.split()[0]) for k, v in
                (line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())}
        free = info["MemAvailable"] / info["MemTotal"]
        return free, free
    except (OSError, KeyError, ValueError):
        return 1.0, 1.0


def processes() -> list[tuple[int, int, str]]:
    """(pid, parent pid, executable name) of every process; [] when unknown."""
    out = []
    if sys.platform == "win32":
        from ctypes import wintypes

        class Entry(ctypes.Structure):
            _fields_ = [("size", wintypes.DWORD), ("usage", wintypes.DWORD), ("pid", wintypes.DWORD),
                        ("heap", ctypes.c_size_t), ("module", wintypes.DWORD), ("threads", wintypes.DWORD),
                        ("ppid", wintypes.DWORD), ("priority", ctypes.c_long), ("flags", wintypes.DWORD),
                        ("exe", ctypes.c_wchar * 260)]

        k32 = ctypes.windll.kernel32
        k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        snap = k32.CreateToolhelp32Snapshot(2, 0)  # TH32CS_SNAPPROCESS
        if snap in (None, wintypes.HANDLE(-1).value):
            return out
        try:
            e = Entry(size=ctypes.sizeof(Entry))
            ok = k32.Process32FirstW(wintypes.HANDLE(snap), ctypes.byref(e))
            while ok:
                out.append((e.pid, e.ppid, e.exe.lower()))
                ok = k32.Process32NextW(wintypes.HANDLE(snap), ctypes.byref(e))
        finally:
            k32.CloseHandle(wintypes.HANDLE(snap))
        return out
    for stat in Path("/proc").glob("[0-9]*/stat"):
        try:
            text = stat.read_text()
            name = text[text.index("(") + 1:text.rindex(")")]
            out.append((int(stat.parent.name), int(text.rsplit(")", 1)[1].split()[1]), name.lower()))
        except (OSError, ValueError, IndexError):
            pass
    return out


def descendants(root: int) -> list[tuple[int, str]]:
    """(pid, name) of the processes started, directly or not, by `root`."""
    children: dict[int, list[tuple[int, str]]] = {}
    for pid, ppid, name in processes():
        if pid != ppid:
            children.setdefault(ppid, []).append((pid, name))
    out, todo, seen = [], [root], {root}
    while todo:
        for pid, name in children.get(todo.pop(), []):
            if pid not in seen:  # pids are reused: never loop
                seen.add(pid)
                out.append((pid, name))
                todo.append(pid)
    return out


def _kill_tree(pid: int) -> None:
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    else:
        for kill in (os.killpg, os.kill):  # temporary browsers lead their own session
            try:
                kill(pid, signal.SIGKILL)
                return
            except OSError:
                pass


class Watchdog:
    def __init__(self, basetemp: Path, max_pythons: int):
        self.basetemp = basetemp
        self.max_pythons = max_pythons
        self.test_limit = _env("WEBPILOT_E2E_TEST_LIMIT", 90)
        self.run_limit = _env("WEBPILOT_E2E_RUN_LIMIT", 300)
        self.min_free = _env("WEBPILOT_E2E_MIN_FREE", 0.15)
        self.started = time.monotonic()
        self.running: dict[str, float] = {}
        self.lock = threading.Lock()
        self.stopped = threading.Event()
        # Not a daemon: once the workers are killed pytest ends the session, and Python must wait for the
        # cleanup below instead of dropping this thread. pytest_unconfigure ends it on a normal run.
        self.thread = threading.Thread(target=self._loop, name="e2e-watchdog")

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stopped.set()

    # pytest hooks (registered as a plugin); with xdist the controller gets them for every worker's tests.

    def pytest_runtest_logstart(self, nodeid: str, location) -> None:
        with self.lock:
            self.running[nodeid] = time.monotonic()

    def pytest_runtest_logfinish(self, nodeid: str, location) -> None:
        with self.lock:
            self.running.pop(nodeid, None)

    def pytest_unconfigure(self, config) -> None:
        self.stop()

    def problem(self) -> str | None:
        pythons = sum(name.startswith("python") for _, name in descendants(os.getpid()))
        if pythons > self.max_pythons:
            return f"{pythons} python processes descend from this run, more than the {self.max_pythons} expected"
        now = time.monotonic()
        if now - self.started > self.run_limit:
            return f"the run took more than {self.run_limit:.0f} s (WEBPILOT_E2E_RUN_LIMIT)"
        with self.lock:
            for nodeid, start in self.running.items():
                if now - start > self.test_limit:
                    return f"{nodeid} ran for more than {self.test_limit:.0f} s (WEBPILOT_E2E_TEST_LIMIT)"
        phys, commit = free_memory()
        if min(phys, commit) < self.min_free:
            return (f"free memory fell to {phys:.0%} of RAM and {commit:.0%} of the commit limit, "
                    f"below {self.min_free:.0%} (WEBPILOT_E2E_MIN_FREE)")
        return None

    def _loop(self) -> None:
        while not self.stopped.wait(POLL):
            try:
                reason = self.problem()
            except Exception as e:  # noqa: BLE001 - a broken check must stop the run, not the watchdog
                reason = f"the watchdog's checks failed: {e!r}"
            if reason:
                self.abort(reason)
                return

    def abort(self, reason: str) -> None:
        msg = f"\n\nE2E WATCHDOG: aborting the run: {reason}. Killing the temporary browsers and pytest workers.\n"
        try:
            sys.__stderr__.write(msg)
            sys.__stderr__.flush()
            (self.basetemp / "watchdog.txt").write_text(msg.strip() + "\n", "utf-8")
        except OSError:
            pass
        profiles = []
        for state in self.basetemp.rglob("temp.json"):  # every worker's browser, and test_blocked.py's
            try:
                data = json.loads(state.read_text("utf-8"))
                _kill_tree(int(data["pid"]))
                profiles.append(Path(data["profile"]))
            except (OSError, ValueError, KeyError, TypeError):
                pass
        for pid, _ in reversed(descendants(os.getpid())):  # deepest first, so none is left without a parent
            try:
                os.kill(pid, signal.SIGKILL if sys.platform != "win32" else signal.SIGTERM)
            except OSError:
                pass
        profiles = [p for p in profiles if p.name.startswith("webpilot-temp-")]  # only what temp_browser made
        for _ in range(10):  # Chromium releases its profile files a moment after exiting
            for profile in profiles:
                shutil.rmtree(profile, ignore_errors=True)
            if not any(p.exists() for p in profiles):
                break
            time.sleep(0.5)
        sys.__stderr__.write(f"E2E WATCHDOG: aborted the run: {reason}. See {self.basetemp / 'watchdog.txt'}\n")
        sys.__stderr__.flush()
        os._exit(3)
