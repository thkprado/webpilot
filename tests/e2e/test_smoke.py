"""Smoke suite: connection, tabs, navigation, snapshot, click and type in the real extension (headless)."""

import re

import pytest
from helpers import ref

from webpilot.client import WebPilotError

pytestmark = pytest.mark.e2e


def log(b) -> list:
    return b.eval("window.__log")


# ------------------------------------------------------------------ connection, tabs, navigation


def test_temp_browser_is_connected(b):
    assert "temp" in b.status()["extensions"]
    assert b.call("ping")["mode"] == "temp"


def test_goto_and_info(b, site):
    res = b.goto(site.url("basic.html"))
    assert res["url"] == site.url("basic.html")
    assert res["title"] == "Basic"
    assert res["loaded"] is True
    info = b.info()
    assert info["url"] == site.url("basic.html") and info["tabId"] == res["tabId"]


def test_tabs_new_use_close(b, site):
    first = b.goto(site.url("nav-a.html"))["tabId"]
    second = b.new_tab(site.url("nav-b.html"))
    assert second["title"] == "Nav B" and second["tabId"] != first
    tabs = {t["id"]: t for t in b.tabs()}
    assert tabs[second["tabId"]]["current"] and not tabs[first]["current"]
    assert b.info()["title"] == "Nav B"  # commands follow the newest tab

    assert b.use_tab(first)["title"] == "Nav A"
    assert b.info()["tabId"] == first
    assert {t["id"]: t for t in b.tabs()}[first]["current"]

    assert b.close_tab(second["tabId"]) == {"closed": second["tabId"]}
    assert second["tabId"] not in {t["id"] for t in b.tabs()}
    assert b.info()["tabId"] == first  # closing another tab leaves the current one alone


@pytest.mark.parametrize("trusted", [False, True])
def test_back_forward_reload(b, site, trusted):
    # Neither page gets a user gesture without --trusted; back must not skip them (Chromium's goBack does).
    with pytest.raises(WebPilotError, match="no previous page"):
        b.back()  # the fresh tab has no history yet
    b.goto(site.url("nav-a.html"))
    res = b.click("text=Go to B", trusted=trusted)
    assert res["changed"] is True and res["title"] == "Nav B"
    b.goto(site.url("nav-a.html"))
    assert b.back()["title"] == "Nav B"
    assert b.back()["title"] == "Nav A"
    res = b.forward()
    assert res["title"] == "Nav B" and res["url"] == site.url("nav-b.html") and res["loaded"] is True
    b.forward()
    with pytest.raises(WebPilotError, match="no next page"):
        b.forward()
    b.back()
    b.eval("window.__mark = 1")
    res = b.reload()
    assert res["title"] == "Nav B" and res["loaded"] is True
    assert b.eval("window.__mark ?? null") is None  # a fresh document


# ------------------------------------------------------------------ snapshot


def test_snapshot_refs_and_text(b, site):
    b.goto(site.url("basic.html"))
    snap = b.snapshot()
    text = snap["text"]
    assert snap["url"] == site.url("basic.html") and snap["truncated"] is False
    assert "# Basic page" in text and "Some intro text." in text
    assert re.search(r'\[e\d+ button "Go"\]', text)
    assert re.search(r'\[e\d+ link "To page A" -> /nav-a\.html\]', text)
    assert "Item two" in text


def test_snapshot_leaves_out_hidden_elements_and_script_hrefs(b, site):
    b.goto(site.url("basic.html"))
    text = b.snapshot()["text"]
    for hidden in ("Display none button", "Invisible button", "Hidden paragraph"):
        assert hidden not in text
    for name in ("Script link", "Data link", "VB link"):
        assert re.search(rf'\[e\d+ link "{name}"\]', text), name  # the link, without "-> href"
    assert "javascript:" not in text and "data:" not in text and "vbscript:" not in text


def test_snapshot_interactive_selector_and_max_chars(b, site):
    b.goto(site.url("basic.html"))
    interactive = b.snapshot(interactive=True)["text"]
    assert "Some intro text" not in interactive and "Item two" not in interactive
    lines = interactive.splitlines()
    assert lines and all(re.fullmatch(r"\[e\d+ .*\]", line) for line in lines), lines

    scoped = b.snapshot(selector="#list")["text"]
    assert "Item one" in scoped and "Item three" in scoped and "Go" not in scoped
    with pytest.raises(WebPilotError, match="selector not found"):
        b.snapshot(selector="#missing")

    short = b.snapshot(max_chars=40)
    assert short["truncated"] is True and len(short["text"]) <= 40


def test_refs_stay_the_same_across_snapshots(b, site):
    b.goto(site.url("basic.html"))
    first = ref(b.snapshot()["text"], "button", "Go")
    assert ref(b.snapshot()["text"], "button", "Go") == first


# ------------------------------------------------------------------ click


def test_click_by_ref_css_and_text(b, site):
    b.goto(site.url("basic.html"))
    go = ref(b.snapshot()["text"], "button", "Go")
    assert b.click(go)["clicked"] == 'button#go "Go"'
    b.click("#go")
    b.click("text=Go")
    b.click("text=Next|Próximo")  # the first label that exists wins
    assert log(b) == ["go", "go", "go", "next"]


def test_click_trusted_reaches_the_page_as_a_user_click(b, site):
    b.goto(site.url("basic.html"))
    b.eval("document.getElementById('go').addEventListener('click', (e) => log(e.isTrusted))")
    b.click("#go")
    b.click("#go", trusted=True)
    assert log(b) == ["go", False, "go", True]


def test_click_on_a_link_navigates(b, site):
    b.goto(site.url("basic.html"))
    res = b.click("text=To page A")
    assert res["changed"] is True
    assert res["url"] == site.url("nav-a.html") and res["title"] == "Nav A"


def test_click_on_a_missing_target_is_an_error(b, site):
    b.goto(site.url("basic.html"))
    with pytest.raises(WebPilotError, match="not found"):
        b.click("#missing", timeout=1)


# ------------------------------------------------------------------ type


def test_type_clears_or_appends(b, site):
    b.goto(site.url("form.html"))
    b.type("#name", "Ada")
    b.type("#name", "Grace")
    b.type("#city", " Paulo", clear=False)
    assert b.eval("['name', 'city'].map((id) => document.getElementById(id).value)") == ["Grace", "São Paulo"]
    assert "change:name" in log(b) and "change:city" in log(b)


def test_type_by_label_ref_and_submit(b, site):
    b.goto(site.url("form.html"))
    text = b.snapshot()["text"]
    assert re.search(r'\[e\d+ input:text "City" value="São"\]', text)
    name = ref(text, "input:text", "Name")
    res = b.type(name, "Ada", submit=True, wait_text="Submitted Ada")
    assert res["waited"]["found"] is True
    assert {"submitted": {"name": "Ada", "city": "São", "color": "r"}} in log(b)


def test_type_into_native_select(b, site):
    b.goto(site.url("form.html"))
    b.type("#color", "Green")  # by option text
    assert b.eval("document.getElementById('color').value") == "g"
    b.type("#color", "b")  # by option value
    assert b.eval("document.getElementById('color').value") == "b"
    assert re.search(r'\[e\d+ select "Color" value="Blue" options=\[Red\|Green\|Blue\]\]', b.snapshot()["text"])
    with pytest.raises(WebPilotError, match=r'option not found: "Purple"; options: Red \| Green \| Blue'):
        b.type("#color", "Purple")
