"""Every parser must parse each of its saved fixtures into non-empty data."""

from pathlib import Path

import pytest

from webpilot import registry
from webpilot.reflect import analyze

PARSERS, LOAD_ERRORS = registry.load_all()
CASES = [(p, fx) for p in PARSERS for fx in registry.fixture_files(p.name)]


def test_parsers_load():
    assert not LOAD_ERRORS, LOAD_ERRORS
    assert {"google", "duckduckgo"} <= {p.name for p in PARSERS}


@pytest.mark.parametrize("parser,fixture", CASES, ids=[f"{p.name}/{f.name}" for p, f in CASES])
def test_fixture(parser, fixture):
    url, html = registry.read_fixture(fixture)
    assert parser.matches(url), f"{parser.name} MATCH does not cover {url}"
    data = parser.parse(html, url)
    assert data, "parser returned empty data"


def test_google_results_have_fields():
    google = registry.get("google")
    fixtures = registry.fixture_files("google")
    assert fixtures
    for fx in fixtures:
        url, html = registry.read_fixture(fx)
        results = google.parse(html, url)["results"]
        assert results
        for r in results:
            assert r["title"] and r["url"].startswith("http")


def test_google_skips_only_google_hosts():
    html = """<div id="rso">
    <div><a href="https://maps.google.com/x"><h3>Maps</h3></a></div>
    <div><a href="https://user:pw@Google.com:443/y"><h3>Google</h3></a></div>
    <div><a href="https://notgoogle.com/z"><h3>Lookalike</h3></a></div>
    <div><a href="https://google.com.evil.test/w"><h3>Suffix</h3></a></div>
    </div>"""
    urls = [r["url"] for r in registry.get("google").parse(html, "https://www.google.com/search?q=t")["results"]]
    assert urls == ["https://notgoogle.com/z", "https://google.com.evil.test/w"]


def test_duckduckgo_minimal_html():
    html = """<div class="result"><a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fa.test%2Fx">A</a>
    <a class="result__snippet">snip</a></div>
    <div class="result result--ad"><a class="result__a" href="https://ad.test">Ad</a></div>"""
    data = registry.get("duckduckgo").parse(html, "https://html.duckduckgo.com/html/?q=t")
    assert data == {"query": "t", "results": [{"title": "A", "url": "https://a.test/x", "snippet": "snip"}]}


def test_reflect_suggests_parser_and_flags_failures():
    entries = [
        {"cmd": "goto", "url": "https://shop.test/a", "ok": True},
        {"cmd": "snapshot", "url": "https://shop.test/a", "ok": True, "out_chars": 9000},
        {"cmd": "snapshot", "url": "https://shop.test/b", "ok": True, "out_chars": 9000},
        {"cmd": "html", "url": "https://shop.test/b", "ok": True, "out_chars": 900000, "purpose": "extract"},
        {"cmd": "extract", "url": "https://news.test/", "ok": False, "parser": "news", "error": "KeyError: x"},
    ]
    report = analyze(entries)
    text = "\n".join(report["suggestions"])
    assert "Write a parser for shop.test" in text
    assert "Fix parser news" in text
    assert "900000" not in text  # internal fetches are not "large outputs"



def test_reflect_separates_flows_and_credits_iframes():
    exam = "https://quiz.test/exam"
    entries = [{"cmd": "goto", "url": exam, "ok": True}]
    for n in range(6):  # snapshot -> click: refs for an interactive flow, not content to parse
        entries += [
            {"cmd": "snapshot", "url": exam, "ok": True, "out_chars": 3000,
             "frames": [{"domain": "lms.test", "chars": 2500}]},
            {"cmd": "wait", "url": exam, "ok": True},
            {"cmd": "click", "url": exam, "ok": True},
        ]
    entries += [
        {"cmd": "snapshot", "url": "https://shop.test/a", "ok": True, "out_chars": 9000},
        {"cmd": "goto", "url": "https://shop.test/b", "ok": True},
        {"cmd": "snapshot", "url": "https://shop.test/b", "ok": True, "out_chars": 9000},
    ]
    report = analyze(entries)
    text = "\n".join(report["suggestions"])
    assert "Write a parser for shop.test" in text
    assert "parser for lms.test" not in text and "parser for quiz.test" not in text
    assert "Record the flow on lms.test: 6 reads (15000 chars)" in text
    domains = {d["domain"]: d for d in report["domains"]}
    assert domains["quiz.test"]["action_chars"] == 3000  # the page around the iframe keeps its own share



def test_reflect_groups_outputs_and_flags_busy_pages():
    page = "https://quiz.test/exam"
    entries = [
        {"cmd": "html", "url": page, "ok": True, "out_chars": 90000, "purpose": "save"},  # html -o: not read
        {"cmd": "text", "url": page, "ok": True, "out_chars": 30000},
        {"cmd": "text", "url": page, "ok": True, "out_chars": 40000},
    ] + [
        {"cmd": "click", "url": page, "ok": True, "ms": 5400, "busy": "dom", "frame_domain": "lms.test",
         "args": {"target": f"#answer_{n}"} if n == 0 else {"target": f"#answer_{n}", "waitText": "Next"}}
        for n in range(3)
    ]
    text = "\n".join(analyze(entries)["suggestions"])
    assert "Large output (2x, up to 40000 chars) from `text` on quiz.test" in text
    assert "90000" not in text
    assert "Page never went quiet after 3 actions on lms.test" in text
    assert "1 of them had no --wait-text" in text


def test_example_parser():
    """The example in examples/parsers_user (what users copy to start their own parsers_user/)."""
    root = Path(__file__).parent.parent / "examples" / "parsers_user"
    parser = registry._load(root / "hackernews.py")
    for fx in sorted((root / "fixtures" / "hackernews").glob("*.html")):
        url, html = registry.read_fixture(fx)
        assert parser.matches(url)
        stories = parser.parse(html, url)["stories"]
        assert len(stories) >= 20
        assert all(s["title"] and s["id"] for s in stories)
        assert any(s["points"] for s in stories)
