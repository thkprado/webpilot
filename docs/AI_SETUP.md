# Setting up WebPilot (instructions for an AI agent)

You are an AI coding agent and the user asked you to set up WebPilot on their machine. Follow these steps in order.
Run commands yourself when you can; ask the user only for what you cannot do (clicking in the browser UI) or
what changes their configuration outside this folder.

## 0. Ground rules

- WebPilot gives agents control of the user's real browser (their logged-in sessions). Tell the user this in one
  sentence before you start, and point them to the "Security and responsible use" section of `README.md`.
- Do not store, print or send `~/.webpilot/config.json`: it holds the token that controls the browser.
- Do not enable `auto_captcha`. It is opt-in and the user did not ask for it.
- Do not edit global instruction files (`~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, ...) or skills folders
  (`~/.claude/skills/`, ...) without asking first (step 7).

## 1. Check the machine

Run these and stop with a clear message to the user if something is missing (give the install link):

| Need | Check | Install |
|---|---|---|
| Git | `git --version` | https://git-scm.com |
| Python 3.11+ | `python --version` (or `python3`) | https://www.python.org |
| uv | `uv --version` | https://docs.astral.sh/uv/getting-started/installation/ |
| Node.js 20+ and npm | `node --version`, `npm --version` | https://nodejs.org |
| A Chromium-based browser, 120+ (Chrome, Edge, Brave, Vivaldi, Opera, ...); Firefox and Safari are not supported | ask the user which one they use | |

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

1. Open the browser's extensions page: `chrome://extensions` (Chrome, Brave, Vivaldi and most others),
   `edge://extensions` (Edge) or `opera://extensions` (Opera).
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

Agents only use WebPilot if something tells them about it. Find out which harness the user runs (you are probably
one of them; they may use several), then ask:

"How should your agents learn about WebPilot?
1. **Skill** (recommended where supported): loads only when a task needs the browser.
2. **Note in your agent instructions**: always in context, works in any harness.
3. **Nothing for now.**"

Offer option 1 only for harnesses that support Agent Skills. Also ask whether it should be global (all projects,
the default) or for one project only. Only after they choose, write the file, replacing `<webpilot>` with the absolute
path (forward slashes are fine on Windows). If a file already exists there, show it and ask before replacing it.

**Option 1: skill.** Run `webpilot skill list` to see the supported harnesses and which are on this machine, then
install for the ones the user chose (names: `claude`, `codex`, `antigravity` or `agy`, `pi`, `copilot`):

```bash
webpilot skill install claude pi            # global; add --project to use the current project's skills folder
```

It writes `webpilot/SKILL.md` pointing at `<webpilot>/README.md` and refuses to replace a webpilot skill it did not
write (if it reports one, show it to the user and ask before rerunning with `--force`). `webpilot skill uninstall NAME`
removes it again. For a harness with Agent Skills that is not in that list, copy `src/webpilot/SKILL.md` into its
skills folder as `webpilot/SKILL.md`, replacing `<readme>` with the absolute path of `<webpilot>/README.md`.

Tell the user the skill becomes available in new sessions (Claude Code: also as `/webpilot`).

**Option 2: note in the instructions.** Add the snippet below to the file they choose (see the table in `README.md`,
section "Making WebPilot known to other agents"). Append it; do not rewrite the rest of the file:

```markdown
## Browser (WebPilot)
To browse the web, read pages, search, or interact with sites, use the `webpilot` CLI.
It drives the user's real Chromium-based browser (Chrome, Edge, Brave, ...; logged-in sessions) or a temporary one (`--temp`).
Before first use in a session, read <webpilot>/README.md fully (sections 2+).
On a site you may have used before, first check its site notes and `webpilot script` (README §2).
Real browser = the user's real accounts: never buy, send, delete, or change settings without asking.
```

In either option, if `uv tool install` did not work in step 4, replace `webpilot` with `uv run --project <webpilot> webpilot`.

## 8. Report

Tell the user, briefly: what was installed and where (including any skill or instruction file you wrote), how you verified it, the browser profile name(s) detected,
and the one-line rule for agents (never act on real accounts without asking). Mention `blocked_domains` in
`~/.webpilot/config.json` as the way to keep sites off limits, and `SECURITY.md` for the threat model.
