# Security Policy

## Supported versions

WebPilot is pre-1.0. Only the latest commit on `main` receives security fixes.

## Reporting a vulnerability

Please **do not open a public issue** for security problems.

Report them privately through GitHub: **Security → Report a vulnerability** on this repository
(private vulnerability reporting). If that is unavailable, contact the maintainer through the
email on the GitHub profile [@thkprado](https://github.com/thkprado).

Include, when possible: what you found, steps to reproduce, the affected commit, and the impact you expect.
This is a personal project: expect an acknowledgement within about 7 days and a fix or mitigation as
soon as reasonably possible. Please give me time to fix the problem before disclosing it publicly.

## Threat model

WebPilot lets a local program (usually an AI coding agent) control a browser. In *real* mode that browser
holds your logged-in sessions, so the tool is powerful by design.

**What WebPilot defends against**

- Web pages and other websites talking to the daemon: it listens on `127.0.0.1` only, requires a random
  token (`~/.webpilot/config.json`) in the first message, and rejects connections from web pages
  (checks the `Origin`).
- Agent access to sites you want off limits: `blocked_domains` in the config.
- Dangerous writes by accident: `fetch` refuses methods other than GET/HEAD unless `--allow-write` is given.

**What it does not defend against**

- A malicious or compromised local user or process that can read `~/.webpilot/config.json`
  (it contains the token), or run as you, can drive your browser.
- An agent that you instructed (or that was tricked by prompt injection from a web page) to do harmful
  things within the permissions you gave it. Review what an agent does in your real browser, and use
  `--temp` or `blocked_domains` when in doubt.
- Other software on the machine with access to your browser profile.

## Extension permissions

The extension requests `<all_urls>`, `tabs`, `tabGroups`, `scripting`, `debugger`, `storage`, `alarms` and
`webRequest`, because it must read and operate any page you let the agent open. It is meant to be loaded
unpacked from a build you made from this source. Do not install builds from unknown sources.

## Reports that are in scope

- Bypassing the token or origin check of the daemon.
- Any way for a web page to control the extension or the daemon.
- Leaking the token or session data outside the machine.
- Bypassing `blocked_domains` or the `fetch` write protection.

Out of scope: an agent misbehaving inside the permissions you granted, and issues that need prior full
control of your user account.
