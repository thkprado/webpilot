"""Runs WebPilot's click/type/press against the react-select test page and reports what the page saw.

Serve the page first (see README.md), then:
    uv run python tests/pages/combobox/repro.py            # temporary browser
    uv run python tests/pages/combobox/repro.py --real     # the real browser (a new tab)
    uv run python tests/pages/combobox/repro.py -k option  # only scenarios whose name contains "option"
"""

import argparse
import json

from webpilot import Browser, WebPilotError

URL = "http://127.0.0.1:8777/"

# DOM events seen by the page (capture phase), next to the react-select callbacks in __events.
SPY = """() => {
  window.__dom = [];
  const name = (t) => t === document ? "document" : t.id || (t.getAttribute?.("role") ?? "") || t.localName;
  for (const t of ["pointerdown", "mousedown", "mouseup", "click", "focusin", "focusout", "keydown"]) {
    document.addEventListener(t, (e) => __dom.push(`${t}:${name(e.target)}${e.isTrusted ? "" : ":synthetic"}${t === "keydown" ? ":" + e.key : ""}`), true);
  }
  document.addEventListener("scroll", (e) => __dom.push(`scroll:${name(e.target)}`), true);
  return true;
}"""
PROBE = """() => ({
  state: JSON.parse(document.getElementById("state").textContent),
  menu: !!document.querySelector(".react-select__menu"),
  focus: document.hasFocus(), visibility: document.visibilityState,
  active: document.activeElement?.id || document.activeElement?.localName,
  events: __events.splice(0).map((e) => `${e.field}:${e.what}${e.value !== undefined ? "=" + JSON.stringify(e.value) : ""}${e.action ? "(" + e.action + ")" : ""}`),
  dom: __dom.splice(0),
})"""


# Choosing with synthetic events only: filter through the input's native value setter, then keydown
# ArrowDown/Enter on the input. Works with the window hidden or unfocused, where trusted input is dropped.
SYNTHETIC_KEYS = """(id, text, downs) => new Promise((done) => {
  const i = document.getElementById(id);
  const key = (k) => i.dispatchEvent(new KeyboardEvent("keydown", { key: k, bubbles: true, cancelable: true }));
  i.focus();
  if (text) {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(i, text);
    i.dispatchEvent(new Event("input", { bubbles: true }));
  }
  setTimeout(() => {
    for (let n = 0; n < downs; n++) key("ArrowDown");
    setTimeout(() => { key("Enter"); setTimeout(() => done(true), 100); }, 100);
  }, 100);
})"""


def opt(field: str, i: int) -> str:
    return f"#react-select-{field}-option-{i}"


def fresh(b: Browser) -> None:
    b.goto(URL)
    b.wait(selector="#state")
    b.eval(SPY, args=[])


def act(b: Browser, label: str, fn) -> dict:
    try:
        r = fn()
        res = {k: r[k] for k in ("changed", "busy", "reresolved", "selected", "option", "value") if k in r}
    except WebPilotError as e:
        res = {"error": str(e)}
    return {"step": label, **res, **b.eval(PROBE, args=[])}


def sel(b, target, text):
    return act(b, f'select {target} "{text}"', lambda: b.select(target, text))


def open_trusted(b, field):
    return act(b, f"click --trusted #field-{field}", lambda: b.click(f"#field-{field}", trusted=True))


SCENARIOS = {
    "click-input": lambda b: [act(b, "click #field-inquire", lambda: b.click("#field-inquire"))],
    "trusted-click-input": lambda b: [open_trusted(b, "inquire")],
    "click-option": lambda b: [
        open_trusted(b, "inquire"),
        act(b, "click option 3", lambda: b.click(opt("inquire", 3))),
    ],
    "trusted-click-option": lambda b: [
        open_trusted(b, "inquire"),
        act(b, "click --trusted option 3", lambda: b.click(opt("inquire", 3), trusted=True)),
    ],
    "trusted-click-option-portal": lambda b: [
        open_trusted(b, "topic"),
        act(b, "click --trusted topic option 3", lambda: b.click(opt("topic", 3), trusted=True)),
    ],
    "trusted-click-option-long-list": lambda b: [
        open_trusted(b, "country"),
        act(b, "click --trusted country option 40 (Peru)", lambda: b.click(opt("country", 40), trusted=True)),
    ],
    "type-enter": lambda b: [
        act(b, 'type #field-inquire "billing"', lambda: b.type("#field-inquire", "billing")),
        act(b, "press Enter", lambda: b.press("Enter")),
    ],
    "trusted-type-enter": lambda b: [
        act(b, 'type --trusted #field-inquire "billing"', lambda: b.type("#field-inquire", "billing", trusted=True)),
        act(b, "press Enter", lambda: b.press("Enter")),
    ],
    "synthetic-keys-filter": lambda b: [
        act(b, 'synthetic: filter "Peru", Enter', lambda: b.eval(SYNTHETIC_KEYS, args=["field-country", "Peru", 0]) and {}),
    ],
    "synthetic-keys-not-searchable": lambda b: [
        act(b, "synthetic: ArrowDown x3, Enter", lambda: b.eval(SYNTHETIC_KEYS, args=["field-plan", "", 3]) and {}),
    ],
    # `select`: the whole choice in one command, with synthetic events (works with the window hidden).
    "select-inquire": lambda b: [sel(b, "#field-inquire", "billing")],
    "select-country": lambda b: [sel(b, "#field-country", "Peru")],
    "select-plan": lambda b: [sel(b, "#field-plan", "Teams")],
    "select-plan-wrapper": lambda b: [sel(b, "#field-plan-label + div", "enterprise")],
    "select-topic": lambda b: [sel(b, "#field-topic", "Security")],
    "select-native": lambda b: [sel(b, "#native", "Pro")],
    "select-not-found": lambda b: [sel(b, "#field-plan", "Gold")],
    "keyboard": lambda b: [
        open_trusted(b, "inquire"),
        *[act(b, "press ArrowDown", lambda: b.press("ArrowDown")) for _ in range(3)],
        act(b, "press Enter", lambda: b.press("Enter")),
    ],
}


def main() -> None:
    global URL
    ap = argparse.ArgumentParser()
    ap.add_argument("--real", action="store_true", help="use the real browser instead of the temporary one")
    ap.add_argument("-k", default="", help="only scenarios whose name contains this")
    ap.add_argument("--url", default=URL)
    a = ap.parse_args()
    URL = a.url
    with Browser("real" if a.real else "temp") as b:
        if a.real:
            b.new_tab()
        for name, run in SCENARIOS.items():
            if a.k not in name:
                continue
            fresh(b)
            print(f"== {name}")
            for step in run(b):
                print(json.dumps(step, ensure_ascii=False))


if __name__ == "__main__":
    main()
