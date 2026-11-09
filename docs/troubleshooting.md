# WebPilot: troubleshooting

Read this when an error or a result does not say what to do next; most errors already do, so follow them first.
The core guide is [agent.md](agent.md).

| Symptom | What to do |
|---|---|
| "extension (real browser) is not connected" | The browser must be open with the extension loaded. Ask the user to check the extension's badge: `ON` connected, `OFF` daemon not running (it starts with the next command), `CFG` the user must run `webpilot setup` again, `DUP` two connected profiles share a name (rename one in the extension's popup). `webpilot status` shows what the daemon sees. Do not switch to `--temp` without asking: the user's sessions are only in the real browser. |
| "several browser profiles are connected" | Ask the user which profile to use, then pass `-p NAME` on every command. The user can set a default with `"profile"` in `~/.webpilot/config.json`. |
| "browser profile 'X' is not connected" | That profile's browser window is closed or its extension is off; the error lists the connected names. Ask the user. |
| "could not run script in this tab" / restricted page | Pages such as `chrome://`, `edge://`, the extension store and PDFs cannot be scripted. `goto` a normal page. |
| A snapshot after an action still shows "Loading..." | Add `--wait-text`/`--wait-for` with something from the next state, or `wait --text "Loading" --gone`. |
| `"busy": "dom"` or `"network"` in every result | The page never goes quiet (a clock, an animation, polling), so each action waits until the cap. Pass `--wait-text`/`--wait-for` with a marker of the next step. |
| `"changed": false` | The page did not react. Follow the result's `hint`: `--trusted`, `submit`, or another element (a parent, the label, the real input). |
| A dropdown option was clicked or chosen with keys, but nothing was chosen | Use `select <combobox ref> <text>`: one command, so the menu cannot close in between (it closes when the browser window loses focus). |
| "the browser window is minimized or covered" | Real input (`--trusted`, `type --submit`, `press`) would be lost. Ask the user to bring the browser to the front, or do without it: `click`/`type` without `--trusted`, `submit` instead of `--submit`, `select` for dropdowns. |
| `--wait-text`/`wait` timed out | The marker never appeared. Look at what the page shows instead (`snapshot`, `screenshot`): an error, a different state, a URL without its fragment. |
| `fetch`: "... is a Windows path" | Git Bash rewrote the relative URL. Prefix the command with `MSYS_NO_PATHCONV=1`, or pass the full URL. |
| Google showed "unusual traffic" | Use `search -e ddg`, or ask the user to solve the captcha in the browser. |
| Something else, unexplained | The daemon's log is `~/.webpilot/daemon.log`. Describe the problem to the user with the command and its output. |
