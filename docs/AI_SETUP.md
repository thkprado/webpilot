# Setting up WebPilot (instructions for an AI agent)

You are an AI coding agent and the user asked you to set up WebPilot on their machine. Follow these steps in order.
Run commands yourself when you can; ask the user only for what you cannot do (clicking in the browser UI) or
what changes their configuration outside this folder.

## 0. Ground rules

- WebPilot gives agents control of the user's real browser (their logged-in sessions). Tell the user this in one
  sentence before you start, and point them to the "Security and responsible use" section of `README.md`.
- Do not store, print or send `~/.webpilot/config.json`: it holds the token that controls the browser.
- Do not enable `auto_captcha`. It is opt-in and the user did not ask for it.
- Do not edit global instruction files (`~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, ...) without asking first (step 7).

## 1. Check the machine

Run these and stop with a clear message to the user if something is missing (give the install link):

| Need | Check | Install |
|---|---|---|
| Git | `git --version` | https://git-scm.com |
| Python 3.11+ | `python --version` (or `python3`) | https://www.python.org |
| uv | `uv --version` | https://docs.astral.sh/uv/getting-started/installation/ |
| Node.js 20+ and npm | `node --version`, `npm --version` | https://nodejs.org |
| Microsoft Edge or Google Chrome (120+) | ask the user which one they use | |

Detect the OS (Windows, macOS or Linux) to pick the right shell syntax and paths.

## 2. Get the code

If you are already inside a WebPilot clone, use it. Otherwise ask the user where to put it (default: `~/src/webpilot`) and run:

```bash
git clone https://github.com/thkprado/webpilot.git
cd webpilot
```

From here on, `<webpilot>` means the absolute path of that folder.

## 3. Build the extension

```bash
cd <webpilot>/extension
npm install
npm run build
```

This creates `extension/dist`. If it fails, show the user the error and stop.

## 4. Install the Python side and configure

```bash
cd <webpilot>
uv sync
uv run webpilot setup          # creates the token and extension/dist/config.json
uv tool install --editable .   # makes `webpilot` available in any folder
```

Run `webpilot setup` again after any change to `~/.webpilot/config.json`. If `uv tool install` reports that the
`uv` tools folder is not on `PATH`, run `uv tool update-shell` and tell the user to open a new terminal.

## 5. Load the extension (the user does this)

You cannot click in the browser. Give the user exactly these steps, with the absolute path of `<webpilot>/extension/dist`:

1. Open `edge://extensions` (Edge) or `chrome://extensions` (Chrome).
2. Turn on **Developer mode**.
3. Click **Load unpacked** and choose `<webpilot>/extension/dist`.
4. If they use several browser profiles, repeat in each profile.

Then ask the user to tell you when it is done. After a rebuild, the extension must be reloaded on that same page.

## 6. Verify

```bash
webpilot status
webpilot goto https://example.com -s
```

- `status` should show the daemon and the extension connected (extension badge `ON`). If the extension is not
  connected, check the badge: `OFF` means the daemon is not running (it starts with the first command), `CFG`
  means rerun `webpilot setup`, `DUP` means two profiles share a name. See the troubleshooting table in `README.md`.
- If several browser profiles are connected, **ask the user which one to use** (`webpilot profile list`), then pass `-p NAME`.
- To test without touching the user's accounts, use `webpilot --temp goto https://example.com -s`. The first
  run downloads Playwright's Chromium (one-time), so it can take a minute.

## 7. Make other agents aware of WebPilot (ask first)

Ask the user: "Do you want me to add a short WebPilot note to your agent instructions so your agents use it?"
Only if they say yes, add the snippet below to the file they choose (see the table in `README.md`, section
"Making WebPilot known to other agents"), replacing `<webpilot>` with the absolute path:

```markdown
## Browser (WebPilot)
To browse the web, read pages, search, or interact with sites, use the `webpilot` CLI.
It drives the user's real Edge (logged-in sessions) or a temporary browser (`--temp`).
Before first use in a session, read <webpilot>/README.md fully (sections 2+).
Real browser = the user's real accounts: never buy, send, delete, or change settings without asking.
```

## 8. Report

Tell the user, briefly: what was installed and where, how you verified it, the browser profile name(s) detected,
and the one-line rule for agents (never act on real accounts without asking). Mention `blocked_domains` in
`~/.webpilot/config.json` as the way to keep sites off limits, and `SECURITY.md` for the threat model.
