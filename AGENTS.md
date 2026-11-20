# Agents

- **Using the browser:** read `docs/agent.md` fully, the guide for agents; it says when to read the other guides in `docs/` (Python API, parsers, troubleshooting).
- **"Reflect" / end of session:** follow `docs/reflect.md`.
- **Developing WebPilot itself:**
  - Python lives in `src/webpilot` (`uv run pytest -q`, `uv run ruff check`).
  - The extension lives in `extension/src` (`cd extension && npm run typecheck && npm run build`, then `uv run pytest -m e2e`). After a build, reload the extension on the browser's extensions page (`edge://extensions`, `chrome://extensions`, ...).
  - End-to-end tests (`tests/e2e/`, pages in `tests/e2e/pages/`) drive the built extension in a headless temporary browser against local pages: `uv run pytest -m e2e` after `npm run build` (`WEBPILOT_E2E_HEADED=1` to watch). Plain `uv run pytest` leaves them out. They never touch the user's browser. They run on 3 workers (~50 s; `-n 0` for one, needed with `--pdb`); a watchdog aborts the run (exit code 3, reason printed) when a test hangs, memory runs low or processes multiply; read the reason, don't just rerun.
  - `docs/agent.md` is read whole by every agent session: a new command gets one short quick-reference line, and a new rule only for safety. Details go to `docs/python-api.md`, and what to do after a failure goes into the error message itself. `tests/test_docs.py` caps its size; raise the cap only on purpose, and say why in the commit.
  - `CHANGELOG.md` entries (under `[Unreleased]`) start with one bold sentence saying what changed for the user, then the details: what happened before, the exact new messages, "Reload the extension after updating" when the extension changed.
  - Local pages for checking actions by hand live in `tests/pages/` (each has a README); `tests/pages/combobox/` covers custom dropdowns.
  - Parsers written by agents go in `parsers_user/`, with fixtures in `parsers_user/fixtures/<name>/`. That folder is local and git-ignored; `examples/parsers_user/` is the versioned example. Never commit saved pages from a logged-in browser.
- **Preparing a release** (the `Changelog: prepare X.Y.Z` commit): follow `docs/release.md`.
