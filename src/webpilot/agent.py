"""Which agent is calling: a key that gives each agent its own current tab in the browser.

Two agents driving one browser would otherwise share one current tab, and one agent's `tab new` would move the
other's commands. The key, first match wins:

1. `Browser(agent=...)` (handled by the caller);
2. `WEBPILOT_SESSION`, the name that already groups a run in the session log;
3. a session id the agent's host exports to its commands (GitHub Copilot CLI, Claude Code), hashed;
4. the process tree: the first ancestor that is not a shell or launcher is the agent (`claude`, `copilot`'s
   node, ...), keyed by name, pid and start time. When that ancestor is a terminal (Windows Terminal, VS Code's
   terminal, tmux, sshd, ...), the key is the shell just below it: each terminal is then one agent.

No key (detection failed) means the browser's shared current tab, as before agents had their own.
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
from collections.abc import Callable, Mapping
from typing import NamedTuple

# Host session ids, exact and cheap: no process walk. Only a hash of the value leaves this module.
HOST_SESSION_VARS = (("COPILOT_AGENT_SESSION_ID", "copilot"), ("CLAUDE_CODE_SESSION_ID", "claude"))

# Processes between the agent and this one: shells and launchers, often a new one per command.
# Never `node`: Copilot CLI's host is a node process (named `MainThread` on Linux).
LAUNCHERS = frozenset("""
    bash sh zsh fish dash ksh mksh ash tcsh csh nu pwsh powershell cmd
    uv uvx py pythonw webpilot env sudo doas timeout nohup nice xargs winpty winpty-agent login
""".split())

# Terminals: everything under one is a person or an agent typing in one long-lived shell per terminal.
TERMINAL_HOSTS = frozenset("""
    windowsterminal openconsole conhost code code-insiders codium cursor windsurf mintty
    tmux screen sshd sshd-session gnome-terminal-server gnome-terminal konsole xterm alacritty kitty wezterm
    wezterm-gui terminator tilix xfce4-terminal mate-terminal lxterminal terminal iterm2 ghostty tabby hyper
""".split())

MAX_DEPTH = 30


class Proc(NamedTuple):
    name: str
    ppid: int
    created: float  # start time, so a reused pid gives another key


Lookup = Callable[[int], Proc]


def _norm(name: str) -> str:
    """`Code - Insiders.exe` -> `code`, `tmux: server` -> `tmux`, `python3.12` -> `python`."""
    name = name.lower().removesuffix(".exe")
    name = re.split(r"[\s:]", name.strip(), maxsplit=1)[0]
    return "python" if name.startswith("python") and name != "pythonw" else name


def _is_launcher(name: str) -> bool:
    return name in LAUNCHERS or name == "python"


def _short_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()[:12]


def psutil_lookup() -> Lookup:
    """Process lookup through psutil, imported only here (the env rungs need no process walk)."""
    import psutil

    # Windows: psutil's ppid() lists every process on each call (~8 ms); its parent map does it once.
    ppid_map = getattr(psutil._psplatform, "ppid_map", None)
    parents: dict[int, int] | None = ppid_map() if sys.platform == "win32" and ppid_map else None

    def lookup(pid: int) -> Proc:
        p = psutil.Process(pid)
        ppid = parents[pid] if parents is not None and pid in parents else p.ppid()
        return Proc(p.name(), ppid, p.create_time())

    return lookup


def from_process_tree(lookup: Lookup, start: int) -> str | None:
    """The agent's key from the ancestors of `start` (this process's parent), or None."""
    pid, below, below_created = start, None, float("inf")
    for _ in range(MAX_DEPTH):
        if pid <= 0:
            return None
        proc = lookup(pid)
        if proc.created > below_created:
            return None  # the real parent ended and its pid was reused by a later process
        name = _norm(proc.name)
        if not _is_launcher(name):
            if name in TERMINAL_HOSTS and below:
                return below
            return f"{name}:{pid}:{int(proc.created)}"
        below = f"{name}:{pid}:{int(proc.created)}"
        if proc.ppid == pid:
            return None
        pid, below_created = proc.ppid, proc.created
    return None


def agent_key(environ: Mapping[str, str] | None = None, lookup: Lookup | None = None,
              start: int | None = None) -> str | None:
    """This caller's agent key (rungs 2-4 of the module docstring), or None for the shared current tab."""
    environ = os.environ if environ is None else environ
    if name := environ.get("WEBPILOT_SESSION", "").strip():
        return f"session:{name}"
    for var, label in HOST_SESSION_VARS:
        if value := environ.get(var, "").strip():
            return f"{label}:{_short_hash(f'{var}:{value}')}"
    try:
        return from_process_tree(lookup or psutil_lookup(), os.getppid() if start is None else start)
    except Exception:  # noqa: BLE001 - access denied, a process gone mid-walk, no psutil: the shared tab
        return None
