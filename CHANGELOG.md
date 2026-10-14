# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- "Let your AI set it up" section in the README and the agent guide `docs/AI_SETUP.md`.
- Portuguese README (`README.pt-BR.md`).

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
