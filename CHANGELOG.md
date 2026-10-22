# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

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
