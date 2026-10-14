"""Local configuration: the files holding the daemon token stay private to their owner."""

import json
import os
import stat

import pytest

from webpilot import config


def mode(path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_load_creates_token_and_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("WEBPILOT_DIR", str(tmp_path))
    cfg = config.load()
    assert cfg["token"] and cfg["port"] == config.DEFAULT_PORT
    assert json.loads((tmp_path / "config.json").read_text("utf-8"))["token"] == cfg["token"]
    assert config.load()["token"] == cfg["token"]


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions; Windows relies on the profile's ACLs")
def test_token_files_are_owner_only(tmp_path, monkeypatch):
    monkeypatch.setenv("WEBPILOT_DIR", str(tmp_path / "wp"))
    cfg = config.load()
    path = tmp_path / "wp" / "config.json"
    assert mode(tmp_path / "wp") == 0o700
    assert mode(path) == 0o600
    path.chmod(0o644)  # as written by an older version
    config.load()
    assert mode(path) == 0o600
    ext = tmp_path / "ext"
    ext.mkdir()
    (ext / "config.json").write_text("{}", "utf-8")
    (ext / "config.json").chmod(0o644)
    assert mode(config.write_extension_config(ext, cfg, "real")) == 0o600
