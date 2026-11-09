# Agents

- **Using the browser:** read `docs/agent.md`, the guide for agents; it says when to read the other guides in `docs/` (Python API, parsers, troubleshooting).
- **"Reflect" / end of session:** follow `docs/reflect.md`.
- **Developing WebPilot itself:**
  - Python lives in `src/webpilot` (`uv run pytest -q`, `uv run ruff check`).
  - The extension lives in `extension/src` (`cd extension && npm run typecheck && npm run build`, then `uv run pytest -m e2e`). After a build, reload the extension on the browser's extensions page (`edge://extensions`, `chrome://extensions`, ...).
  - End-to-end tests (`tests/e2e/`, pages in `tests/e2e/pages/`) drive the built extension in a headless temporary browser against local pages: `uv run pytest -m e2e` after `npm run build` (`WEBPILOT_E2E_HEADED=1` to watch). Plain `uv run pytest` leaves them out. They never touch the user's browser. They run on 3 workers (~50 s; `-n 0` for one, needed with `--pdb`); a watchdog aborts the run (exit code 3, reason printed) when a test hangs, memory runs low or processes multiply; read the reason, don't just rerun.
  - Local pages for checking actions by hand live in `tests/pages/` (each has a README); `tests/pages/combobox/` covers custom dropdowns.
  - Parsers written by agents go in `parsers_user/`, with fixtures in `parsers_user/fixtures/<name>/`. That folder is local and git-ignored; `examples/parsers_user/` is the versioned example. Never commit saved pages from a logged-in browser.
- **Preparing a release** (the `Changelog: prepare X.Y.Z` commit): first review what is open on GitHub and report it to the user:
  - pull requests: `gh pr list` (Dependabot PRs: read the release notes for breaking changes and check them against the code);
  - issues: `gh issue list`;
  - security alerts: `gh api 'repos/{owner}/{repo}/dependabot/alerts?state=open'`, the same with `code-scanning/alerts` and `secret-scanning/alerts`.

  Check that the CI run of the last commit on main is green, `e2e` job included (`gh run list --branch main --limit 1`).

  Merge or fix what belongs in the release, or list what is left open and why. Record dependency updates and security fixes in `CHANGELOG.md`. Then set the version in `pyproject.toml`, `extension/manifest.json` and `uv.lock` (`uv lock`), and turn `[Unreleased]` into the dated version section.
