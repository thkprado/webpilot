"""fill: several fields in one command (text, textarea, contenteditable, select, checkbox, radio, switch), a field
that appears after an earlier one is filled, fields in iframes, the failure message, --submit, the CLI and what
the session log keeps. Custom dropdowns are in test_combobox.py."""

import json
import sys

import pytest
from helpers import page_log, ref

from webpilot import cli, session_log
from webpilot.client import WebPilotError

pytestmark = pytest.mark.e2e


@pytest.fixture
def form(b, site):
    b.goto(site.url("fill.html"))
    return b


def values(b) -> dict:
    return b.eval("""(() => {
      const v = (id) => document.getElementById(id);
      return {
        name: v("name").value, email: v("email").value, password: v("password").value, bio: v("bio").value,
        country: v("country").value, terms: v("terms").checked, news: v("news").checked,
        plan: document.querySelector("[name=plan]:checked").value, dark: v("dark").getAttribute("aria-checked"),
        notes: v("notes").innerText,
      };
    })()""")


def test_every_kind_of_field_in_one_command(form):
    res = form.fill({
        "#name": "Ana", "#email": "ana@example.com", "#password": "s3cret!", "#bio": "Line one", "#country": "Portugal",
        "#terms": True, "#news": False, "#plan-pro": "true", "#dark": True, "#notes": "Call after 5",
    })
    assert values(form) == {
        "name": "Ana", "email": "ana@example.com", "password": "s3cret!", "bio": "Line one", "country": "pt",
        "terms": True, "news": False, "plan": "pro", "dark": "true", "notes": "Call after 5",
    }
    filled = {f["target"]: f for f in res["filled"]}
    assert list(filled) == ["#name", "#email", "#password", "#bio", "#country", "#terms", "#news", "#plan-pro",
                            "#dark", "#notes"]
    assert filled["#name"] == {"target": "#name", "field": 'input#name "Name"', "value": "Ana"}
    assert filled["#password"] == {"target": "#password", "field": 'input#password "Password"'}  # never its value
    assert filled["#country"] == {"target": "#country", "field": 'select#country "Country"', "option": "Portugal",
                                  "value": "Portugal"}
    assert filled["#terms"]["checked"] is True and filled["#news"]["checked"] is False
    assert filled["#dark"] == {"target": "#dark", "field": 'div#dark "Dark mode"', "checked": True}
    assert res["changed"] is True
    assert "submitted" not in res and "Created" not in form.text(selector="#out")["text"]


def test_toggles_click_only_when_the_state_differs(form):
    res = form.fill({"#news": True, "#plan-free": True, "#dark": False, "#terms": True})
    assert [f.get("checked") for f in res["filled"]] == [True, True, False, True]
    assert page_log(form) == ["change:terms"]  # only the one that was off


def test_a_label_stands_for_its_field(form):
    form.fill({"text=I accept the terms": True, "text=Pro": True})
    assert values(form)["terms"] is True and values(form)["plan"] == "pro"


def test_a_field_that_appears_after_an_earlier_one_is_filled(form):
    res = form.fill({"#country": "Brazil", "#state": "SP"})
    assert res["filled"][1] == {"target": "#state", "field": 'input#state "State"', "value": "SP"}
    assert form.eval("document.getElementById('state').value") == "SP"


def test_the_value_the_field_kept_is_reported(form):
    res = form.fill({"#code": "ab12"})
    assert res["filled"][0]["value"] == "AB12"


def test_a_dialog_opened_by_a_field_is_answered(form):
    res = form.fill({"#age": "15", "#name": "Ana"})
    assert res["dialogs"] == [{"type": "alert", "message": "You must be 18 or older", "answer": None}]
    assert values(form)["name"] == "Ana"


@pytest.mark.parametrize(("fields", "error"), [
    ({"#name": "Ana", "#cv": "cv.pdf"},
     r'field 2 \(#cv\): input#cv "CV" is a file input: use upload #cv FILE; filled before it: #name$'),
    ({"#terms": "yes"}, r'field 1 \(#terms\): a checkbox takes true or false, not "yes"; nothing filled$'),
    ({"#plan-free": False}, r"field 1 \(#plan-free\): .* is checked; a radio button is unchecked by checking another"),
    ({"#ref": "R-2"}, r'field 1 \(#ref\): input#ref "Reference" is read-only'),
    ({"#name": "Ana", "#email": "a@example.com", "text=Create account": "x"},
     r"field 3 \(text=Create account\): button .* is not a form field: .*; filled before it: #name, #email$"),
    ({"#name": "Ana", "#country": "Spain"}, r'field 2 \(#country\): option not found: "Spain"; options: Choose \| Brazil'),
    ({"#nowhere": "x"}, r"field 1 \(#nowhere\): element not found: #nowhere \(waited 0.5s\); nothing filled$"),
], ids=["file", "checkbox-value", "radio-off", "read-only", "button", "option", "missing"])
def test_stops_at_the_first_field_that_fails(form, fields, error):
    with pytest.raises(WebPilotError, match=error):
        form.fill(fields, timeout=0.5)
    after = list(fields)[-1]
    if after != "#name" and "#name" in fields:
        assert values(form)["name"] == "Ana"  # the fields before it stay filled


def test_submit_sends_the_last_fields_form(form):
    res = form.fill({"#name": "Ana", "#terms": True}, submit=True, wait_text="Created Ana")
    assert res["submitted"].startswith("form#signup") and res["waited"]["found"] is True
    assert page_log(form, 2)[-1] == {"submitted": {"name": "Ana", "email": "", "password": "", "code": "", "bio": "",
                                                   "country": "", "terms": "on", "news": "on", "plan": "free",
                                                   "age": "", "ref": "R-1", "dark": "false"}}


def test_fields_in_iframes(b, site):
    b.goto(site.url(f"frames.html?port={site.other.rsplit(':', 1)[1]}"))
    snap = b.snapshot(interactive=True)["text"]
    same, cross = ref(snap, "input:text", "Same input"), ref(snap, "input:text", "Cross input")
    res = b.fill({same: "one", cross: "two"})
    assert [f["value"] for f in res["filled"]] == ["one", "two"]
    assert sorted(e for e in page_log(b, 2) if "value=" in e) == ["cross:value=two", "same:value=one"]


def test_cli_fills_pairs_and_the_log_keeps_only_lengths(form, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["webpilot", "--temp", "fill", "#name", "Ana", "#password", "s3cret!",
                                      "#terms", "true"])
    try:
        cli.run()
    except SystemExit as e:
        assert not e.code
    res = json.loads(capsys.readouterr().out)
    assert [f["target"] for f in res["filled"]] == ["#name", "#password", "#terms"]
    log = session_log.read([session_log.session_name()])[-1]
    assert log["cmd"] == "fill" and log["args"]["fields"] == [
        {"target": "#name", "value": "<3 chars>"}, {"target": "#password", "value": "<7 chars>"},
        {"target": "#terms", "value": "<4 chars>"},
    ]
    assert "s3cret" not in json.dumps(log)


def test_cli_needs_pairs(form, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["webpilot", "--temp", "fill", "#name", "Ana", "#email"])
    with pytest.raises(SystemExit) as e:
        cli.run()
    assert e.value.code == 1
    assert "fill takes pairs of TARGET VALUE; '#email' has no value" in capsys.readouterr().err
