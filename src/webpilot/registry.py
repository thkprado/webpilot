"""Site parsers: Python modules that turn a page's HTML into compact JSON.

A parser module defines:
    MATCH = [r"^https://example\\.com/item/"]   # regexes tried against the page URL
    def parse(html: str, url: str) -> dict | list: ...

Search order (first match wins): WEBPILOT_PARSERS_DIR, <project>/parsers_user, built-in webpilot/parsers.
"""

from __future__ import annotations

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


def parser_dirs() -> list[Path]:
    dirs = []
    if os.environ.get("WEBPILOT_PARSERS_DIR"):
        dirs.append(Path(os.environ["WEBPILOT_PARSERS_DIR"]))
    dirs += [PROJECT_ROOT / "parsers_user", BUILTIN_DIR]
    return [d for d in dirs if d.is_dir()]


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
