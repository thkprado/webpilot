"""eval, fetch and screenshot against local pages."""

import base64

import pytest
from helpers import CANVAS, png_size

from webpilot.client import WebPilotError

pytestmark = pytest.mark.e2e


# ------------------------------------------------------------------ eval


def test_eval_values_and_promises(b, site):
    b.goto(site.url("basic.html"))
    assert b.eval("document.title") == "Basic"
    assert b.eval("({a: [1, 'x', null], b: true, s: 'São'})") == {"a": [1, "x", None], "b": True, "s": "São"}
    assert b.eval("undefined") is None
    assert b.eval("new Promise((r) => setTimeout(() => r(42), 200))") == 42
    assert b.eval("fetch('/api/echo').then((r) => r.json()).then((j) => j.method)") == "GET"


def test_eval_with_args(b, site):
    b.goto(site.url("basic.html"))
    tricky = "quotes ' \" and `backticks` ${x}\nnew line"
    assert b.eval("(o, n) => o.n + n", args=[{"n": 1}, 2]) == 3
    assert b.eval("(t) => t", args=[tricky]) == tricky
    assert b.eval("async (ms) => { await new Promise((r) => setTimeout(r, ms)); return ms; }", args=[50]) == 50
    with pytest.raises(WebPilotError, match="with arguments, the expression must be a function"):
        b.eval("document.title", args=[1])
    # A function without args would come back as {}: it is an error that says how to call it.
    for fn in ("() => document.title", "async () => 1", "(function () { return 1; })"):
        with pytest.raises(WebPilotError, match=r"is a function, which eval returns without calling it"):
            b.eval(fn)
    assert b.eval("() => document.title", args=[]) == "Basic"
    assert b.eval("(() => document.title)()") == "Basic"


def test_eval_errors(b, site):
    b.goto(site.url("basic.html"))
    with pytest.raises(WebPilotError, match="Error: boom"):
        b.eval("(() => { throw new Error('boom'); })()")
    with pytest.raises(WebPilotError, match="ReferenceError: nothingHere is not defined"):
        b.eval("nothingHere.x")
    with pytest.raises(WebPilotError, match="Error: async boom"):
        b.eval("Promise.reject(new Error('async boom'))")
    with pytest.raises(WebPilotError) as e:
        b.eval("let a = 1;\nlet b = a +* 2;")
    assert str(e.value) == ("SyntaxError: Unexpected token '*' at line 2, column 12:\n"
                            "  let a = 1;⏎let b = a +* 2;\n"
                            "  " + " " * len("let a = 1;⏎let b = a +") + "^")


def test_eval_timeout(b, site):
    b.goto(site.url("basic.html"))
    with pytest.raises(WebPilotError, match=r"timed out waiting for the browser \(eval\)"):
        b.eval("new Promise(() => {})", timeout=1)
    assert b.eval("1 + 1") == 2  # the tab still answers


def test_eval_canvas_data_url(b, site):
    b.goto(site.url("basic.html"))
    url = b.eval(CANVAS)
    assert url.startswith("data:image/png;base64,")
    assert png_size(base64.b64decode(url.split(",", 1)[1])) == (30, 20)


# ------------------------------------------------------------------ fetch


def header(echo: dict, name: str) -> str | None:
    return next((v for k, v in echo["headers"].items() if k.lower() == name.lower()), None)


def test_fetch_resolves_relative_urls_and_parses_json(b, site):
    b.goto(site.url("basic.html"))
    res = b.fetch("api/echo?x=1")
    assert res["status"] == 200 and res["url"] == site.url("api/echo?x=1")
    assert res["headers"]["content-type"] == "application/json"
    assert res["body"]["method"] == "GET" and res["body"]["path"] == "/api/echo?x=1"
    raw = b.fetch("/api/echo", raw=True)
    assert isinstance(raw["body"], str) and '"method": "GET"' in raw["body"]
    assert b.fetch("/nothing-here.html")["status"] == 404


def test_fetch_sends_the_tab_cookies_and_custom_headers(b, site):
    b.goto(site.url("set-cookie?name=e2e_sid&value=s3ssion"))
    b.goto(site.url("basic.html"))
    echo = b.fetch("/api/echo", headers={"X-Test": "yes"})["body"]
    assert echo["cookies"].get("e2e_sid") == "s3ssion"
    assert header(echo, "X-Test") == "yes"


def test_fetch_writes_need_allow_write(b, site):
    b.goto(site.url("basic.html"))
    for method in ("POST", "put", "DELETE"):
        with pytest.raises(WebPilotError, match=f"fetch {method.upper()} can change data on the site"):
            b.fetch("/api/echo", method=method, json={"a": 1})
    echo = b.fetch("/api/echo", method="POST", json={"a": 1}, allow_write=True)["body"]
    assert echo["method"] == "POST" and echo["body"] == '{"a": 1}'
    assert header(echo, "Content-Type") == "application/json"
    assert b.fetch("basic.html", method="HEAD")["status"] == 200  # reads need no confirmation


def test_fetch_timeout_and_tab_without_a_site(b, site):
    with pytest.raises(WebPilotError, match="open the site first"):
        b.fetch("/api/echo")  # the fresh tab is about:blank
    b.goto(site.url("basic.html"))
    with pytest.raises(WebPilotError, match="fetch timed out after 1 s"):
        b.fetch("/api/slow?ms=3000", timeout=1)


# ------------------------------------------------------------------ screenshot


def test_screenshot_viewport_and_full_page(b, site, tmp_path):
    b.goto(site.url("long.html"))
    scale, width, height, page_height = b.eval(
        "[devicePixelRatio, innerWidth, innerHeight, document.documentElement.scrollHeight]")
    shot = b.screenshot(tmp_path / "view.png")
    assert shot == (tmp_path / "view.png").resolve()
    assert png_size(shot.read_bytes()) == (round(width * scale), round(height * scale))
    full_w, full_h = png_size(b.screenshot(tmp_path / "full.png", full=True).read_bytes())
    assert full_h > height * scale and abs(full_h - page_height * scale) <= 2 and full_w >= width * scale - 20
