"""eval, fetch, requests and screenshot against local pages."""

import base64
import json
import sys

import pytest
from helpers import CANVAS, page_log, png_size

from webpilot import cli
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


# ------------------------------------------------------------------ requests


def paths(res: dict) -> list[str]:
    return [r["url"].split("/", 3)[3] for r in res["requests"]]


# The page's two calls on load start in the same millisecond or so: either may come first.
LOAD = ["api/echo?list=items", "api/echo?xhr=1"]


def open_requests(b, site, frame: bool = False) -> None:
    port = site.other.rsplit(":", 1)[1]
    b.goto(site.url(f"requests.html?port={port}" if frame else "requests.html"))
    b.wait(text="items:")
    page_log(b, 2 if frame else 1)  # the XHR answered (and the iframe's call)


def test_requests_lists_the_pages_fetch_and_xhr_calls(b, site):
    open_requests(b, site)
    res = b.requests()
    assert res["url"] == site.url("requests.html")
    assert sorted(paths(res)) == LOAD
    call = next(r for r in res["requests"] if r["url"].endswith("list=items"))
    assert call["status"] == 200 and call["contentType"] == "application/json" and call["bytes"] > 0
    assert call["ms"] >= 0 and "type" not in call and "n" not in call and "frame" not in call
    # --all adds the image (and the favicon), with each request's type.
    every = b.requests(all=True)
    assert {"api/echo?list=items", "api/echo?xhr=1", "pixel.svg"} <= set(paths(every))
    types = {p: r["type"] for p, r in zip(paths(every), every["requests"])}
    assert types["pixel.svg"] == "img" and types["api/echo?xhr=1"] == "xhr" and types["api/echo?list=items"] == "fetch"
    assert paths(b.requests(filter="XHR=1")) == ["api/echo?xhr=1"]  # any case
    # WebPilot's own fetch is not the page's: left out.
    b.fetch("/api/echo?own=1")
    assert "api/echo?own=1" not in paths(b.requests())


def test_requests_new_after_an_action_and_repeated_urls(b, site):
    open_requests(b, site)
    b.click("#more", wait_text="page 2")
    assert paths(b.requests(new=True)) == ["api/echo?page=2"]
    b.click("#again", wait_text="three calls done")
    new = b.requests(new=True)["requests"]
    assert len(new) == 1 and new[0]["url"].endswith("api/echo?same=1") and new[0]["n"] == 3
    # After a navigation, --new is what the new page asked.
    open_requests(b, site)
    assert sorted(paths(b.requests(new=True))) == LOAD
    empty = b.requests(new=True, filter="nothing-like-this")
    assert empty["requests"] == [] and "no requests since the last action" in empty["hint"]


def test_requests_max_keeps_the_newest_and_counts_the_rest(b, site):
    open_requests(b, site)
    b.click("#more", wait_text="page 2")
    res = b.requests(max=1)
    assert paths(res) == ["api/echo?page=2"] and res["omitted"] == 2
    with pytest.raises(WebPilotError, match="max must be a positive whole number"):
        b.requests(max=0)


def test_requests_past_the_browsers_buffer_and_in_iframes(b, site):
    open_requests(b, site, frame=True)
    res = b.requests()
    child = [r for r in res["requests"] if "frame" in r]
    assert len(child) == 1 and child[0]["url"] == site.other_url("api/echo?child=1")
    assert child[0]["frame"].startswith("f")
    # The browser keeps 250 entries per page; calls after that still show.
    b.eval("Promise.all(Array.from({length: 300}, (_, i) => fetch('/api/echo?n=' + i)))", timeout=30)
    b.click("#more", wait_text="page 2")
    assert paths(b.requests(new=True)) == ["api/echo?page=2"]
    assert len(b.requests(filter="echo?n=", max=1000)["requests"]) == 300


def test_cli_requests_prints_one_request_per_line(b, site, monkeypatch, capsys):
    open_requests(b, site)
    monkeypatch.setattr(sys, "argv", ["webpilot", "--temp", "requests", "--filter", "echo"])
    try:
        cli.run()
    except SystemExit as e:
        assert not e.code
    printed = capsys.readouterr().out
    res = json.loads(printed)
    assert sorted(paths(res)) == LOAD
    assert sum(line.startswith('    {') and line.rstrip(',').endswith('}') for line in printed.splitlines()) == 2
