# End-to-end test pages

Static pages served by the `site` fixture in `tests/e2e/conftest.py` (on `127.0.0.1`, two ports for two
origins). One concern each, plain HTML and JS, no build step. Handlers record what happened in
`window.__log`, which tests read back with `eval`.

- `basic.html`: buttons, links (including `javascript:`/`data:`/`vbscript:` hrefs), hidden elements, a list.
- `form.html`: text inputs (one with a value), a native `<select>`, a form whose submit is logged.
- `nav-a.html`, `nav-b.html`: two pages linking to each other, for history and navigation.

The server also answers `/api/echo` (the request as JSON), `/api/slow?ms=`, `/set-cookie?name=&value=` and
`/redirect?to=`. To look at a page by hand: `python -m http.server -d tests/e2e/pages`.
