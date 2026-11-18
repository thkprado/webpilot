"""Two agents in one browser: each has its own current tab, and works in it while its tab is in the background."""

import time

import pytest
from helpers import PAGE_LOG, ref

from webpilot.client import Browser, WebPilotError

pytestmark = pytest.mark.e2e


@pytest.fixture
def agents(temp):
    """Browsers for agents "a" and "b"; tabs opened by the test are closed afterwards."""
    a, b = Browser("temp", autostart=False, agent="a"), Browser("temp", autostart=False, agent="b")
    yield a, b
    try:
        for t in a.tabs():
            if t["id"] not in temp.initial_tabs:
                a.close_tab(t["id"])
    except WebPilotError:
        pass
    a.close()
    b.close()


def by_id(browser: Browser) -> dict[int, dict]:
    return {t["id"]: t for t in browser.tabs()}


def test_each_agent_keeps_its_own_tab(agents, site):
    a, b = agents
    tab_a = a.new_tab(site.url("basic.html"))["tabId"]
    go = ref(a.snapshot()["text"], "button", "Go")
    tab_b = b.new_tab(site.url("dynamic.html"))["tabId"]  # in front now; A's tab goes to the background

    assert a.click(go)["clicked"] == 'button#go "Go"'  # A's ref, still in A's tab
    assert a.eval("window.__log") == ["go"]
    assert b.eval("window.__log") == []
    assert a.info()["tabId"] == tab_a and b.info()["tabId"] == tab_b

    seen_a, seen_b = by_id(a), by_id(b)
    assert seen_a[tab_a]["current"] and "other_agent" not in seen_a[tab_a]
    assert seen_a[tab_b]["other_agent"] and not seen_a[tab_b]["current"]
    assert seen_b[tab_b]["current"] and seen_b[tab_a]["other_agent"]

    assert b.close_tab() == {"closed": tab_b}  # B's own tab, not A's
    assert a.info()["tabId"] == tab_a
    assert "other_agent" not in by_id(a).get(tab_b, {})
    # B has no current tab now: its next command opens a fresh one instead of taking A's.
    assert b.info()["tabId"] not in (tab_a, tab_b)


def test_no_agent_uses_the_shared_tab(agents, site):
    a, _ = agents
    shared = Browser("temp", autostart=False, agent="", log=False)
    try:
        tab_shared = shared.new_tab(site.url("nav-a.html"))["tabId"]
        tab_a = a.new_tab(site.url("nav-b.html"))["tabId"]
        assert shared.info()["tabId"] == tab_shared  # A's new tab did not move it
        assert by_id(a)[tab_shared]["other_agent"]
        assert by_id(shared)[tab_a]["other_agent"]
        # Another Browser without a key shares that slot, as every client did before agent keys.
        other = Browser("temp", autostart=False, agent="", log=False)
        try:
            assert other.info()["tabId"] == tab_shared
        finally:
            other.close()
    finally:
        shared.close()


def test_closing_another_agents_tab_frees_its_slot(agents, site):
    a, b = agents
    tab_a = a.new_tab(site.url("basic.html"))["tabId"]
    b.new_tab(site.url("nav-a.html"))
    b.close_tab(tab_a)  # by id: allowed, e.g. when the user asks
    assert a.info()["tabId"] != tab_a  # A gets a fresh tab, not B's


def test_commands_work_in_a_background_tab(agents, site, tmp_path):
    """With two agents one tab is always in the background: no action may wait there for frames it never draws."""
    a, b = agents
    a.new_tab(site.url("dynamic.html"))
    tab_b = b.new_tab(site.url("input.html"))["tabId"]
    assert a.eval("document.visibilityState") == "hidden"

    def front() -> list[int]:
        return [t["id"] for t in b.tabs() if t["active"]]

    start = time.monotonic()
    res = a.click("#show-later", wait_text="Arrived late")  # a page timer of 800 ms, then the settle wait
    assert "busy" not in res
    assert "Arrived late" in a.snapshot()["text"]
    a.click("#hide-later")
    assert a.wait(text="Loading...", gone=True, timeout=5)
    a.click("text=Target", trusted=True)  # a lone mouse move used to wait 5 s for a frame
    assert a.eval(PAGE_LOG, args=[1]) == ["target"]

    a.goto(site.url("hover.html"))
    a.hover("#css-menu", trusted=True)  # a CSS :hover menu needs the real pointer
    assert "Repairs" in a.snapshot()["text"]
    assert front() == [tab_b]  # brought to the front for the move, then B's tab put back

    for kw in ({}, {"full": True}, {"target": "#css-menu"}):
        shot = a.screenshot(tmp_path / "shot.png", **kw)  # could take up to 15 s in a background tab
        assert shot.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        assert front() == [tab_b]

    a.goto(site.url("input.html"))
    res = a.type("#b", "typed in the background", trusted=True)
    assert "busy" not in res
    assert a.eval("document.getElementById('b').value") == "typed in the background"
    assert b.eval("document.getElementById('b').value") == ""  # B's page untouched
    assert time.monotonic() - start < 12, "an action in a background tab waited for its cap"
