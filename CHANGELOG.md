# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed
- `click --trusted` no longer clicks whatever covers the target. A real click lands on the topmost element at the target's center, so a cookie banner or a modal on top got the click and the result read as a normal click. Now an overlay that goes away within `--timeout` (a spinner, a toast) is waited for, and one that stays is an error naming it, e.g. `e12 (button "Buy") is covered by div.cookie-banner "We use cookies. Accept": close that first (click its button), or click without --trusted`. This includes an overlay in the parent page over an iframe the target is in. Clicks without `--trusted` are unchanged. Reload the extension after updating.

### Fixed
- On Windows, a command no longer waits 2 s or more when the daemon is not running yet: `webpilot status` with the daemon stopped answered in about 2.3 s, the first command after a restart (or after `webpilot stop`) took about 3 s to start the daemon and connect; now about 0.3 s and 1 s. A second daemon started while one already listens (two commands at once) exits with one line in `daemon.log` instead of a traceback.

## [0.1.13] - 2026-11-08

### Fixed
- `back` and `forward` failed with "Cannot find a next page in history" when the pages involved never had a user gesture, which is the case for pages an agent opened with `goto` or clicked into without `--trusted`: Chromium's history intervention skips such entries. They now step to the adjacent history entry, like `history.back()` from the page, and say so clearly when there is none. Reload the extension after updating.
- Elements inside open shadow roots (web components) showed up in the snapshot with a ref, but `click`, `type`, `select` and `scroll` on that ref failed with "is gone; take a new snapshot". Refs, `text=` targets and CSS selectors now reach into open shadow roots (a selector is tried on the page first), and so does `wait --selector`; fields inside a shadow root get their name from a `<label for>` in that same root. Reload the extension after updating.

### Changed
- Error messages say what to do next, so agents no longer need the troubleshooting table: a ref that is gone or not found (run `snapshot -i` again; for a dropdown option whose menu closed, use `select`), "not a combobox" and "no list of options opened", a page no extension may script (`chrome://`, the extension store, a PDF: go to a normal page; Chrome's own "Cannot access" errors now say so too), a tab showing the browser's error page, the extension not connected (check the badge, ask the user to open the browser), several profiles connected (ask the user which one, never pick one), a profile not connected, and a minimized window (`submit` instead of `type --submit`). `click` and `submit` results with `"changed": false` carry a `hint` with what to try instead. `eval` of a bare function without arguments (`"() => ..."`) is now an error that says how to call it, instead of returning `{}`. Reload the extension after updating.
- The guide for agents moved out of the README into `docs/agent.md`, about a third of what agents read before: commands, workflow and rules (the safety rules unchanged), with a "Read when" list pointing at the rest, read only when needed: `docs/python-api.md` (Python API and site APIs with the session), `docs/parsers.md` (parsers, site notes, scripts) and `docs/troubleshooting.md`. The README is now for people. Run `webpilot skill install` again (`webpilot skill list` shows `outdated` until then), and in instruction snippets you pasted yourself replace `read <webpilot>/README.md fully (sections 2+)` with `read <webpilot>/docs/agent.md fully`. The README's first lines point agents at the guide, so old snippets still get there.
- For contributors: end-to-end tests of the extension in `tests/e2e/` (headless temporary browser, local pages), run with `uv run pytest -m e2e`; plain `uv run pytest` leaves them out. They cover iframes, shadow DOM, waits, keys, forms, the react-select page of `tests/pages/combobox`, `eval`, `fetch`, screenshots, `blocked_domains` and the CLI's exit codes. They run on 3 parallel workers (~50 s), in CI too (job `e2e`), under a watchdog that stops a run that hangs or eats memory. pytest-xdist is a new development dependency. See CONTRIBUTING.

## [0.1.12] - 2026-11-06

### Changed
- Locked dependencies updated: websockets 17.4 (limits empty message fragments, which could exhaust the memory of the local server), plus pytest 9.2.0, ruff 0.17.3 and `@types/chrome` 0.3.7 for development.

## [0.1.11] - 2026-11-06

### Fixed
- `webpilot wait` exits with code 1 when the text or selector does not appear (or, with `--gone`, does not disappear) within `--timeout`, like `--wait-text`/`--wait-for` on actions; the JSON result (`found: false`) is still printed. Before, it exited 0, and an agent went on as if it had appeared. The Python API is unchanged: `Browser.wait()` returns `{"found", "ms"}`, now documented in the README.
- The session log marks waits that timed out (`wait_missed`), from `wait` or from an action's `--wait-text`/`--wait-for`, and `reflect-data` reports them as "timed out" with what to check, instead of as a "Slow `wait`".

## [0.1.10] - 2026-10-30

### Changed
- Locked dependencies updated: playwright 1.64.1 (its bundled Node.js 24.22.1 distrusts the compromised eMudhra intermediate CAs), selectolax 1.0.2 and websockets 17.3, plus ruff 0.17.2 and `@types/chrome` 0.3.6 for development.

## [0.1.9] - 2026-10-23

### Added
- `webpilot script` with no name lists each script with the first line of its docstring, grouped by folder, marks the ones shadowed by a script of the same name in an earlier folder, and then lists the site notes (`NOTES.md`) found. Files that cannot be read or have a syntax error are reported on stderr with exit code 1; files starting with `_` are helpers and are not listed. With no scripts at all, it says where it searched and how to start from the example.

### Changed
- The `webpilot` skill and the instructions snippet tell agents to check the site notes and `webpilot script` before a flow on a site used before. README §2 has copyable `webpilot script` examples, says that brackets in the syntax lines mark optional parts, and starts the recommended workflow with the notes and scripts (notes are context, never permission to act). README §3 describes scripts and the lookup order shared by parsers, scripts and notes. Run `webpilot skill install` again to update an installed skill (`webpilot skill list` shows it `outdated`).
- `docs/reflect.md` says when to write a parser, a script or notes, to mark guesses in the notes as `hypothesis:`, and how to validate a new script (`--help`, errors, a representative run); parser tests do not validate a script.
- The example `hn_top` script documents its arguments with copyable lines and argparse help, and its note points at it.

### Fixed
- `webpilot script` now looks in `WEBPILOT_PARSERS_DIR/scripts` before `parsers_user/scripts`, the same order as parsers, and warns when `WEBPILOT_PARSERS_DIR` is not a folder.
- `webpilot script NAME --help` (or `-h`) shows the script's own help: everything after the name goes to the script. The script's exit code is the command's (argparse: `--help` 0, a bad argument 2), its folder is first on `sys.path` so it can import a sibling `_helper.py`, and "script not found" lists the folders searched.

## [0.1.8] - 2026-10-23

### Added
- The `reflect` skill for this project in Antigravity (`.agents/skills/reflect`) and GitHub Copilot CLI (`.github/skills/reflect`), alongside the `/reflect` command in Claude Code. It follows `docs/reflect.md`.

## [0.1.7] - 2026-10-23

### Added
- `eval --out FILE` (`-o`) writes the result to a file instead of stdout: a base64 data URL (such as a canvas's `toDataURL()`) is decoded to its bytes, any other string is written as text, and other values as JSON. It prints `{"saved", "bytes", "type"}` (`type` only for data URLs), and, like `html --out`, `reflect-data` does not count the saved result as a read.
- The session log notes the type of an `eval` result that is a data URL (`data_url: image/png`, never the content), from the CLI and the Python API, and `reflect-data` gives large ones their own suggestion: write them with `eval --out FILE` instead of keeping them from stdout.

### Fixed
- `reflect-data` attributes `eval` results, which carry no URL, to the last page visited in the same session, instead of reporting them "on :" with an empty domain.

## [0.1.6] - 2026-10-22

### Changed
- Locked dependencies updated: playwright 1.64.0, selectolax 1.0.1, and ruff 0.17.1 for development.

## [0.1.5] - 2026-10-14

### Added
- `update.bat` (Windows) and `update.sh`: update a clone in one step. They stop the daemon, run `git pull --ff-only`, rebuild the extension (`npm ci` + `npm run build`), run `uv sync`, and reinstall the `webpilot` command when it was installed with `uv tool install`. `--no-pull` only rebuilds, after changing the code yourself. A `.gitattributes` keeps each launcher's line endings in every clone.

## [0.1.4] - 2026-10-14

### Added
- `webpilot skill list | install | uninstall`: installs the `webpilot` Agent Skill for Claude Code, Codex CLI, Antigravity (IDE and agy CLI), pi and GitHub Copilot CLI, globally or per project (`--project`). Pick harnesses by name, with `--all`, or answer a prompt for each; uninstall only removes skills the command wrote.

## [0.1.3] - 2026-10-14

### Changed
- Locked dependencies updated: selectolax 1.0.0, typer 0.27.3, websockets 17.2, and `@types/chrome` 0.3.5 for the extension.
- CI also runs the tests against the lowest versions `pyproject.toml` allows.

### Fixed
- The declared minimum versions of `typer` and `websockets` were too old to work: `websockets` below 15.0 lacks the sync client's `ping_interval`, and `typer` below 0.15.4 breaks with Click 8.2+. They are now `typer>=0.15.4` and `websockets>=15.0`; Dependabot only updates `uv.lock`, so routine bumps no longer raise these floors.

## [0.1.2] - 2026-10-14

### Added
- The AI setup guide (`docs/AI_SETUP.md`) offers to make WebPilot known to agents as an Agent Skill (Claude Code, Codex) or as a note in their instructions, globally or per project, and asks before writing either.

### Changed
- Docs, CLI messages and the package description name any Chromium-based browser (Chrome, Edge, Brave, Vivaldi, Opera, ...) instead of only Edge. The extension itself is unchanged.

## [0.1.1] - 2026-10-14

### Added
- "Let your AI set it up" section in the README and the agent guide `docs/AI_SETUP.md`.
- Portuguese README (`README.pt-BR.md`).

### Security
- `blocked_domains` could be bypassed with a trailing dot (`https://bank.example.com./`), and entries with capitals, `*.` or a scheme never matched. Hosts and entries are now normalized before comparing.
- On Linux/macOS, `~/.webpilot` and the files holding the daemon token (`config.json`, the extension's `config.json`) are now owner-only (0700/0600); existing installs are tightened on the next run.
- The session log records the host only, never `user:password@` or the port of a URL.
- Snapshots leave out `data:` and `vbscript:` link targets as well as `javascript:`; the Google parser skips Google links by exact hostname.

### Fixed
- The daemon answers a malformed request with an error instead of dropping the connection, and ignores malformed messages from the extension.

### Changed
- CI lints with ruff and tests Python 3.11 and 3.14; Dependabot also covers the extension's npm packages and `uv.lock`.

## [0.1.0] - 2026-10-14

First public release.

### Added
- CLI (`webpilot`) and Python API (`Browser`) to drive the real Edge/Chrome browser through the WebPilot extension, or a temporary Chromium (`--temp`).
- Page snapshots with refs, clicks, typing, custom dropdowns (`select`), iframes, `fetch` with the tab's session, screenshots.
- Site parsers (`extract`), with a Hacker News example in `examples/parsers_user/`.
- Session log and `reflect-data` for end-of-session reflection.
- Safety: daemon bound to `127.0.0.1` with a token, `blocked_domains`, write protection in `fetch`.
- MIT license, security policy, code of conduct, contributing guide, issue/PR templates, CI and Dependabot.

### Changed
- `auto_captcha` is off by default (opt-in with `"auto_captcha": true` in `~/.webpilot/config.json`). `webpilot captcha` still works on request.
- Extension popup and package descriptions are in English.
