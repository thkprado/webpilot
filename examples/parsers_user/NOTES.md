# Site notes

Workflows and quirks learned while browsing. Agents update this file during the reflection (`docs/reflect.md`).
Format: one `##` heading per domain, with URLs, selectors and steps that work.

## news.ycombinator.com

- Story lists: `webpilot extract` uses the `hackernews` parser (title, url, points, comments).
- Top stories with points and comments: `webpilot script hn_top` (`--help` for its arguments).
- Next page: `click "text=More"`, or go straight to `/news?p=2`.
