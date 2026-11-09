"""Actions in depth: stale refs, waits, keys, typing, forms, scrolling, trusted input and reads."""

import re
import time

import pytest
from helpers import page_log, ref

from webpilot.client import WebPilotError

pytestmark = pytest.mark.e2e


# ------------------------------------------------------------------ stability


def test_a_ref_still_works_after_a_re_render(b, site):
    b.goto(site.url("dynamic.html"))
    target = ref(b.snapshot()["text"], "button", "Target")
    b.click("#rerender")
    assert b.eval("document.querySelector('#target-wrap button').hasAttribute('data-wp-ref')") is False
    res = b.click(target)
    assert res["reresolved"] is True and res["clicked"] == 'button "Target"'
    assert ref(b.snapshot()["text"], "button", "Target") == target  # the new element took over the ref
    assert page_log(b) == ["target"]


def test_a_ref_that_is_gone_fails_with_a_clear_error(b, site):
    b.goto(site.url("dynamic.html"))
    target = ref(b.snapshot()["text"], "button", "Target")
    b.click("#remove")
    with pytest.raises(WebPilotError, match=rf'ref {target} \(button "Target"\) is gone; take a new snapshot'):
        b.click(target, timeout=1)
    start = time.monotonic()
    with pytest.raises(WebPilotError, match="ref e9999 not found .*take a new snapshot"):
        b.click("e9999", timeout=30)  # never handed out: fails at once instead of waiting
    assert time.monotonic() - start < 5
    with pytest.raises(WebPilotError, match="invalid selector"):
        b.click("button[", timeout=30)


# ------------------------------------------------------------------ waits


def test_wait_for_text_and_selector(b, site):
    b.goto(site.url("dynamic.html"))
    b.click("#show-later")
    res = b.wait(text="Arrived late", timeout=5)
    assert res["found"] is True and res["ms"] > 0
    assert b.wait(selector="#late")["found"] is True
    b.click("#hide-later")
    assert b.wait(selector="#spinner", gone=True, timeout=5)["found"] is True
    assert b.wait(text="Loading...", gone=True, timeout=1)["found"] is True  # already gone


def test_wait_that_times_out_returns_found_false(b, site):
    b.goto(site.url("dynamic.html"))
    start = time.monotonic()
    res = b.wait(text="Never shown", timeout=1)
    assert res["found"] is False and res["ms"] >= 1000
    assert time.monotonic() - start < 5
    assert b.wait(selector="#target-wrap", gone=True, timeout=1)["found"] is False


def test_action_wait_text_and_selector(b, site):
    b.goto(site.url("dynamic.html"))
    res = b.click("#show-later", wait_text="Arrived late")
    assert res["waited"]["found"] is True
    assert b.text(selector="#late-zone")["text"] == "Arrived late"
    res = b.click("#hide-later", wait_selector="#late", wait_timeout=2)
    assert res["waited"]["found"] is True
    res = b.click("text=Target", wait_text="Never shown", wait_timeout=1)
    assert res["waited"]["found"] is False  # the API returns; the CLI exits 1 (test_cli.py)


def test_a_page_that_never_goes_quiet_hits_the_cap(b, site):
    b.goto(site.url("busy.html"))
    start = time.monotonic()
    res = b.click("text=Tick button")
    assert res["busy"] == "dom"
    assert time.monotonic() - start < 10  # 5 s cap on DOM churn
    start = time.monotonic()
    res = b.click("text=Tick button", wait_text="Time:")
    assert res["busy"] == "dom" and res["waited"]["found"] is True
    assert time.monotonic() - start < 5  # with a marker the cap is shorter
    assert page_log(b) == ["tick", "tick"]


# ------------------------------------------------------------------ keys


def keys(b) -> list:
    return [(e["key"], e["ctrl"], e["trusted"], e["target"]) for e in page_log(b) if "key" in e]


def test_press_keys_reach_the_focused_element(b, site):
    b.goto(site.url("input.html"))
    b.click("#b")
    for key in ("Escape", "ArrowDown", "ArrowUp", "x"):
        assert b.press(key)["pressed"] == key
    assert keys(b) == [("Escape", False, True, "b"), ("ArrowDown", False, True, "b"),
                       ("ArrowUp", False, True, "b"), ("x", False, True, "b")]
    assert b.eval("document.getElementById('b').value") == "x"  # a printable key types


def test_press_tab_moves_focus_and_control_a_selects_all(b, site):
    b.goto(site.url("input.html"))
    b.click("#a")
    b.press("Control+a")
    assert b.eval("(() => { const a = document.getElementById('a'); return [a.selectionStart, a.selectionEnd]; })()") == [
        0, len("first value")]
    b.press("Tab")
    assert b.eval("document.activeElement.id") == "b"
    assert keys(b) == [("a", True, True, "a"), ("Tab", False, True, "a")]
    with pytest.raises(WebPilotError, match="unknown key: Nope"):
        b.press("Nope")
    with pytest.raises(WebPilotError, match="unknown modifier: Hyper"):
        b.press("Hyper+a")


def test_press_enter_submits_the_focused_form(b, site):
    b.goto(site.url("input.html"))
    b.type("#q2", "via enter")
    b.press("Enter")
    assert {"submitted": "f2", "submitter": "s2", "q": "via enter"} in page_log(b)


# ------------------------------------------------------------------ typing


def test_type_into_textarea_and_contenteditable(b, site):
    b.goto(site.url("input.html"))
    b.type("#notes", "new notes")
    b.type("#notes", " and more", clear=False)
    assert b.eval("document.getElementById('notes').value") == "new notes and more"
    b.type("#editor", "fresh")
    assert b.eval("document.getElementById('editor').textContent") == "fresh"
    b.type("#editor", " text", clear=False)
    assert b.eval("document.getElementById('editor').textContent") == "fresh text"
    text = b.snapshot()["text"]
    assert re.search(r'\[e\d+ textarea "Notes" value="new notes and more"\]', text)
    ref(text, "div", "Editor")


def test_type_trusted_reaches_the_page_as_user_input(b, site):
    b.goto(site.url("input.html"))
    b.type("#b", "typed")
    b.type("#b", "real", trusted=True)
    b.type("#b", "!", trusted=True, clear=False)
    assert b.eval("document.getElementById('b').value") == "real!"
    inputs = [e["trusted"] for e in page_log(b) if e.get("input") == "b"]
    assert inputs[0] is False and inputs[-1] is True and all(inputs[1:])
    b.type("#editor", "rich", trusted=True)
    assert b.eval("document.getElementById('editor').textContent") == "rich"


def test_type_into_something_not_editable_is_an_error(b, site):
    b.goto(site.url("input.html"))
    with pytest.raises(WebPilotError, match="not editable"):
        b.type("h1", "x")
    with pytest.raises(WebPilotError, match="not editable"):
        b.type("h1", "x", trusted=True)


# ------------------------------------------------------------------ forms


def submissions(b) -> list:
    return [e for e in page_log(b) if "submitted" in e]


def test_submit_around_a_ref_the_focused_form_and_the_first_form(b, site):
    b.goto(site.url("input.html"))
    b.type("#q1", "one")
    b.type("#q2", "two")
    q2 = ref(b.snapshot()["text"], "input:text", "Query two")
    assert b.submit(q2)["submitted"] == 'form#f2 "Send two"'
    b.submit("#s1")  # a submit button is the submitter
    b.eval("document.getElementById('q2').focus()")
    b.submit()  # the focused form
    b.eval("document.activeElement.blur()")
    b.submit()  # the first visible form
    assert submissions(b) == [
        {"submitted": "f2", "submitter": None, "q": "two"},
        {"submitted": "f1", "submitter": "s1", "q": "one"},
        {"submitted": "f2", "submitter": None, "q": "two"},
        {"submitted": "f1", "submitter": None, "q": "one"},
    ]
    with pytest.raises(WebPilotError, match="no form around"):
        b.submit("h1")


def test_submit_with_no_form_on_the_page_is_an_error(b, site):
    b.goto(site.url("basic.html"))
    with pytest.raises(WebPilotError, match="no form on the page"):
        b.submit()


# ------------------------------------------------------------------ scroll


def test_scroll_directions_amounts_and_targets(b, site):
    b.goto(site.url("long.html"))
    viewport = b.eval("innerHeight")
    res = b.scroll("down")
    assert res["y"] == round(viewport * 0.8) == b.eval("Math.round(scrollY)")
    assert b.scroll("down", amount=100)["y"] == round(viewport * 0.8) + 100
    assert b.scroll("up", amount=100)["y"] == round(viewport * 0.8)
    res = b.scroll("bottom")
    assert res["y"] == res["height"] - res["viewport"] and res["height"] > 4000
    assert b.scroll("top")["y"] == 0
    res = b.scroll("#middle")
    box = b.eval("(() => { const r = document.getElementById('middle').getBoundingClientRect(); "
                 "return [r.top, r.bottom]; })()")
    assert 0 < box[0] < box[1] < viewport  # in view
    middle = ref(b.snapshot(selector="body")["text"], "button", "Middle button")
    b.scroll("top")
    assert b.scroll(middle)["y"] == res["y"]
    with pytest.raises(WebPilotError, match="element not found"):
        b.call("scroll", to="#missing", timeout=1)


# ------------------------------------------------------------------ reads


def test_text_with_selector_and_max_chars(b, site):
    b.goto(site.url("basic.html"))
    full = b.text()
    assert full["title"] == "Basic" and "Some intro text." in full["text"] and full["truncated"] is False
    assert "Hidden paragraph" not in full["text"]
    assert b.text(selector="#list")["text"] == "Item one\nItem two\nItem three"
    short = b.text(max_chars=10)
    assert short["text"] == full["text"][:10] and short["truncated"] is True
    with pytest.raises(WebPilotError, match="selector not found: #missing"):
        b.text(selector="#missing")


def test_html_with_selector(b, site):
    b.goto(site.url("basic.html"))
    page = b.html()
    assert page["html"].startswith("<html") and "<title>Basic</title>" in page["html"]
    assert b.html(selector="#go")["html"].startswith('<button id="go"')
    with pytest.raises(WebPilotError, match="selector not found: #missing"):
        b.html(selector="#missing")
