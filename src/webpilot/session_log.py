"""Append-only JSONL log of every browser action, used by `webpilot reflect-data`.

One file per session in ~/.webpilot/sessions/. The session name defaults to today's date;
set WEBPILOT_SESSION to group a run under its own name.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

from .config import home

SECRET_ARGS = {"text", "body"}  # typed text may be a password, a request body anything: only the length is logged


def session_name() -> str:
    return os.environ.get("WEBPILOT_SESSION") or date.today().isoformat()


def sessions_dir() -> Path:
    path = home() / "sessions"
    path.mkdir(exist_ok=True)
    return path


def domain(url: str | None) -> str:
    if not url:
        return ""
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _clean_args(args: dict) -> dict:
    out = {}
    for k, v in args.items():
        if k in SECRET_ARGS and isinstance(v, str):
            out[k] = f"<{len(v)} chars>"
        elif k == "args" and isinstance(v, list):
            # eval arguments are page data (often typed text): only their number and size
            out[k] = f"<{len(v)} values, {len(json.dumps(v, ensure_ascii=False))} chars>"
        elif k == "headers" and isinstance(v, dict):
            out[k] = sorted(v)  # names only: values may be Cookie/Authorization
        elif isinstance(v, str) and len(v) > 200:
            out[k] = v[:200] + "..."
        else:
            out[k] = v
    return out


def record(**entry) -> None:
    entry["args"] = _clean_args(entry.get("args") or {})
    line = {"ts": datetime.now().isoformat(timespec="seconds"), "session": session_name(), **entry}
    try:
        with open(sessions_dir() / f"{session_name()}.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except OSError:
        pass  # logging must never break browsing


def available() -> list[str]:
    return sorted(p.stem for p in sessions_dir().glob("*.jsonl"))


def read(names: list[str]) -> list[dict]:
    entries = []
    for name in names:
        path = sessions_dir() / f"{name}.jsonl"
        if not path.exists():
            continue
        for line in path.read_text("utf-8").splitlines():
            if line.strip():
                entries.append(json.loads(line))
    return entries
