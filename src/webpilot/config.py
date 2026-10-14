"""Local configuration: ~/.webpilot (override with WEBPILOT_DIR)."""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PORT = 8765
DEFAULTS = {"port": DEFAULT_PORT, "auto_captcha": False, "blocked_domains": []}


def home() -> Path:
    path = Path(os.environ.get("WEBPILOT_DIR") or Path.home() / ".webpilot")
    path.mkdir(parents=True, exist_ok=True)
    return path


def extension_dist() -> Path:
    return Path(os.environ.get("WEBPILOT_EXTENSION_DIR") or PROJECT_ROOT / "extension" / "dist")


def load() -> dict:
    """Reads the config, creating the token and defaults on first use."""
    path = home() / "config.json"
    cfg = json.loads(path.read_text("utf-8")) if path.exists() else {}
    missing = {k: v for k, v in DEFAULTS.items() if k not in cfg}
    if "token" not in cfg:
        missing["token"] = secrets.token_urlsafe(24)
    if missing:
        cfg.update(missing)
        path.write_text(json.dumps(cfg, indent=2), "utf-8")
    if os.environ.get("WEBPILOT_PORT"):
        cfg["port"] = int(os.environ["WEBPILOT_PORT"])
    return cfg


def write_extension_config(ext_dir: Path, cfg: dict, mode: str) -> Path:
    """Writes the config.json the extension reads at startup (token, port, mode)."""
    data = {
        "token": cfg["token"],
        "port": cfg["port"],
        "mode": mode,
        "autoCaptcha": cfg.get("auto_captcha", False),
        "blockedDomains": cfg.get("blocked_domains", []),
    }
    path = ext_dir / "config.json"
    path.write_text(json.dumps(data, indent=2), "utf-8")
    return path
