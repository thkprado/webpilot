# Agents

- **Using the browser:** read `README.md`, which has the full reference for the `webpilot` CLI and the Python API.
- **"Reflect" / end of session:** follow `docs/reflect.md`.
- **Developing WebPilot itself:**
  - Python lives in `src/webpilot` (`uv run pytest -q`).
  - The extension lives in `extension/src` (`cd extension && npm run typecheck && npm run build`). After a build, reload the extension in `edge://extensions`.
  - Local pages for checking actions by hand live in `tests/pages/` (each has a README); `tests/pages/combobox/` covers custom dropdowns.
  - Parsers written by agents go in `parsers_user/`, with fixtures in `parsers_user/fixtures/<name>/`. That folder is local and git-ignored; `examples/parsers_user/` is the versioned example. Never commit saved pages from a logged-in browser.
