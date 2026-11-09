"""`select` on react-select comboboxes (tests/pages/combobox), for both builds of the page: React 19 (`/`) and
React 17 with a legacy root, like www.npmjs.com (`/?react=17`). repro.py stays for investigating by hand."""

import json
from pathlib import Path

import pytest

from webpilot.client import WebPilotError

COMBOBOX = Path(__file__).parents[1] / "pages" / "combobox"  # served by the site fixture under /combobox/

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not (COMBOBOX / "bundle.js").exists() or not (COMBOBOX / "bundle17.js").exists(),
                       reason="combobox page not built (run `npm ci && npm run build` in tests/pages/combobox)"),
]


@pytest.fixture(params=["", "?react=17"], ids=["react19", "react17"])
def page(request, b, site):
    b.goto(site.url(f"/combobox/{request.param}"))
    assert b.wait(selector="#state")["found"]
    version = "React 17" if request.param else "React 19"
    assert b.text(selector="#react-version")["text"].startswith(version)
    return b


def state(b) -> dict:
    return json.loads(b.text(selector="#state")["text"])


def changes(b) -> list:
    """react-select's onChange calls, as (field, value)."""
    return [(e["field"], e["value"]) for e in b.eval("__events") if e["what"] == "change"]


@pytest.mark.parametrize(("target", "text", "field", "option"), [
    ("#field-inquire", "billing", "inquire", "I have an account or billing issue"),
    ("#field-country", "Peru", "country", "Peru"),  # long list: filtered by typing
    ("#field-plan", "Teams", "plan", "Teams"),  # not searchable: arrows only
    ("#field-plan-label + div", "enterprise", "plan", "Enterprise"),  # an element around the combobox
    ("#field-topic", "Security", "topic", "Security"),  # menu in a portal, closes on scroll
], ids=["inquire", "country", "plan", "plan-wrapper", "topic"])
def test_select_chooses_the_option(page, target, text, field, option):
    res = page.select(target, text)
    assert res["selected"] is True and res["option"] == option and option in res["value"]
    assert state(page)[field] == option
    assert changes(page) == [(field, option)]
    assert page.eval("!!document.querySelector('.react-select__menu')") is False  # the menu closed


def test_select_on_a_native_select(page):
    res = page.select("#native", "Pro")
    assert res == {**res, "selected": True, "option": "Pro", "value": "Pro", "changed": True}
    assert page.eval("document.getElementById('native').value") == "v1"


def test_select_of_a_missing_option_lists_the_options(page):
    with pytest.raises(WebPilotError, match=r'option not found: "Gold"; options: Free \| Pro \| Teams \| Enterprise'):
        page.select("#field-plan", "Gold")
    with pytest.raises(WebPilotError, match=r'option not found: "Atlantis"; options: Argentina \| Australia'):
        page.select("#field-country", "Atlantis")  # typed text matched nothing: the full list is shown
    assert state(page)["plan"] is None and state(page)["country"] is None
    assert page.eval("!!document.querySelector('.react-select__menu')") is False
