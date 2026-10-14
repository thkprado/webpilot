"""Temporary browser: Playwright's Chromium with a throwaway profile and the WebPilot extension loaded."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from . import config

STATE = "temp.json"


def _state_path() -> Path:
    return config.home() / STATE


def chromium_path() -> str:
    cache = config.home() / "chromium_path"
    if cache.exists() and Path(cache.read_text("utf-8").strip()).exists():
        return cache.read_text("utf-8").strip()
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        path = p.chromium.executable_path
    if not Path(path).exists():
        print("Installing Playwright Chromium (one-time)...", file=sys.stderr)
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
    cache.write_text(path, "utf-8")
    return path


def start(headless: bool = False) -> dict:
    dist = config.extension_dist()
    if not (dist / "manifest.json").exists():
        raise RuntimeError(f"extension not built: {dist} (run `npm install && npm run build` in extension/)")
    stop()
    profile = Path(tempfile.mkdtemp(prefix="webpilot-temp-"))
    ext = profile / "extension"
    shutil.copytree(dist, ext, ignore=shutil.ignore_patterns("config.json"))
    config.write_extension_config(ext, config.load(), "temp")
    args = [
        chromium_path(),
        f"--user-data-dir={profile / 'profile'}",
        f"--disable-extensions-except={ext}",
        f"--load-extension={ext}",
        "--no-first-run",
        "--no-default-browser-check",
        "--window-size=1280,900",
        # A window covered by others stays visible, so trusted input still reaches it (minimized is still hidden).
        "--disable-features=CalculateNativeWinOcclusion",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
    ]
    if headless:
        args.append("--headless=new")
    args.append("about:blank")
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    proc = subprocess.Popen(
        args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
        start_new_session=sys.platform != "win32",
    )
    state = {"pid": proc.pid, "profile": str(profile), "headless": headless, "started": time.time()}
    _state_path().write_text(json.dumps(state), "utf-8")
    return state


def stop() -> bool:
    path = _state_path()
    if not path.exists():
        return False
    state = json.loads(path.read_text("utf-8"))
    pid = state.get("pid")
    if pid:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
        else:
            import os
            import signal

            try:
                os.killpg(pid, signal.SIGTERM)
            except OSError:
                pass
    profile = Path(state["profile"]) if state.get("profile") else None
    if profile is None or not profile.name.startswith("webpilot-temp-"):
        profile = None  # never delete anything we did not create
    for _ in range(10):  # Chromium releases profile files a moment after exiting
        if profile is None or not profile.exists():
            break
        shutil.rmtree(profile, ignore_errors=True)
        if profile.exists():
            time.sleep(0.5)
    path.unlink(missing_ok=True)
    return True
