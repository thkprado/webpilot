# Preparing a release

The `Changelog: prepare X.Y.Z` commit. First review what is open on GitHub and report it to the user:

- pull requests: `gh pr list` (Dependabot PRs: read the release notes for breaking changes and check them against the code);
- issues: `gh issue list`;
- security alerts: `gh api 'repos/{owner}/{repo}/dependabot/alerts?state=open'`, the same with `code-scanning/alerts` and `secret-scanning/alerts`.

Check that the CI run of the last commit on main is green, `e2e` job included (`gh run list --branch main --limit 1`).

Merge or fix what belongs in the release, or list what is left open and why. Record dependency updates and security fixes in `CHANGELOG.md`. Then set the version in `pyproject.toml`, `extension/manifest.json` and `uv.lock` (`uv lock`), and turn `[Unreleased]` into the dated version section.
