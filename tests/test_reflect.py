"""`reflect-data --usage`: per-command numbers that never carry page data."""

import json
import re
from pathlib import Path

from webpilot.cli import browser_commands
from webpilot.reflect import usage, usage_markdown
from webpilot.session_log import kind

ROOT = Path(__file__).resolve().parents[1]


def test_kind_keeps_only_the_leading_words():
    assert kind("element not found: #buy-now (waited 5s)") == "element not found"
    assert kind("no list of options opened for input#field-plan") == "no list of options opened for"
    assert kind("the browser window is minimized or covered, so real input would be lost") == \
        "the browser window is minimized or covered"
    assert kind('use select e5 "Premium plan"') == "use select"
    assert kind("Frame with ID 0 is showing error page") == "Frame with"
    assert kind("TypeError: Cannot read properties of null (reading 'textContent')") == "TypeError"
    assert kind("Uncaught SyntaxError: Invalid token") == "SyntaxError"
    assert kind("Maria Silva not allowed") == "other"  # a lone capitalised word may be a name
    assert kind("") == kind(None) == "other"


def test_usage_counts_per_command_without_page_data():
    entries = [
        {"ts": "2026-11-20T10:00:00", "session": "s", "cmd": "goto", "url": "https://shop.test/a", "ok": True, "ms": 900},
        {"ts": "2026-11-20T10:00:01", "session": "s", "cmd": "eval", "ok": True, "ms": 20},  # on shop.test
        # the page `extract` read for its parser: part of the extract, not a call of its own
        {"ts": "2026-11-20T10:00:01", "session": "s", "cmd": "html", "url": "https://shop.test/a", "ok": True,
         "purpose": "extract"},
        {"ts": "2026-11-20T10:00:02", "session": "s", "cmd": "click", "url": "https://shop.test/a", "ok": False,
         "ms": 5000, "error": "element not found: text=Secret Order 42 (waited 5s)"},
        {"ts": "2026-11-20T10:00:03", "session": "s", "cmd": "click", "url": "https://shop.test/a", "ok": True,
         "ms": 300, "hint": "the page showed no change"},
        {"ts": "2026-11-21T09:00:00", "session": "s", "cmd": "click", "url": "https://shop.test/b", "ok": True,
         "ms": 400, "wait_missed": True, "busy": "dom"},
        # test pages served locally: left out, eval included through the session's last URL
        {"ts": "2026-11-21T09:01:00", "session": "t", "cmd": "goto", "url": "http://127.0.0.1:8000/x", "ok": True},
        {"ts": "2026-11-21T09:01:01", "session": "t", "cmd": "eval", "ok": False, "error": "TypeError: x"},
        {"ts": "2026-11-21T09:01:02", "session": "u", "cmd": "select", "url": "file:///C:/pages/combo.html",
         "ok": False, "error": "option not found: \"Gold\""},
    ]
    report = usage(entries, ["click", "eval", "goto", "html", "select", "tab.new"])
    assert (report["entries"], report["local_left_out"], report["days"]) == (5, 3, 2)
    assert (report["first"], report["last"]) == ("2026-11-20", "2026-11-21")
    click = report["commands"][0]
    assert click == {"cmd": "click", "calls": 3, "share_pct": 60.0, "failed": 1, "failed_pct": 33.3,
                     "median_ms": 400, "wait_missed": 1, "busy": 1,
                     "hints": {"the page showed no change": 1}, "errors": {"element not found": 1}}
    assert report["never_used"] == ["html", "select", "tab.new"]
    text = usage_markdown(report, ["2026-11-20", "2026-11-21"]) + json.dumps(report)
    assert "shop.test" not in text and "Secret" not in text and "127.0.0.1" not in text
    assert "| click | 3 | 60.0 % | 1 (33.3 %) | 400 | 1 | 1 |" in text
    assert "- `click` x1: element not found" in text


def test_browser_commands_match_the_extension():
    # every command the extension runs for the CLI, plus extract (Python only); ping and profile.set are internal
    source = (ROOT / "extension" / "src" / "background" / "commands.ts").read_text("utf-8")
    extension = set(re.findall(r'^  "?([a-zA-Z.]+)"?: async', source, re.M)) - {"ping", "profile.set"}
    assert set(browser_commands()) == extension | {"extract"}
