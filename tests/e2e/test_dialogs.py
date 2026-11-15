"""alert, confirm and prompt: answered during actions and navigations instead of blocking the page, and
reported in the result; a dialog nobody answered fails the next command with a clear message."""

import json
import sys
import time

import pytest
from helpers import page_log, ref

from webpilot import cli, session_log
from webpilot.client import WebPilotError

pytestmark = pytest.mark.e2e

DISMISSED = ("the page asked for confirmation and it was dismissed; if the user agreed to this, repeat with "
             "--dialog accept")


def test_confirm_is_dismissed_by_default_and_reported(b, site):
    b.goto(site.url("dialogs.html?noframe=1"))
    res = b.click("#confirm")
    assert res["dialogs"] == [{"type": "confirm", "message": "Delete the item?", "answer": False}]
    assert res["hint"] == DISMISSED
    assert page_log(b) == ["kept"]


def test_alert_is_closed_without_a_hint(b, site):
    b.goto(site.url("dialogs.html?noframe=1"))
    res = b.click("#alert")
    assert res["dialogs"] == [{"type": "alert", "message": "Saved", "answer": None}]
    assert "hint" not in res
    assert page_log(b) == ["alert done"]


def test_dialog_accept_and_prompt_text_reach_the_page(b, site):
    b.goto(site.url("dialogs.html?noframe=1"))
    res = b.click("#confirm", dialog="accept")
    assert res["dialogs"][0]["answer"] is True and "hint" not in res
    res = b.click("#prompt", dialog="accept")
    assert res["dialogs"] == [{"type": "prompt", "message": "Your name?", "answer": "Anonymous"}]  # its default
    b.click("#prompt", dialog="accept", prompt_text="Ana")
    res = b.click("#prompt")
    assert res["dialogs"][0]["answer"] is None and res["hint"] == DISMISSED
    assert page_log(b) == ["deleted", "name: Anonymous", "name: Ana", "no name"]
    with pytest.raises(WebPilotError, match="dialog must be 'accept' or 'dismiss'"):
        b.click("#confirm", dialog="yes")


def test_a_dialog_inside_an_iframe(b, site):
    b.goto(site.url("dialogs.html"))
    button = ref(b.snapshot()["text"], "button", "Child delete")
    assert button.startswith("f")
    res = b.click(button)
    assert res["dialogs"] == [{"type": "confirm", "message": "Delete the item?", "answer": False,
                               "frame": button.split("e")[0]}]
    assert page_log(b, 1) == ["child kept"]


def test_a_trusted_click_and_a_key_press(b, site):
    b.goto(site.url("dialogs.html?noframe=1"))
    res = b.click("#confirm", trusted=True, dialog="accept")
    assert res["dialogs"][0]["answer"] is True
    b.eval("document.querySelector('#prompt').focus()")
    res = b.press("Enter", dialog="accept", prompt_text="Bia")
    assert res["dialogs"][0]["type"] == "prompt"
    assert page_log(b) == ["deleted", "name: Bia"]


def test_the_page_answers_its_own_dialogs_again_after_the_action(b, site):
    b.goto(site.url("dialogs.html?noframe=1"))
    b.click("#alert")
    assert b.eval("window[Symbol.for('webpilot.dialogs')].until") == 0


def test_goto_a_page_that_alerts_while_loading(b, site):
    start = time.monotonic()
    res = b.goto(site.url("dialogs.html?onload=1&noframe=1"))
    assert time.monotonic() - start < 10
    assert res["loaded"] is True
    assert res["dialogs"] == [{"type": "alert", "message": "Welcome to the dialogs page", "answer": None}]
    assert page_log(b) == ["onload:undefined"]
    res = b.reload()
    assert res["loaded"] is True and res["dialogs"][0]["type"] == "alert"


def test_a_dialog_nobody_answered_fails_the_next_command(b, site):
    b.goto(site.url("dialogs.html?noframe=1"))
    b.eval("setTimeout(() => alert('Too late'), 50), 1")  # after the command: the page's own dialog
    time.sleep(0.5)
    start = time.monotonic()
    with pytest.raises(WebPilotError, match="the page is not answering: a dialog it opened"):
        b.snapshot()
    assert time.monotonic() - start < 15  # checked after 5 s, given 5 s more to answer
    assert b.reload()["loaded"] is True  # navigating closes the dialog
    assert b.snapshot()["title"] == "Dialogs"


def test_leaving_a_page_that_asks_before_unload(b, site):
    b.goto(site.url("dialogs.html?beforeunload=1&noframe=1"))
    b.click("#title", trusted=True)  # beforeunload prompts only after a user gesture
    res = b.goto(site.url("basic.html"))
    assert res["loaded"] is True and res["title"] == "Basic"
    assert [d["type"] for d in res["dialogs"]] == ["beforeunload"] and res["dialogs"][0]["answer"] is True
    b.goto(site.url("dialogs.html?beforeunload=1&noframe=1"))
    b.click("#title", trusted=True)
    res = b.reload()
    assert res["loaded"] is True and res["dialogs"][0]["type"] == "beforeunload"
    b.click("#title", trusted=True)
    tab = b.info()["tabId"]
    res = b.close_tab()
    assert res["closed"] == tab and res["dialogs"][0]["type"] == "beforeunload"
    assert tab not in [t["id"] for t in b.tabs()]


def test_leaving_without_a_user_gesture_needs_no_debugger(b, site):
    b.goto(site.url("dialogs.html?beforeunload=1&noframe=1"))
    b.click("#title")  # synthetic: no user activation, so the page cannot ask
    res = b.goto(site.url("basic.html"))
    assert res["loaded"] is True and "dialogs" not in res


def test_cli_prints_dialogs_and_the_log_keeps_only_their_types(b, site, monkeypatch, capsys):
    b.goto(site.url("dialogs.html?noframe=1"))
    monkeypatch.setattr(sys, "argv", ["webpilot", "--temp", "click", "#prompt", "--dialog", "accept",
                                      "--prompt-text", "Secret name"])
    try:
        cli.run()
    except SystemExit as e:
        assert not e.code
    res = json.loads(capsys.readouterr().out)
    assert res["dialogs"] == [{"type": "prompt", "message": "Your name?", "answer": "Secret name"}]
    entry = session_log.read([session_log.session_name()])[-1]
    assert entry["cmd"] == "click" and entry["dialogs"] == ["prompt"]
    assert entry["args"]["promptText"] == "<11 chars>" and entry["args"]["dialog"] == "accept"
    assert "Your name" not in json.dumps(entry)
