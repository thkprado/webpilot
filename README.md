# WebPilot

**English** · [Português](README.pt-BR.md)

Lets coding agents (Claude Code, Codex, Gemini CLI/Antigravity, pi, Cursor, or anything with a shell) drive a browser:

- **real**: your own Chromium-based browser (Chrome, Edge, Brave, Vivaldi, Opera, ...), with your sessions and logins, through the WebPilot extension.
- **temp**: a temporary Chromium with a throwaway profile (`--temp`).

Agent tabs in the real browser go into a purple tab group named **WebPilot**. **Agents: read [docs/agent.md](docs/agent.md) fully before using the browser; this README is for people.**

---

## 1. Setup (once, by the user)

### Let your AI set it up

Do you use an AI coding assistant (Claude Code, Codex, Gemini CLI/Antigravity, Cursor, ...)? Paste this into it:

```text
Set up WebPilot on this machine for me: https://github.com/thkprado/webpilot - follow docs/AI_SETUP.md in that repository.
```

It checks your tools (Git, Python, uv, Node.js, a Chromium-based browser), clones and builds the extension, configures the daemon and
verifies it. The only thing it cannot do is click in your browser: it gives you the exact steps to load the extension
(step "Load unpacked" below). At the end it offers to make WebPilot known to your agents, as a skill (Claude Code, Codex, Antigravity, pi, Copilot CLI) or a note in their instructions, and asks before writing either. The steps it follows are in
[docs/AI_SETUP.md](docs/AI_SETUP.md).

### Or do it yourself

`<webpilot>` stands for the folder where you cloned this repository, for example `C:\src\webpilot` or `~/src/webpilot`.

```powershell
cd <webpilot>                                           # the folder where you cloned this repository
cd extension; npm install; npm run build; cd ..       # build the extension into extension/dist
uv sync
uv run webpilot setup                                   # create token + extension/dist/config.json
uv tool install --editable .                            # optional: `webpilot` available in any folder
```

Open your browser's extensions page (`chrome://extensions`; Edge: `edge://extensions`, Opera: `opera://extensions`), turn on **Developer mode**, click **Load unpacked** and pick `extension/dist`. The extension icon shows a badge:

| Badge | Meaning |
|---|---|
| `ON` | connected to the daemon |
| `OFF` | daemon not running (it starts on the first `webpilot` command) |
| `CFG` | run `webpilot setup` again |
| `DUP` | another connected profile already uses this profile name; rename one (below) |

Click the icon for a popup with the connection state and this profile's name.

**Several profiles or browsers.** Load `extension/dist` the same way in each profile (or browser); they all share one daemon. Each profile gets a random name (`profile-1a2b`). To rename it, click the extension icon in that profile and edit the name in the popup, or use `webpilot profile list` (shows the active tab of each) and `webpilot profile rename profile-1a2b work`. With one profile connected nothing changes. With several, commands need `--profile NAME` (or `-p`), `WEBPILOT_PROFILE=NAME`, or `"profile": "NAME"` in `~/.webpilot/config.json` as the default; otherwise they fail and list the connected names.

The daemon (`webpilot serve`) starts automatically in the background. It listens only on `127.0.0.1`, requires the token from `~/.webpilot/config.json`, and rejects connections from web pages.

Without `uv tool install`, use `uv run --project <webpilot> webpilot ...`.

**Updating.** Run `update.bat` (Windows) or `./update.sh` in `<webpilot>`: it stops the daemon, pulls the newest code (`git pull --ff-only`), rebuilds the extension, runs `uv sync`, and reinstalls the `webpilot` command if you installed it with `uv tool install`. Then click reload on the WebPilot card on the browser's extensions page. `--no-pull` skips the pull, to rebuild after changing the code yourself.

### Making WebPilot known to other agents

Agents only use WebPilot if their instructions mention it. Run `uv tool install --editable .` first (so `webpilot` works in any folder; check with `webpilot status`), then paste this snippet into each harness's instruction file, replacing `<webpilot>` with the absolute path of your WebPilot folder. It only points at the agent guide, so [docs/agent.md](docs/agent.md) stays the single source of truth:

```markdown
## Browser (WebPilot)
To browse the web, read pages, search, or interact with sites, use the `webpilot` CLI.
It drives the user's real Chromium-based browser (Chrome, Edge, Brave, ...; logged-in sessions) or a temporary one (`--temp`).
Before first use in a session, read <webpilot>/docs/agent.md fully.
On a site you may have used before, first check its site notes and `webpilot script` (see the guide).
Real browser = the user's real accounts: never buy, send, delete, or change settings without asking.
```

| Harness | Global (all projects) | Per project |
|---|---|---|
| Claude Code | `~/.claude/CLAUDE.md` | `CLAUDE.md` |
| Codex CLI | `~/.codex/AGENTS.md` | `AGENTS.md` |
| Gemini CLI / Antigravity | `~/.gemini/GEMINI.md` | `GEMINI.md` or `AGENTS.md` |
| pi | `~/.pi/agent/AGENTS.md` | `AGENTS.md` |
| Cursor | Settings → Rules → User Rules | `AGENTS.md` or `.cursor/rules/webpilot.mdc` |
| Anything else with a shell | its system prompt / rules file | `AGENTS.md` |

Harnesses that support Agent Skills can get a `webpilot` skill instead, with the same text: it loads only when a task needs the browser instead of in every session. `webpilot skill` installs it for you:

```bash
webpilot skill list                      # harnesses, whether they are on this machine, skill state
webpilot skill install claude pi         # the ones you name; no name: asks for each; --all: every one found
webpilot skill install --project agy     # this project's skills folder instead of the global one
webpilot skill uninstall copilot         # or --all; only removes a skill it wrote (--force for others)
```

| Harness (name) | Global skill | Per project |
|---|---|---|
| Claude Code (`claude`) | `~/.claude/skills/webpilot/` | `.claude/skills/webpilot/` |
| Codex CLI (`codex`) | `~/.codex/skills/webpilot/` | `.codex/skills/webpilot/` |
| Antigravity IDE and agy CLI (`antigravity` or `agy`) | `~/.gemini/config/skills/webpilot/` | `.agents/skills/webpilot/` |
| pi (`pi`) | `~/.pi/agent/skills/webpilot/` | `.pi/skills/webpilot/` |
| GitHub Copilot CLI (`copilot`) | `~/.copilot/skills/webpilot/` | `.github/skills/webpilot/` |

The skill points at this clone's `docs/agent.md`. Run `webpilot skill install` again after moving the clone; `webpilot skill list` shows `outdated` when an installed skill differs from the current one. Copilot CLI also reads `~/.claude/skills/`, so on a machine with both, one of the two is enough.

Without `uv tool install`, replace `webpilot` in the snippet with `uv run --project <webpilot> webpilot`.

## 2. How agents use it

Agents run `webpilot` commands from their shell (or a Python script) and read the results:

```bash
webpilot goto https://news.ycombinator.com -s     # open a page and print a snapshot with refs: [e12 link "More"]
webpilot click e12 -s                             # act on a ref and read the next page
webpilot select e16 "billing"                     # choose in a dropdown
webpilot extract                                  # a site parser's compact JSON, when one matches
webpilot --temp search "python uv" -n 5           # the same, in a throwaway browser
```

What agents read lives in `docs/`, in English:

| File | Read |
|---|---|
| [docs/agent.md](docs/agent.md) | every session, before first use: commands, workflow, rules |
| [docs/python-api.md](docs/python-api.md) | before writing a script (`webpilot.Browser`) or calling a site's API with the session |
| [docs/parsers.md](docs/parsers.md) | before writing a site parser, site notes or a script |
| [docs/troubleshooting.md](docs/troubleshooting.md) | when an error does not say what to do |
| [docs/reflect.md](docs/reflect.md) | at the end of a session |

The guide's rules keep agents from acting on your accounts without asking: no purchases, messages, deletions,
setting changes or HTTP writes without your confirmation; your other tabs only when asked; with several browser
profiles they ask which one to use; they stop on captcha challenges and ask you to sign in instead of typing
passwords.

## 3. Site parsers, notes and scripts

Agents get faster on sites they use often by writing, usually during the end-of-session reflection:

- **parsers** (`parsers_user/<name>.py`): turn a site's HTML into compact JSON, used by `extract`;
- **site notes** (`parsers_user/NOTES.md`): workflows and quirks, one `##` section per domain;
- **scripts** (`parsers_user/scripts/<name>.py`): flows run again with `webpilot script <name>`.

`parsers_user/` is local to each user and is not versioned (it is in `.gitignore`): fixtures are saved pages, and
notes and scripts reflect your own browsing. To start from the example (a Hacker News parser with its fixture,
notes and `scripts/hn_top.py`): `cp -r examples/parsers_user parsers_user`. `WEBPILOT_PARSERS_DIR` adds another
folder, searched first. Details: [docs/parsers.md](docs/parsers.md).

## 4. Reflection (end of session)

Every action is logged in `~/.webpilot/sessions/<date>.jsonl`. Typed text is not logged, only its length.

```bash
webpilot reflect-data              # today's session; --days 7, --session NAME, --json
```

It reports domains read without a parser, repeated interactive flows (snapshots taken only to find refs before clicking; iframe content counts for the iframe's domain), parser failures, empty parser results, large outputs, repeated errors and slow commands, each with a suggestion. The full procedure is in `docs/reflect.md`. In this project, use `/reflect` in Claude Code, or the `reflect` skill in Antigravity (`.agents/skills/`) and Copilot CLI (`.github/skills/`).

## 5. Reference

| Item | Location |
|---|---|
| Config/token | `~/.webpilot/config.json` (`port`, `auto_captcha` (default `false`), `blocked_domains`, `profile`); rerun `webpilot setup` after editing it |
| Daemon log | `~/.webpilot/daemon.log` |
| Screenshots | `~/.webpilot/screenshots/` |
| Temporary browser | Chromium from Playwright; profile in `%TEMP%\webpilot-temp-*`, deleted by `webpilot temp stop` (or `webpilot stop`, which also stops the daemon); `webpilot temp start --headless` for headless. It starts with Chromium's occlusion detection off, so a window covered by others still takes real input; a minimized one does not |

- `auto_captcha: true` makes `goto` click "I'm not a robot" checkboxes by itself (result in the `captcha` field); off by default. Image challenges are never solved: the agent asks you.
- `blocked_domains` (for example `["mybank.example.com"]`) prevents the agent from navigating to or operating on those domains and their subdomains in the real browser. Case, a leading `*.` and a trailing dot do not matter.
- Environment variables: `WEBPILOT_MODE=temp`, `WEBPILOT_SESSION=name`, `WEBPILOT_PROFILE=name`, `WEBPILOT_HEADLESS=1`, `WEBPILOT_PORT`, `WEBPILOT_DIR`, `WEBPILOT_PARSERS_DIR`.

### Troubleshooting

Errors say what to do next; [docs/troubleshooting.md](docs/troubleshooting.md) covers the rest (the extension's badge is explained in Setup above). For people:

| Symptom | What to do |
|---|---|
| Extension console: "WebSocket connection to 'ws://127.0.0.1:8765/' failed: ... ERR_CONNECTION_REFUSED" | Normal while the daemon is not running: the extension retries every few seconds so it connects as soon as the daemon starts. To silence it, turn the extension off on the browser's extensions page and back on before using WebPilot. |
| After the browser was idle, the first command waits a while | The extension reconnects first; that can take up to 30 s. |
| You changed the extension code | Run `npm run build` in `extension/`, then click reload on its card on the browser's extensions page. |

## 6. Architecture

```
agent ──shell──> webpilot CLI / Python lib ──WebSocket──> daemon (127.0.0.1:8765)
                                                             │  token + extension origin only
                                    ┌────────────────────────┴──────────────────┐
                           extension in your browser (real)         extension in Chromium (temp)
                           chrome.scripting / chrome.debugger       same code, mode=temp
```

- `extension/src/background.ts`: WebSocket bridge, tabs, navigation, trusted input (CDP via `chrome.debugger`), captcha.
- `extension/src/page.ts`: injected into the page; snapshot with refs, click/type/select, captcha detection.
- `extension/src/popup.ts` + `popup.html`: toolbar popup with the connection state and the profile name.
- `src/webpilot/`: `server.py` (daemon), `client.py` (API), `cli.py`, `registry.py` (parsers), `search.py`, `session_log.py`, `reflect.py`, `temp_browser.py`.

## 7. Security and responsible use

WebPilot gives a program (and the AI agent behind it) control of a browser, so treat it like remote access to your machine:

- In **real** mode the agent acts with your logged-in sessions: email, banking, work tools. Use `blocked_domains` for sites it must never touch, and prefer `--temp` (throwaway profile) when you do not need your accounts.
- The extension requests broad permissions (`<all_urls>`, `debugger`, `scripting`, `webRequest`, `tabs`). Load it only from a build you made yourself from this source, in a browser profile you control.
- The local daemon listens on `127.0.0.1` only and requires the token in `~/.webpilot/config.json`. Keep that file private; anyone who can read it can drive your browser.
- Session logs in `~/.webpilot/sessions/` record URLs and commands (typed text is only logged by length). Saved parser fixtures can contain page content; never commit pages from a logged-in browser.
- You are responsible for following the terms of service of the sites you automate. WebPilot does not solve image captchas, and the automatic checkbox click is opt-in.
- Software is provided "as is", without warranty (see `LICENSE`). Review what an agent is about to do before allowing purchases, messages, deletions or setting changes.

Report vulnerabilities as described in `SECURITY.md`.

## License

[MIT](LICENSE)
