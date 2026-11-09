# End-to-end test pages

Static pages served by the `site` fixture in `tests/e2e/conftest.py` (on `127.0.0.1`, two ports for two
origins). One concern each, plain HTML and JS, no build step. Handlers record what happened in
`window.__log`, which tests read back with `eval` (`page_log` in `tests/helpers.py`).

- `basic.html`: buttons, links (including `javascript:`/`data:`/`vbscript:` hrefs), hidden elements, a list.
- `form.html`: text inputs (one with a value), a native `<select>`, a form whose submit is logged.
- `nav-a.html`, `nav-b.html`: two pages linking to each other, for history and navigation.
- `frames.html?port=PORT`: a same-origin iframe and a cross-origin one (`frame-child.html` from
  `127.0.0.1:PORT`, the other port). The children post what happened to the parent, which logs it.
- `frame-child.html?name=same|cross`: a button, an input and a text, labelled with the name.
- `shadow.html`: a web component with an open shadow root (button, labelled input), a nested shadow root and
  a slotted light-DOM button.
- `dynamic.html`: a target that is re-rendered or removed, text that appears and a spinner that goes away
  800 ms after a click.
- `busy.html`: a clock ticking every 100 ms, so the DOM never goes quiet.
- `input.html`: inputs, a textarea, a contenteditable and two forms; keydown, input and submit are logged.
- `long.html`: a page about 4000 px tall with a button in the middle, for scrolling and full screenshots.
- `covered.html`: a button under a fixed cookie banner (its "Accept" removes it), a custom checkbox (a
  transparent input under a drawn box) and `spin(ms)`, an overlay that goes away after `ms`, for `click --trusted`.

The server also answers `/api/echo` (the request as JSON), `/api/slow?ms=`, `/set-cookie?name=&value=` and
`/redirect?to=`, and serves `tests/pages/combobox/` under `/combobox/` (`test_combobox.py`, skipped until
that page is built). To look at a page by hand: `python -m http.server -d tests/e2e/pages`.
