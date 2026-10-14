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

## Guidelines

- Keep changes focused; one topic per pull request.
- Write code, comments, commit messages and docs in English.
- Add or update tests when you change behavior. Parsers need a fixture in `tests/fixtures/<name>/`.
- Local pages for checking actions by hand live in `tests/pages/` (each has a README).
- **Never commit saved pages, cookies, tokens, HAR files or screenshots from a logged-in browser.** Check fixtures for
  personal data (names, emails, addresses, IP-based location) before committing them.
- `parsers_user/` is local and git-ignored; `examples/parsers_user/` is the versioned example.

## Code of conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). By participating you agree to abide by it.

## Security

Do not report vulnerabilities in public issues. See [SECURITY.md](SECURITY.md).

## License

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE).
