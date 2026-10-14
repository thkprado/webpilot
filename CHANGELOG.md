# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed
- `auto_captcha` is now off by default (opt-in with `"auto_captcha": true` in `~/.webpilot/config.json`). `webpilot captcha` still works on request.
- Extension popup and package descriptions are now in English.

### Added
- MIT license, security policy, contributing guide, issue/PR templates and CI.

## [0.1.0]

Initial version: CLI and Python API to drive the real Edge/Chrome browser (through the extension) or a temporary Chromium,
page snapshots with refs, site parsers and session reflection.
