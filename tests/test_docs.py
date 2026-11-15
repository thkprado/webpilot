"""The agent guide stays short, and the links between the docs resolve."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

# docs/agent.md is read whole by every agent session, so each byte costs every session. Raise this only on purpose
# (and say why in the commit).
AGENT_MD_MAX = 8192

LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)\)")
FENCE = re.compile(r"^```.*?^```", re.S | re.M)


def slug(heading: str) -> str:
    """GitHub's anchor for a heading."""
    text = re.sub(r"[`*_]", "", heading.strip().lower())
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    return re.sub(r"[^\w\- ]", "", text).replace(" ", "-")


def anchors(path: Path) -> set[str]:
    text = FENCE.sub("", path.read_text("utf-8"))
    return {slug(m) for m in re.findall(r"^#+\s+(.+)$", text, re.M)}


def test_agent_guide_size():
    size = len((DOCS / "agent.md").read_bytes())
    assert size <= AGENT_MD_MAX, (
        f"docs/agent.md is {size} bytes, over {AGENT_MD_MAX}: every agent session reads it whole. Put details in "
        "docs/python-api.md or docs/troubleshooting.md, and what to do after a failure in the error message itself; "
        "keep one short quick-reference line per command and new rules for safety only."
    )


def test_relative_links_resolve():
    files = [*DOCS.glob("*.md"), ROOT / "README.md", ROOT / "README.pt-BR.md", ROOT / "AGENTS.md"]
    broken = []
    for md in files:
        text = FENCE.sub("", md.read_text("utf-8"))
        for target in LINK.findall(text):
            if re.match(r"[a-z][a-z0-9+.-]*:", target):  # https:, mailto:, ...
                continue
            path, _, anchor = target.partition("#")
            dest = (md.parent / path).resolve() if path else md
            if not dest.exists():
                broken.append(f"{md.relative_to(ROOT)}: {target} (no such file)")
            elif anchor and dest.suffix == ".md" and dest.parent == DOCS and anchor not in anchors(dest):
                broken.append(f"{md.relative_to(ROOT)}: {target} (no such heading)")
    assert not broken, "broken links:\n" + "\n".join(broken)
