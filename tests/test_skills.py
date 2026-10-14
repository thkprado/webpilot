"""`webpilot skill`: installs SKILL.md per harness and removes only what it wrote."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from webpilot import cli, skills
from webpilot.config import PROJECT_ROOT


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return tmp_path


def run(*args):
    return CliRunner().invoke(cli.app, ["skill", *args])


def test_render_points_at_this_readme():
    text = skills.render()
    assert text.startswith("---\nname: webpilot\n")
    assert (PROJECT_ROOT / "README.md").as_posix() in text and "<readme>" not in text


def test_install_update_and_uninstall(home):
    claude = skills.resolve("claude")
    path = skills.install(claude, home)
    assert path == home / ".claude/skills/webpilot/SKILL.md"
    assert skills.state(claude, home) == "installed"
    path.write_text(path.read_text("utf-8").replace("Browser", "Old"), "utf-8")
    assert skills.state(claude, home) == "outdated"
    skills.install(claude, home)
    assert skills.state(claude, home) == "installed"
    assert skills.uninstall(claude, home) == path
    assert not path.parent.exists() and path.parent.parent.exists()


def test_leaves_foreign_skill_and_extra_files(home):
    pi = skills.resolve("pi")
    path = skills.skill_file(pi, home)
    path.parent.mkdir(parents=True)
    path.write_text("---\nname: webpilot\n---\nmine", "utf-8")
    assert skills.state(pi, home) == "foreign"
    with pytest.raises(FileExistsError):
        skills.install(pi, home)
    assert skills.uninstall(pi, home) is None and path.exists()
    skills.install(pi, home, force=True)
    (path.parent / "notes.md").write_text("x", "utf-8")
    skills.uninstall(pi, home)
    assert not path.exists() and (path.parent / "notes.md").exists()


def test_project_folders(tmp_path):
    assert skills.skill_file(skills.resolve("agy"), tmp_path, tmp_path / "proj") == \
        tmp_path / "proj/.agents/skills/webpilot/SKILL.md"
    with pytest.raises(ValueError):
        skills.resolve("cursor")


def test_cli_all_uses_detected_harnesses(home):
    (home / ".gemini").mkdir()
    (home / ".pi/agent").mkdir(parents=True)
    res = run("install", "--all")
    assert res.exit_code == 0, res.output
    assert [d["harness"] for d in json.loads(res.output)["installed"]] == ["antigravity", "pi"]
    assert (home / ".gemini/config/skills/webpilot/SKILL.md").exists()
    assert not (home / ".claude").exists()
    res = run("uninstall", "agy")
    assert json.loads(res.output)["removed"][0]["harness"] == "antigravity"
    states = {h["harness"]: h["state"] for h in json.loads(run("list").output)}
    assert states == {"claude": "absent", "codex": "absent", "antigravity": "absent", "pi": "installed",
                      "copilot": "absent"}


def test_cli_rejects_unknown_harness(home):
    res = run("install", "cursor")
    assert res.exit_code != 0 and "unknown harness" in res.output
