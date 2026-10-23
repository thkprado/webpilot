"""Site parsers: Python modules that turn a page's HTML into compact JSON.

A parser module defines:
    MATCH = [r"^https://example\\.com/item/"]   # regexes tried against the page URL
    def parse(html: str, url: str) -> dict | list: ...

Search order (first match wins): WEBPILOT_PARSERS_DIR, <project>/parsers_user, built-in webpilot/parsers.
The user's folders also hold scripts (`scripts/*.py`, run by `webpilot script`) and site notes (`NOTES.md`).
"""

from __future__ import annotations

import ast
import importlib.util
import os
import re
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from .config import PROJECT_ROOT

BUILTIN_DIR = Path(__file__).parent / "parsers"


@dataclass
class Parser:
    name: str
    path: Path
    patterns: list[re.Pattern]
    module: ModuleType

    def matches(self, url: str) -> bool:
        return any(p.search(url) for p in self.patterns)

    def parse(self, html: str, url: str):
        return self.module.parse(html, url)


@dataclass
class Script:
    name: str
    path: Path
    doc: str  # first line of the docstring


def env_dir() -> Path | None:
    value = os.environ.get("WEBPILOT_PARSERS_DIR")
    return Path(value) if value else None


def local_dirs(existing: bool = True) -> list[Path]:
    """The user's folders in lookup order: WEBPILOT_PARSERS_DIR (when set), then <project>/parsers_user.

    Deduplicated, since the variable may point at the clone's own folder. existing=False keeps missing
    folders too, to say where a lookup searched.
    """
    dirs: list[Path] = []
    for d in [env_dir(), PROJECT_ROOT / "parsers_user"]:
        if d and (d.is_dir() or not existing) and d.resolve() not in {x.resolve() for x in dirs}:
            dirs.append(d)
    return dirs


def parser_dirs() -> list[Path]:
    return local_dirs() + [BUILTIN_DIR]


def script_dirs(existing: bool = True) -> list[Path]:
    return [d / "scripts" for d in local_dirs(existing) if not existing or (d / "scripts").is_dir()]


def notes_files() -> list[Path]:
    """Every NOTES.md of the user's folders, in lookup order: notes have no name to shadow each other by."""
    return [d / "NOTES.md" for d in local_dirs() if (d / "NOTES.md").is_file()]


def scripts() -> tuple[list[Script], list[tuple[Path, Path]], list[tuple[Path, str]]]:
    """Returns (scripts, shadowed as (path, shadowed by), read errors). Files starting with _ are helpers."""
    found: list[Script] = []
    shadowed: list[tuple[Path, Path]] = []
    errors: list[tuple[Path, str]] = []
    seen: dict[str, Path] = {}
    for d in script_dirs():
        for path in sorted(d.glob("*.py")):
            if path.name.startswith("_"):
                continue
            if path.stem in seen:
                shadowed.append((path, seen[path.stem]))
                continue
            seen[path.stem] = path  # a broken script still takes its name: running it finds this file
            try:
                doc = ast.get_docstring(ast.parse(path.read_text("utf-8"), str(path))) or ""
            except (OSError, UnicodeDecodeError, SyntaxError, ValueError) as e:
                errors.append((path, f"{type(e).__name__}: {e}"))
                continue
            found.append(Script(path.stem, path, doc.strip().splitlines()[0] if doc.strip() else ""))
    return found, shadowed, errors


def find_script(name: str) -> Path | None:
    stem = name.removesuffix(".py")
    return next((d / f"{stem}.py" for d in script_dirs() if (d / f"{stem}.py").is_file()), None)


def _load(path: Path) -> Parser:
    spec = importlib.util.spec_from_file_location(f"webpilot_parser_{path.stem}_{abs(hash(path))}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "parse") or not hasattr(module, "MATCH"):
        raise ValueError(f"{path} must define MATCH and parse(html, url)")
    patterns = [re.compile(m) for m in module.MATCH]
    return Parser(getattr(module, "NAME", path.stem), path, patterns, module)


def load_all() -> tuple[list[Parser], list[tuple[Path, str]]]:
    """Returns (parsers, load errors). Earlier directories shadow later ones by name."""
    parsers: list[Parser] = []
    errors: list[tuple[Path, str]] = []
    seen: set[str] = set()
    for d in parser_dirs():
        for path in sorted(d.glob("*.py")):
            if path.name.startswith("_") or path.stem in seen:
                continue
            try:
                p = _load(path)
            except Exception as e:  # noqa: BLE001 - a broken user parser must not break the CLI
                errors.append((path, f"{type(e).__name__}: {e}"))
                continue
            seen.add(path.stem)
            parsers.append(p)
    return parsers, errors


def find(url: str) -> Parser | None:
    return next((p for p in load_all()[0] if p.matches(url)), None)


def get(name: str) -> Parser | None:
    return next((p for p in load_all()[0] if p.name == name or p.path.stem == name), None)


def fixtures_dir(name: str) -> Path:
    """Where `webpilot parser fixture` saves new fixtures (local, not versioned)."""
    return PROJECT_ROOT / "parsers_user" / "fixtures" / name


def fixture_files(name: str) -> list[Path]:
    """Saved fixtures for parser NAME: the user's, plus the versioned ones of built-in parsers in tests/fixtures."""
    dirs = [fixtures_dir(name), PROJECT_ROOT / "tests" / "fixtures" / name]
    return sorted(f for d in dirs for f in d.glob("*.html"))


def read_fixture(path: Path) -> tuple[str, str]:
    """Fixtures are saved HTML whose first line is `<!-- url: ... -->`."""
    html = path.read_text("utf-8")
    first, _, rest = html.partition("\n")
    m = re.match(r"<!-- url: (.*) -->$", first.strip())
    return (m.group(1), rest) if m else ("", html)
