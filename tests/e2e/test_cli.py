"""The `webpilot` command line against the test daemon: exit codes, output, `eval --out`, and the session log
that `reflect-data` reads. Commands act on the test's tab, which is the extension's current tab."""

import json
import sys

import pytest
from helpers import CANVAS, png_size

from webpilot import cli, reflect, session_log

pytestmark = pytest.mark.e2e


@pytest.fixture
def run(b, monkeypatch, capsys):
    """Runs `webpilot --temp ARGS...` as the console script does; returns (exit code, stdout, stderr)."""

    def run(*args: str) -> tuple[int, str, str]:
        monkeypatch.setattr(sys, "argv", ["webpilot", "--temp", *args])
        try:
            cli.run()
            code = 0
        except SystemExit as e:
            code = e.code or 0
        out, err = capsys.readouterr()
        return code, out, err

    return run


def test_goto_with_snapshot(run, site):
    code, out, err = run("goto", site.url("basic.html"), "-s")
    assert code == 0 and err == ""
    result, snapshot = out.split("\n\n", 1)
    assert json.loads(result)["title"] == "Basic"
    assert snapshot.startswith(f"# Basic\n{site.url('basic.html')}\n\n")
    assert '"Go"]' in snapshot and "Item two" in snapshot


def test_wait_that_times_out_exits_1_with_its_result(run, b, site):
    b.goto(site.url("basic.html"))
    code, out, err = run("wait", "--text", "Never shown", "--timeout", "1")
    assert code == 1 and json.loads(out)["found"] is False
    assert err == "error: text 'Never shown' did not appear within 1 s\n"
    code, out, err = run("wait", "--text", "Some intro text.")
    assert code == 0 and json.loads(out)["found"] is True and err == ""


def test_action_errors_exit_1_on_stderr(run, b, site):
    b.goto(site.url("basic.html"))
    code, out, err = run("click", "#missing", "--timeout", "1")
    assert code == 1 and out == ""
    assert err == "error: element not found: #missing (waited 1s)\n"
    # The action ran but its marker never came: the result is printed, and the exit code says so.
    code, out, err = run("click", "#go", "--wait-text", "Never shown", "--wait-timeout", "1")
    assert code == 1 and json.loads(out)["waited"]["found"] is False
    assert err == "error: the --wait-text/--wait-for condition did not appear\n"
    assert b.eval("window.__log") == ["go"]


def test_eval_out_writes_the_decoded_png(run, b, site, tmp_path):
    b.goto(site.url("basic.html"))
    path = tmp_path / "chart.png"
    code, out, err = run("eval", CANVAS, "--out", str(path))
    assert code == 0 and err == ""
    assert json.loads(out) == {"saved": str(path), "bytes": path.stat().st_size, "type": "image/png"}
    assert png_size(path.read_bytes()) == (30, 20)
    code, out, _ = run("eval", "(a, b) => a + b", "--args-json", "[2, 3]")
    assert code == 0 and json.loads(out) == 5


def test_a_missed_wait_is_logged_and_reported(run, b, site):
    b.goto(site.url("dynamic.html"))
    b.wait(text="Not on this page", timeout=1)
    b.click("#show-later", wait_text="Not either", wait_timeout=1)
    entries = session_log.read([session_log.session_name()])
    wait, click = entries[-2:]
    assert wait["cmd"] == "wait" and wait["wait_missed"] is True
    assert click["cmd"] == "click" and click["wait_missed"] is True and click["url"] == site.url("dynamic.html")
    assert session_log.session_name() == "e2e"  # the conftest keeps the run apart from real sessions

    suggestions = reflect.analyze(entries)["suggestions"]
    assert any(s.startswith("`wait` timed out") and "on 127.0.0.1" in s for s in suggestions), suggestions
    assert any(s.startswith("--wait-text/--wait-for of `click` timed out") for s in suggestions), suggestions
    code, out, _ = run("reflect-data", "--session", "e2e")
    assert code == 0 and "`wait` timed out" in out
