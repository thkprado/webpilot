# Contributing

Thanks for your interest in WebPilot! Issues and pull requests are welcome.

## Setup

```bash
uv sync                                   # Python dependencies
cd extension && npm install && cd ..      # extension dependencies
```

See the [README](README.md#1-setup-once-by-the-user) for building and loading the extension.

## Before opening a pull request

```bash
uv run pytest -q                                      # Python tests
uv run ruff check                                     # Python lint
cd extension && npm run typecheck && npm run build    # extension
```

CI runs the same checks. After rebuilding the extension, reload it in `edge://extensions` (or `chrome://extensions`).

### End-to-end tests

`tests/e2e/` drives the built extension in a headless temporary browser (Playwright's Chromium, installed on
first use) against local pages on `127.0.0.1`. They are left out of `uv run pytest` and run on their own:

```bash
cd extension && npm run build && cd ..   # the tests load extension/dist (skipped when it is missing)
cd tests/pages/combobox && npm ci && npm run build && cd ../../..  # react-select page (test_combobox.py skips without it)
uv run pytest -m e2e                     # WEBPILOT_E2E_HEADED=1 shows the browser, for debugging
```

They use a throwaway config and their own daemon on a free port, so your browser and its extension are never
touched. On a failure, the test's report lists a screenshot and copies of the daemon and session logs. Pages
live in `tests/e2e/pages/` (see its README); run these tests after any change to `extension/src`. CI runs them
too (job `e2e`, with the failure screenshots and logs as an artifact).

`-m e2e` runs on 3 pytest-xdist workers, each with its own daemon and headless browser: ~50 s on a
16-thread Windows machine (~130 s on one worker: `-n 0`). The slowest tests wait on the extension's own caps
(a page that never goes quiet takes 10 s), not on sleeps. Use `-n 0` with `--pdb` or `-s`.

A watchdog (`tests/e2e_watchdog.py`) aborts the run, killing its browsers and workers (exit code 3, reason in
`<basetemp>/watchdog.txt`), when a test runs over 90 s, the run over 300 s, free memory falls under 15%, or
more python processes descend from the run than its workers need. Override the limits with
`WEBPILOT_E2E_TEST_LIMIT`, `WEBPILOT_E2E_RUN_LIMIT` (seconds) and `WEBPILOT_E2E_MIN_FREE` (fraction).

## Guidelines

- Keep changes focused; one topic per pull request.
- Write code, comments, commit messages and docs in English.
- Add or update tests when you change behavior. Parsers need a fixture in `tests/fixtures/<name>/`.
- Local pages for checking actions by hand live in `tests/pages/` (each has a README); pages for the end-to-end
  tests live in `tests/e2e/pages/`.
- **Never commit saved pages, cookies, tokens, HAR files or screenshots from a logged-in browser.** Check fixtures for
  personal data (names, emails, addresses, IP-based location) before committing them.
- `parsers_user/` is local and git-ignored; `examples/parsers_user/` is the versioned example.

## Code of conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). By participating you agree to abide by it.

## Security

Do not report vulnerabilities in public issues. See [SECURITY.md](SECURITY.md).

## License

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE).
