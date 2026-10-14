"""Local configuration: ~/.webpilot (override with WEBPILOT_DIR)."""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PORT = 8765
DEFAULTS = {"port": DEFAULT_PORT, "auto_captcha": False, "blocked_domains": []}


def _private(path: Path, mode: int = 0o600) -> None:
    """Owner-only access: the token controls the browser. On Windows the user profile's ACLs do this."""
    if os.name != "nt":
        path.chmod(mode)


def _write_private(path: Path, text: str) -> None:
    """Writes a file that is never readable by other users, not even for a moment."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with open(fd, "w", encoding="utf-8") as f:
        f.write(text)
    _private(path)  # O_CREAT leaves the mode of an existing file as it was


def home() -> Path:
    custom = os.environ.get("WEBPILOT_DIR")
    path = Path(custom or Path.home() / ".webpilot")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not custom:
        _private(path, 0o700)  # also tightens a folder created by an older version
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
        _write_private(path, json.dumps(cfg, indent=2))
    else:
        _private(path)  # a config written by an older version may still be readable by others
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
    _write_private(path, json.dumps(data, indent=2))
    return path
