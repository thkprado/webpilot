# Combobox test page

A local page with [react-select](https://react-select.com) comboboxes, for checking by hand how
`click`, `type`, `press` and `select` behave on custom dropdowns. Not run by `pytest`.

| Field | What it covers |
|---|---|
| How can we help? | Copy of the field on https://www.npmjs.com/support: same options, `classNamePrefix="react-select"`, a default value, a hidden input `name=inquire` |
| Country (long list) | 53 options: the menu scrolls, and filtering by typing matters |
| Plan (not searchable) | `isSearchable={false}`: the input is read-only, so only the keyboard or the mouse can choose |
| Topic (portal) | Menu rendered in `document.body` (`menuPortalTarget`) with `closeMenuOnScroll` |
| Native select | A plain `<select>`, for comparison |

The page sits between two tall spacers, so every action scrolls first. `#state` shows the chosen
values; `window.__events` logs react-select's callbacks (`change`, `input` with its action,
`menu-open`, `menu-close`).

Two builds of the same app, picked by the URL:

- `/`: React 19 with `createRoot`. State updates from an event are flushed in a microtask.
- `/?react=17`: React 17 with a legacy `ReactDOM.render` root, like www.npmjs.com. Updates are flushed
  before the event returns, so a `focusout` in the middle of a synthetic click already removes the
  menu. **Use this build to reproduce what happens on npm.**

## Run

```bash
cd tests/pages/combobox
npm install && npm run build                     # bundle.js and bundle17.js (git-ignored)
uv run python -m http.server 8777 --bind 127.0.0.1 -d .
```

Then, from the repository root:

```bash
webpilot --temp goto "http://127.0.0.1:8777/?react=17" -s
uv run python tests/pages/combobox/repro.py --url "http://127.0.0.1:8777/?react=17"   # every scenario
uv run python tests/pages/combobox/repro.py -k option                                # some of them
```

`repro.py` reloads the page before each scenario and prints, for each step, the WebPilot result
(`changed`, errors), the chosen values, whether the menu is open, the page's focus and visibility,
the react-select callbacks and the DOM events the page received (`:synthetic` marks untrusted ones).

## Window state matters

Run with the browser window **visible**. Results change with the window state:

- **Hidden** (minimized, or completely covered by other windows: Chromium on Windows treats a
  covered window as hidden): trusted input (`--trusted`, `press`, `type --submit`) is dropped and
  never reaches the page. Synthetic events still work.
- **Visible but not focused** (the usual case, with the terminal in front): `element.focus()` from
  the page fires no `focus`/`focusin`, so a synthetic click on the combobox input does not open the
  menu. Once the debugger is attached (any trusted action or `eval`), the page counts as focused.
- If the window loses focus while a menu is open, the input blurs and react-select closes the menu.
- While the debugger is attached (for about 20 s after a trusted action or `eval`), a minimized
  window still reports `document.visibilityState === "visible"`. `repro.py` reads the page with
  `eval`, so its `visibility` column says `visible` even when minimized. To test a hidden window,
  log `visibilitychange` from the page, wait 20 s for the debugger to detach, minimize, run the
  commands, then read the log.

The temporary browser starts with Chromium's occlusion detection off
(`--disable-features=CalculateNativeWinOcclusion --disable-backgrounding-occluded-windows
--disable-renderer-backgrounding`), so it stays visible while covered; only minimizing hides it.
Trusted input (`--trusted`, `type --submit`, `press`) fails with an error when the window is minimized
(or, in the real browser, covered), instead of being dropped. A background tab of a visible window
does get trusted input, although its page reports `hidden`.
