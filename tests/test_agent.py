"""The agent key: each agent (a Copilot CLI or Claude Code session, a terminal) gets its own current tab.

Process chains are fakes shaped like the ones observed (docs: agent-tabs survey): names, pids, start times."""

import json

import pytest
from test_daemon import daemon, fake_extension  # noqa: F401 - daemon is a fixture

from webpilot import agent, session_log
from webpilot.agent import Proc, agent_key, from_process_tree
from webpilot.client import Browser

NO_ENV: dict = {}


def tree(*procs: tuple[int, str, int, float]):
    """A process lookup over (pid, name, ppid, start time) rows; an unknown pid has ended."""
    table = {pid: Proc(name, ppid, created) for pid, name, ppid, created in procs}

    def lookup(pid: int) -> Proc:
        if pid not in table:
            raise ProcessLookupError(pid)
        return table[pid]

    return lookup


# Claude Code on Windows: a new bash (or cmd + pwsh) per command under one claude.exe.
CLAUDE = [
    (2260, "claude.exe", 5652, 100.0),
    (5652, "pwsh.exe", 22176, 90.0),
    (22176, "WindowsTerminal.exe", 1516, 10.0),
    (1516, "svchost.exe", 1276, 1.0),
]
CLAUDE_CMD_1 = [(31, "bash.exe", 2260, 200.0), (32, "bash.exe", 31, 200.1), (33, "uv.exe", 32, 200.2),
                (34, "python.exe", 33, 200.3)]
CLAUDE_CMD_2 = [(41, "cmd.exe", 2260, 300.0), (42, "pwsh.exe", 41, 300.1), (43, "uv.exe", 42, 300.2),
                (44, "python.exe", 43, 300.3), (45, "python.exe", 44, 300.4)]


def test_claude_like_chain_gives_the_host():
    assert from_process_tree(tree(*CLAUDE, *CLAUDE_CMD_1), 34) == "claude:2260:100"


def test_two_commands_of_one_session_share_a_key():
    lookup = tree(*CLAUDE, *CLAUDE_CMD_1, *CLAUDE_CMD_2)
    assert from_process_tree(lookup, 34) == from_process_tree(lookup, 45) == "claude:2260:100"


def test_two_copilot_cli_sessions_get_two_keys():
    # Linux: a new bash per command; the host is the CLI's node child, whose name is `MainThread`.
    common = [(900, "gnome-terminal-server", 800, 1.0), (800, "systemd", 1, 0.5)]
    session_1 = [(110, "bash", 900, 10.0), (120, "MainThread", 110, 11.0), (130, "MainThread", 120, 11.5)]
    session_2 = [(210, "bash", 900, 20.0), (220, "MainThread", 210, 21.0), (230, "MainThread", 220, 21.5)]
    commands = [(131, "bash", 130, 50.0), (132, "uv", 131, 50.1), (133, "python3", 132, 50.2),
                (141, "bash", 130, 60.0), (142, "python3.12", 141, 60.1),
                (231, "bash", 230, 55.0), (232, "uv", 231, 55.1), (233, "python3", 232, 55.2)]
    lookup = tree(*common, *session_1, *session_2, *commands)
    assert from_process_tree(lookup, 133) == from_process_tree(lookup, 142) == "mainthread:130:11"
    assert from_process_tree(lookup, 233) == "mainthread:230:21"


def test_under_a_terminal_each_shell_is_one_agent():
    # A person (or an agent typing in a terminal): two Windows Terminal windows, two commands in each.
    terminal = [(22176, "WindowsTerminal.exe", 1516, 10.0), (1516, "svchost.exe", 1276, 1.0)]
    shells = [(500, "pwsh.exe", 22176, 100.0), (600, "pwsh.exe", 22176, 110.0)]
    commands = [(501, "uv.exe", 500, 200.0), (502, "python.exe", 501, 200.1),
                (503, "uv.exe", 500, 300.0), (504, "python.exe", 503, 300.1),
                (601, "uv.exe", 600, 250.0), (602, "python.exe", 601, 250.1)]
    lookup = tree(*terminal, *shells, *commands)
    assert from_process_tree(lookup, 502) == from_process_tree(lookup, 504) == "pwsh:500:100"
    assert from_process_tree(lookup, 602) == "pwsh:600:110"


def test_terminal_names_are_normalized():
    lookup = tree((10, "Code - Insiders.exe", 1, 1.0), (20, "zsh", 10, 2.0), (30, "python3.13", 20, 3.0),
                  (40, "tmux: server", 1, 1.0), (50, "bash", 40, 2.0))
    assert from_process_tree(lookup, 30) == "zsh:20:2"
    assert from_process_tree(lookup, 50) == "bash:50:2"


def test_unknown_or_broken_trees_give_no_key():
    assert agent_key(NO_ENV, lookup=tree(), start=99) is None  # the parent has already ended
    assert agent_key(NO_ENV, lookup=tree((5, "bash", 0, 1.0)), start=5) is None  # launchers up to the root
    # pid 7's real parent ended and its pid went to a later process: never key on that one
    assert from_process_tree(tree((7, "bash", 8, 50.0), (8, "claude", 1, 60.0)), 7) is None

    def denied(pid):
        raise PermissionError(pid)

    assert agent_key(NO_ENV, lookup=denied, start=1) is None


def test_webpilot_session_wins_then_host_session_ids():
    lookup = tree(*CLAUDE, *CLAUDE_CMD_1)
    env = {"WEBPILOT_SESSION": "review", "CLAUDE_CODE_SESSION_ID": "abc"}
    assert agent_key(env, lookup=lookup, start=34) == "session:review"
    claude = agent_key({"CLAUDE_CODE_SESSION_ID": "abc-123"}, lookup=lookup, start=34)
    assert claude.startswith("claude:") and "abc" not in claude  # only a hash of the id leaves the machine's env
    assert claude == agent_key({"CLAUDE_CODE_SESSION_ID": "abc-123"})  # no process walk needed
    copilot_1 = agent_key({"COPILOT_AGENT_SESSION_ID": "s1"})
    copilot_2 = agent_key({"COPILOT_AGENT_SESSION_ID": "s2"})
    assert copilot_1.startswith("copilot:") and copilot_1 != copilot_2
    assert agent_key({"WEBPILOT_SESSION": " ", "CLAUDE_CODE_SESSION_ID": ""}, lookup=lookup, start=34) == "claude:2260:100"


def test_browser_agent_argument_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("WEBPILOT_DIR", str(tmp_path))
    monkeypatch.setenv("WEBPILOT_SESSION", "from-env")
    assert Browser("real", agent="a", autostart=False).agent == "a"
    assert Browser("real", agent="", autostart=False).agent is None  # the browser's shared current tab
    assert Browser("real", autostart=False).agent == "session:from-env"


def test_real_process_tree_gives_a_key_or_none():
    # Whatever runs the tests (a terminal, an agent, CI), the walk must not raise.
    key = agent_key(NO_ENV)
    assert key is None or key.count(":") == 2


def test_daemon_forwards_the_agent_and_the_log_records_it(daemon):  # noqa: F811
    ext = fake_extension(daemon["port"], daemon["token"])
    a = Browser("real", agent="a", autostart=False)
    shared = Browser("real", agent="", autostart=False)
    res = a.call("snapshot")
    assert res["agent"] == "a" and res["args"] == {}  # next to args, not inside them
    assert "agent" not in shared.call("snapshot")
    a.close()
    shared.close()
    ext.close()
    entries = session_log.read([session_log.session_name()])
    assert entries[-2]["agent"] == "a" and "agent" not in entries[-1]
    assert "agent" not in json.dumps(entries[-2]["args"])


@pytest.mark.parametrize("name", ["bash", "pwsh.exe", "uv", "python3.11", "webpilot.exe", "env"])
def test_launchers(name):
    assert agent._is_launcher(agent._norm(name))
