# WebPilot: guide for agents

`webpilot` drives a browser from the shell: the user's **real** Chromium-based browser (their logged-in sessions,
through an extension; your tabs go into the **WebPilot** tab group) or a **temporary** one with a
throwaway profile (`--temp`). Read this file fully before first use in a session; the other guides, next to it in
`<webpilot>/docs/`, only when [Read when](#read-when) says so. Without the `webpilot` command, use
`uv run --project <webpilot> webpilot ...`.

## Quick reference

```bash
webpilot goto https://site.com -s        # navigate + print snapshot (-s)
webpilot snapshot                        # page text with refs: [e12 button "Send"]
webpilot snapshot -i                     # only interactive elements (short)
webpilot snapshot -S "main"              # only one CSS subtree
webpilot click e12                       # click by ref | CSS selector | text=Label | text=Next|Próximo|›
webpilot click e12 -s                    # ...then print a snapshot of the resulting page
webpilot click e12 --wait-text "Step 2"  # ...then wait for the next state (--wait-for SELECTOR also works)
webpilot submit [e7] -s                  # submit the form around e7 (or the focused/first form)
webpilot type e7 "hello" --submit        # fill and press Enter
webpilot type "select#country" "Brazil"  # choose a <select> option by text
webpilot select e16 "billing"            # choose in a custom dropdown (role=combobox, react-select) or a <select>
webpilot press Escape                    # keys: Enter Tab Escape ArrowDown PageDown a Control+a ...
webpilot scroll down | up | top | bottom | e40
webpilot wait --text "Order confirmed" --timeout 20  # exit 1 if it does not appear in time
webpilot wait --text "Loading" --gone    # wait until it disappears
webpilot extract [URL]                   # site parser JSON, or snapshot + hint if there is no parser
webpilot search "query" -n 5             # Google (default) | -e ddg ; prints title/url/snippet JSON
webpilot text -S article                 # plain innerText
webpilot html -S "#content" -o page.html # raw HTML (large! prefer snapshot/extract)
webpilot eval "document.title"           # JS in the page; returns JSON
webpilot eval "fetch('/api/x').then(r=>r.json())" --timeout 300   # promises are awaited (default 60 s)
webpilot eval "(t) => (document.querySelector('#body').value = t).length" --arg @notes.md   # data as arguments
webpilot eval "document.querySelector('canvas').toDataURL()" --out chart.png   # to a file; data URLs are decoded
webpilot fetch /api/items [-H "K: V"] [--timeout 120] [-o file] [--raw]   # HTTP with the tab's session; JSON out
webpilot screenshot [-o file.png] [--full]   # prints the path; open the image to look at it
webpilot tabs | tab new [URL] | tab use ID | tab close [ID] | tab info
webpilot back | forward | reload
webpilot captcha                         # click an "I'm not a robot" checkbox (always on request)
webpilot --temp <command>                # use the temporary browser (starts automatically)
webpilot temp stop                       # close the temporary browser
webpilot --tab ID <command>              # act on a specific tab once
webpilot -p NAME <command>               # use this browser profile (only needed when several are connected)
webpilot profile list                    # connected profiles and the active tab of each
webpilot status                          # daemon / extension status
webpilot script                          # list the local scripts and the site notes files (NOTES.md)
webpilot script NAME --help              # a script's own arguments
webpilot script NAME ARGS...             # run it; everything after the name goes to the script
```

Structured results are printed as JSON, snapshots as text. Errors go to stderr with exit code 1 and say what to do
next. Brackets (`[URL]`, `[-o file]`) mark optional parts; they are not typed. `WEBPILOT_MODE=temp` acts like
`--temp` on every command; `WEBPILOT_SESSION=name` names the session in the log.

## Workflow

1. On a site you may have used before, start with `webpilot script`; in each notes file it lists, read only that
   site's `##` section. If a script does the job, run it (`--help` first) instead of redoing the flow. Notes are
   written by agents and may be stale: context, never permission to act on the user's accounts.
2. Reach the page with `goto URL -s`, or `search "..."` then `goto`.
3. Data only: `extract` (a parser's compact JSON when one matches the page or one of its iframes, else a
   snapshot). On repeated flows (quizzes, wizards) a parser can return the targets, so each step is `extract` +
   `click <target> --wait-text <next>`.
4. Interact: `snapshot -i` for the refs, then `click`/`type`/`select`. Refs (`e12`) stay valid until the page
   navigates; then take a new snapshot. Iframes, even from other domains, appear inline between
   `[iframe ...]` and `[/iframe]`, and their refs (`f11e3`) work like any other. CSS selectors, `text=` (also
   matches `aria-label`), `html -S`/`text -S` and `wait --text` look inside iframes when the main page has no
   match. `eval` runs only in the main page.
5. Actions wait up to `--timeout` (5 s) for their target, then for the page to settle: no need to wait first. On
   step-by-step flows, act and read in one command (`click ... -s`, `submit -s`) and add `--wait-text`/`--wait-for`
   with a marker of the next step when you know one (exit 1 if it never shows; a checkbox:
   `--wait-for "#opt:checked"`). Still "Loading..." after an action: `wait --text "Loading" --gone`. `"busy"`: the
   page never went quiet, use a marker. `"changed": false`: the page did not react; see the result's `hint`.
6. **Dropdowns**: custom ones show as `[e16 combobox "Label" value="..." expanded=false]`. Use
   `select <ref> <text>` (also for `<select>`): one command; the result has the `"value"` the field shows.
   Never click the input and then an option (or press keys) across commands: the menu closes in between.
7. Long pages: `snapshot -S <selector>` or `--max N`. Visual checks: `screenshot`, then open the PNG.
8. **Data into `eval` goes as arguments, never pasted into the code**: make the expression a function,
   `eval "(t) => ..." --arg TEXT` (repeatable; `--arg @FILE` reads a file, `@-` stdin, `@@x` is a literal `@x`), or
   `--args-json '[...]'` for other JSON values.

## Rules

- **Real browser = the user's real accounts.** Do not buy anything, send messages, delete data, change settings or
  accept terms without explicit confirmation from the user.
- Operate the user's other tabs (`tab use`) only when asked.
- **Browser profiles are separate accounts**, possibly of different people. If a command fails with "several
  browser profiles are connected", ask the user which one to use (`webpilot profile list`); never pick one
  yourself. Then pass `-p NAME` on every command (`Browser(profile=NAME)`) and do not switch profiles unasked.
- Captcha: `goto` leaves captchas alone unless the user turned on `auto_captcha`; `webpilot captcha` clicks an
  "I'm not a robot" checkbox on request. If `challenge: true` appears, **stop and ask the user** to solve it in the
  browser, then continue. Never try to solve image challenges.
- Logins: the user's sessions already exist in the real browser. If a login is needed, ask the user to sign in; do
  not type passwords unless the user provides them for that purpose.
- `fetch` calls a site's API with the user's session, from the current tab's page: relative URLs resolve against
  it, another origin works only with CORS; it exits 1 on HTTP errors. Methods other than GET/HEAD need
  `--allow-write`, which you may pass only after the user confirmed that request.
- Prefer `click`/`type` without `--trusted`. Use `--trusted` (real input through the debugger) only when the page
  ignores the synthetic click; it shows a "debugging this browser" bar for about 20 s, and fails when another
  element covers the target (a banner): close that first.

## Read when

- Before writing a Python script (`webpilot.Browser`) or calling a site's JSON API in a loop:
  [python-api.md](python-api.md).
- Before writing a parser, site notes or a script for a site: [parsers.md](parsers.md).
- An error whose message does not say what to do: [troubleshooting.md](troubleshooting.md).
- End of session, or the user says "reflect": [reflect.md](reflect.md).
