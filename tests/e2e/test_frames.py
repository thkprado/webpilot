"""Iframes (same-origin and cross-origin) and shadow DOM: snapshot, refs, click, type and reads inside them."""

import re

import pytest
from helpers import page_log, ref

from webpilot.client import WebPilotError

pytestmark = pytest.mark.e2e


@pytest.fixture
def frames(b, site):
    """frames.html with one same-origin and one cross-origin child, both loaded; returns its snapshot text."""
    b.goto(site.url(f"frames.html?port={site.other.rsplit(':', 1)[1]}"))
    return b.snapshot()["text"]


# ------------------------------------------------------------------ frames


def test_snapshot_inlines_same_and_cross_origin_frames(b, frames):
    assert "[iframe Same frame]" in frames and "[iframe Cross frame]" in frames
    assert frames.count("[/iframe]") == 2
    same, cross = ref(frames, "button", "Same button"), ref(frames, "button", "Cross button")
    assert re.fullmatch(r"f\d+e\d+", same) and re.fullmatch(r"f\d+e\d+", cross)
    assert same.split("e")[0] != cross.split("e")[0]  # each frame has its own id
    assert "Only in the same frame" in frames and "Only in the cross frame" in frames
    assert re.search(r"\[e\d+ button \"Top button\"\]", frames)  # top-frame refs keep no prefix
    # Each frame's content sits between its placeholder and [/iframe].
    assert frames.index("[iframe Same frame]") < frames.index("Same button") < frames.index("[iframe Cross frame]")

    interactive = b.snapshot(interactive=True)["text"]
    assert ref(interactive, "button", "Cross button") == cross  # same refs in the interactive view


@pytest.mark.parametrize("trusted", [False, True])
def test_click_and_type_into_frames_by_ref(b, frames, trusted):
    for name in ("Same", "Cross"):
        res = b.click(ref(frames, "button", f"{name} button"), trusted=trusted)
        assert res["clicked"] == f'button#child-btn "{name} button"'
        assert "frameUrl" in res and "frame-child.html" in res["frameUrl"]
        b.type(ref(frames, "input:text", f"{name} input"), f"hello {name}", trusted=trusted)
    click = "click:trusted" if trusted else "click"
    assert page_log(b, 4) == [f"same:{click}", "same:value=hello Same", f"cross:{click}", "cross:value=hello Cross"]


def test_trusted_click_refuses_a_frame_covered_in_the_parent_page(b, frames):
    cross = ref(frames, "button", "Cross button")
    b.eval("document.body.insertAdjacentHTML('beforeend', "
           "'<div id=\"veil\" style=\"position:fixed;inset:0;z-index:9\" onclick=\"__log.push(`veil`)\">Wait</div>')")
    with pytest.raises(WebPilotError, match=rf'{cross} \(button#child-btn "Cross button"\) is covered by div#veil "Wait"'):
        b.click(cross, trusted=True, timeout=0.5)
    assert b.eval("window.__log") == []


def test_selector_and_text_targets_found_only_in_a_frame(b, frames):
    b.click(".cross-btn")  # no such element in the top frame: looked for in the iframes
    b.click("text=Same button")
    res = b.text(selector=".cross-text")
    assert res["text"] == "Only in the cross frame" and re.fullmatch(r"f\d+", res["frame"])
    html = b.html(selector=".same-text")
    assert html["html"].startswith('<p id="child-text"') and "frame" in html
    assert page_log(b, 2) == ["cross:click", "same:click"]


def test_html_with_frames_returns_each_frame_document(b, frames, site):
    page = b.html(frames=True)
    assert page["url"].startswith(site.url("frames.html"))
    by_url = {f["url"]: f for f in page["frames"]}
    same = by_url[site.url("frame-child.html?name=same")]
    cross = by_url[site.other_url("frame-child.html?name=cross")]
    assert re.fullmatch(r"f\d+", same["frame"]) and same["title"] == "Same child"
    assert "Only in the cross frame" in cross["html"] and cross["html"].startswith("<html")
    assert "child-btn" not in page["html"]  # the top document alone
    assert "frames" not in b.html()


# ------------------------------------------------------------------ shadow DOM


def test_snapshot_shows_open_shadow_roots(b, site):
    b.goto(site.url("shadow.html"))
    text = b.snapshot()["text"]
    assert "Inside the shadow root" in text
    for name in ("Shadow button", "Deep button", "Slotted button"):
        ref(text, "button", name)
    ref(text, "input:text", "Shadow input")


@pytest.mark.parametrize("trusted", [False, True])
def test_click_and_type_inside_shadow_roots(b, site, trusted):
    b.goto(site.url("shadow.html"))
    text = b.snapshot()["text"]
    b.click(ref(text, "button", "Shadow button"), trusted=trusted)
    b.click(ref(text, "button", "Deep button"), trusted=trusted)
    b.click(ref(text, "button", "Slotted button"), trusted=trusted)
    b.type(ref(text, "input:text", "Shadow input"), "in the shadow", trusted=trusted)
    assert page_log(b) == ["shadow:trusted" if trusted else "shadow", "deep", "slotted", "value=in the shadow"]


def test_text_and_css_targets_reach_into_shadow_roots(b, site):
    b.goto(site.url("shadow.html"))
    b.click("text=Shadow button")
    b.click("#deep-btn")
    b.type("#shadow-input", "by selector")
    assert page_log(b) == ["shadow", "deep", "value=by selector"]
