"""Summarises session logs into concrete optimisation suggestions for the agent."""

from __future__ import annotations

from collections import Counter, defaultdict

from .session_log import domain as _domain

RAW_READS = {"snapshot", "html", "text"}
ACTIONS = {"click", "type", "select", "press", "submit"}
PASSIVE = {"wait", "screenshot", "scroll"}  # skipped when looking for what a read was for
FLOW_READS = 5  # reads before actions on one domain that make it worth recording the flow
LARGE_OUTPUT = 20000
SLOW_MS = 15000
INTERNAL = {"extract", "fixture", "save"}  # html fetched for a parser, a fixture or a file: not read by the agent
BUSY_ACTIONS = 3  # actions on one domain whose page never went quiet before it is worth a suggestion


def _for_action(entries: list[dict], i: int) -> bool:
    """Whether read i was taken to find refs: an --interactive snapshot, or the next step acts on the page."""
    if (entries[i].get("args") or {}).get("interactive"):
        return True
    session = entries[i].get("session")
    for e in entries[i + 1:]:
        if e.get("session") != session:
            return False
        if e["cmd"] in RAW_READS or e["cmd"] in PASSIVE:
            continue
        return e["cmd"] in ACTIONS
    return False


def _credits(e: dict) -> list[tuple[str, int]]:
    """(domain, chars) shares of a read: inlined iframes count for their own domain."""
    frames = [(f.get("domain") or "", f.get("chars") or 0) for f in e.get("frames") or []]
    top = max((e.get("out_chars") or 0) - sum(c for _, c in frames), 0)
    return [(_domain(e.get("url")), top)] + [f for f in frames if f[0]]


def analyze(entries: list[dict]) -> dict:
    commands = Counter(e["cmd"] for e in entries)
    domains: dict[str, dict] = defaultdict(lambda: {
        "visits": 0, "raw_reads": 0, "raw_chars": 0, "action_reads": 0, "action_chars": 0,
        "parser_hits": 0, "parsers": set(), "errors": 0,
    })
    errors: Counter = Counter()
    parser_errors: dict[str, list[str]] = defaultdict(list)
    empty_parses: Counter = Counter()
    large: dict[tuple, list[int]] = defaultdict(list)  # (cmd, domain) -> sizes
    slow: dict[tuple, list[int]] = defaultdict(list)  # (cmd, domain) -> durations
    busy: dict[tuple, list[dict]] = defaultdict(list)  # (domain, reason) -> actions that never settled

    for i, e in enumerate(entries):
        d = domains[_domain(e.get("url"))] if e.get("url") else None
        cmd = e["cmd"]
        internal = e.get("purpose") in INTERNAL
        if d is not None:
            if cmd in ("goto", "tab.new"):
                d["visits"] += 1
            if cmd in RAW_READS and not internal:
                # Reads taken to act (snapshot -> click) are a flow to record, not content a parser could serve.
                kind = "action" if _for_action(entries, i) else "raw"
                credits = _credits(e)
                domains[max(credits, key=lambda c: c[1])[0]][f"{kind}_reads"] += 1
                for name, chars in credits:
                    domains[name][f"{kind}_chars"] += chars
            if cmd == "extract" and e.get("parser"):
                d["parser_hits"] += 1
                d["parsers"].add(e["parser"])
            if not e.get("ok", True):
                d["errors"] += 1
        if not e.get("ok", True):
            if cmd == "extract" and e.get("parser"):
                parser_errors[e["parser"]].append(e.get("error", ""))
            else:
                errors[(cmd, (e.get("error") or "")[:120])] += 1
        if cmd == "extract" and e.get("parser") and e.get("empty"):
            empty_parses[e["parser"]] += 1
        if not internal and (e.get("out_chars") or 0) > LARGE_OUTPUT:
            large[(cmd, _domain(e.get("url")))].append(e["out_chars"])
        if (e.get("ms") or 0) > SLOW_MS:
            slow[(cmd, _domain(e.get("url")))].append(e["ms"])
        if e.get("busy"):
            busy[(e.get("frame_domain") or _domain(e.get("url")), e["busy"])].append(e)

    def is_flow(d: dict) -> bool:
        return d["action_reads"] >= FLOW_READS and d["action_reads"] > d["raw_reads"]

    suggestions = []
    for name, d in sorted(domains.items(), key=lambda kv: -kv[1]["raw_chars"]):
        if name and d["raw_reads"] >= 2 and not d["parsers"] and not is_flow(d):
            suggestions.append(
                f"Write a parser for {name}: {d['raw_reads']} raw page reads ({d['raw_chars']} chars) and no parser."
            )
    for name, d in sorted(domains.items(), key=lambda kv: -kv[1]["action_reads"]):
        if name and is_flow(d):
            content = (f" A parser is worth it only if its data is needed again ({d['raw_reads']} other reads)."
                       if d["raw_reads"] >= 2 and not d["parsers"] else "")
            suggestions.append(
                f"Record the flow on {name}: {d['action_reads']} reads ({d['action_chars']} chars) taken to find refs "
                "before click/type. Note its steps in parsers_user/NOTES.md (or a script in parsers_user/scripts/ "
                f"if it repeats) and use `snapshot -i`/`--selector` to keep reads small.{content}"
            )
    for name, errs in parser_errors.items():
        suggestions.append(f"Fix parser {name}: {len(errs)} failure(s), last: {errs[-1]}")
    for name, count in empty_parses.items():
        suggestions.append(f"Parser {name} returned empty data {count} time(s): the site layout may have changed.")
    for (cmd, err), count in errors.items():
        if count >= 2:
            suggestions.append(f"Repeated error in `{cmd}` ({count}x): {err}")
    for (cmd, name), sizes in sorted(large.items(), key=lambda kv: -sum(kv[1]))[:5]:
        times = f"{len(sizes)}x, up to " if len(sizes) > 1 else ""
        suggestions.append(
            f"Large output ({times}{max(sizes)} chars) from `{cmd}` on {name}: use --selector/--interactive or a parser."
        )
    for (name, reason), acts in sorted(busy.items(), key=lambda kv: -len(kv[1])):
        if len(acts) < BUSY_ACTIONS:
            continue
        unmarked = sum(1 for a in acts if not {"waitText", "waitSelector"} & set(a.get("args") or {}))
        what = "the DOM kept changing, e.g. a running clock" if reason == "dom" else "requests stayed in flight (polling)"
        tip = (f" {unmarked} of them had no --wait-text/--wait-for: with a marker of the next state the wait is shorter."
               if unmarked else "")
        suggestions.append(
            f"Page never went quiet after {len(acts)} actions on {name}: {what} (avg "
            f"{round(sum(a.get('ms') or 0 for a in acts) / len(acts))} ms).{tip} Note it in parsers_user/NOTES.md."
        )
    for (cmd, name), times in sorted(slow.items(), key=lambda kv: -max(kv[1]))[:5]:
        count = f"{len(times)}x, up to " if len(times) > 1 else ""
        suggestions.append(f"Slow `{cmd}` ({count}{max(times)} ms) on {name}.")

    return {
        "entries": len(entries),
        "commands": dict(commands.most_common()),
        "domains": [
            {"domain": k, **{kk: (sorted(vv) if isinstance(vv, set) else vv) for kk, vv in v.items()}}
            for k, v in sorted(domains.items(),
                               key=lambda kv: -(kv[1]["visits"] + kv[1]["raw_reads"] + kv[1]["action_reads"]))
            if k
        ],
        "errors": [{"cmd": c, "error": m, "count": n} for (c, m), n in errors.most_common()],
        "suggestions": suggestions,
    }


def to_markdown(report: dict, sessions: list[str]) -> str:
    lines = [f"# WebPilot session report ({', '.join(sessions) or 'no sessions'})", "",
             f"{report['entries']} logged actions.", ""]
    lines.append("## Suggestions")
    lines += [f"- {s}" for s in report["suggestions"]] or ["- Nothing obvious to optimise."]
    lines += ["", "## Domains",
              "| domain | visits | raw reads | raw chars | reads to act | parser hits | parsers | errors |",
              "|---|---|---|---|---|---|---|---|"]
    for d in report["domains"]:
        lines.append(f"| {d['domain']} | {d['visits']} | {d['raw_reads']} | {d['raw_chars']} | "
                     f"{d['action_reads']} | {d['parser_hits']} | {', '.join(d['parsers'])} | {d['errors']} |")
    lines += ["", "## Commands", ", ".join(f"{k}: {v}" for k, v in report["commands"].items())]
    if report["errors"]:
        lines += ["", "## Errors"] + [f"- `{e['cmd']}` x{e['count']}: {e['error']}" for e in report["errors"]]
    return "\n".join(lines)
