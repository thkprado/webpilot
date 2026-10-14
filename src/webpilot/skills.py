"""The `webpilot` Agent Skill: installs SKILL.md into the skills folder of each coding agent (harness)."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from .config import PROJECT_ROOT

TEMPLATE = Path(__file__).with_name("SKILL.md")
MARKER = "Installed by `webpilot skill install`"
README_URL = "https://github.com/thkprado/webpilot/blob/main/README.md"


@dataclass(frozen=True)
class Harness:
    name: str
    label: str
    home: str  # its config folder under ~; it counts as installed on this machine when that exists
    global_dir: str  # skills folder under ~
    project_dir: str  # skills folder under the project root


HARNESSES = {h.name: h for h in [
    Harness("claude", "Claude Code", ".claude", ".claude/skills", ".claude/skills"),
    Harness("codex", "Codex CLI", ".codex", ".codex/skills", ".codex/skills"),
    Harness("antigravity", "Antigravity (IDE and agy CLI)", ".gemini", ".gemini/config/skills", ".agents/skills"),
    Harness("pi", "pi", ".pi/agent", ".pi/agent/skills", ".pi/skills"),
    Harness("copilot", "GitHub Copilot CLI", ".copilot", ".copilot/skills", ".github/skills"),
]}
ALIASES = {"claude-code": "claude", "agy": "antigravity", "copilot-cli": "copilot"}


def resolve(name: str) -> Harness:
    key = ALIASES.get(name.lower(), name.lower())
    if key not in HARNESSES:
        raise ValueError(f"unknown harness {name!r}; choose from: {', '.join(HARNESSES)} (or agy)")
    return HARNESSES[key]


def detected(h: Harness, home: Path) -> bool:
    return (home / h.home).is_dir()


def skill_file(h: Harness, home: Path, project: Path | None = None) -> Path:
    base = project / h.project_dir if project else home / h.global_dir
    return base / "webpilot" / "SKILL.md"


def render() -> str:
    """SKILL.md pointing at this clone's README, or at GitHub for an install without the repository."""
    readme = PROJECT_ROOT / "README.md"
    where = readme.as_posix() if readme.exists() else README_URL
    return TEMPLATE.read_text("utf-8").replace("<readme>", where)


def ours(path: Path) -> bool:
    return path.is_file() and MARKER in path.read_text("utf-8", errors="replace")


def state(h: Harness, home: Path, project: Path | None = None) -> str:
    path = skill_file(h, home, project)
    if not path.exists():
        return "absent"
    if not ours(path):
        return "foreign"  # a webpilot skill written by hand or by something else
    return "installed" if path.read_text("utf-8") == render() else "outdated"


def install(h: Harness, home: Path, project: Path | None = None, force: bool = False) -> Path:
    path = skill_file(h, home, project)
    if path.exists() and not ours(path) and not force:
        raise FileExistsError(f"{path} exists and was not written by webpilot; pass --force to replace it")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(), "utf-8")
    return path


def uninstall(h: Harness, home: Path, project: Path | None = None, force: bool = False) -> Path | None:
    """Removes the skill folder; returns None when there was nothing of ours to remove."""
    path = skill_file(h, home, project)
    if not path.exists() or (not ours(path) and not force):
        return None
    if [p.name for p in path.parent.iterdir()] == ["SKILL.md"]:
        shutil.rmtree(path.parent)
    else:  # other files were added next to it: leave them
        path.unlink()
    return path
