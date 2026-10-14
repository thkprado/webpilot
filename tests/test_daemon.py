"""Daemon protocol: a fake extension answers commands relayed from the Python client."""

import asyncio
import json
import socket
import threading

import pytest
from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect

from webpilot.client import Browser, Connection, WebPilotError, _response_body
from webpilot.server import Daemon


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def daemon(tmp_path, monkeypatch):
    port = free_port()
    monkeypatch.setenv("WEBPILOT_DIR", str(tmp_path))
    monkeypatch.setenv("WEBPILOT_PORT", str(port))
    from webpilot import config

    token = config.load()["token"]
    d = Daemon(token, port)
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_until_complete, args=(d.run(),), daemon=True)
    thread.start()
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.1).close()
            break
        except OSError:
            threading.Event().wait(0.05)
    yield {"port": port, "token": token, "daemon": d}
    loop.call_soon_threadsafe(d.stop_event.set)
    thread.join(5)


def fake_extension(port: int, token: str, mode: str = "real", origin: str = "chrome-extension://abc",
                   profile: str | None = None, delay: float = 0, results: dict | None = None):
    """A fake extension that echoes each command, or answers with `results[cmd]` when given."""
    ws = connect(f"ws://127.0.0.1:{port}", origin=origin).__enter__()
    ws.send(json.dumps({"type": "hello", "role": "extension", "mode": mode, "token": token, "profile": profile}))

    def loop():
        try:
            for raw in ws:
                msg = json.loads(raw)
                threading.Event().wait(delay)
                if msg["cmd"] == "fail":
                    ws.send(json.dumps({"id": msg["id"], "ok": False, "error": "boom"}))
                elif results and msg["cmd"] in results:
                    ws.send(json.dumps({"id": msg["id"], "ok": True, "result": results[msg["cmd"]]}))
                else:
                    ws.send(json.dumps({"id": msg["id"], "ok": True, "result": {
                        "cmd": msg["cmd"], "args": msg["args"], "url": "https://x.test/", "profile": profile}}))
        except Exception:
            pass

    threading.Thread(target=loop, daemon=True).start()
    return ws


def test_relay_roundtrip(daemon):
    ext = fake_extension(daemon["port"], daemon["token"])
    b = Browser("real", autostart=False)
    res = b.call("goto", url="https://x.test/")
    assert res["cmd"] == "goto" and res["args"] == {"url": "https://x.test/"}
    assert "real" in b.status()["extensions"]
    with pytest.raises(WebPilotError, match="boom"):
        b.call("fail")
    b.close()
    ext.close()


def test_eval_timeout_is_sent_to_the_daemon(daemon):
    ext = fake_extension(daemon["port"], daemon["token"], delay=1.5)
    b = Browser("real", autostart=False)
    with pytest.raises(WebPilotError, match="timed out"):
        b.eval("slow()", timeout=0.5)
    assert b.eval("slow()", timeout=5)["args"] == {"expression": "slow()"}
    b.close()
    ext.close()


def test_eval_args_are_sent_as_values_and_logged_by_size(daemon):
    ext = fake_extension(daemon["port"], daemon["token"])
    b = Browser("real", autostart=False)
    body = 'line one\nwith \'quotes\', "double" and `ticks`'
    res = b.eval("(t, n) => t.repeat(n)", args=(body, 2))
    assert res["args"] == {"expression": "(t, n) => t.repeat(n)", "args": [body, 2]}
    # Without args, nothing extra is sent (the expression is evaluated, not called).
    assert b.eval("1 + 1")["args"] == {"expression": "1 + 1"}
    b.close()
    ext.close()
    from webpilot import session_log

    entry = session_log.read([session_log.session_name()])[-2]
    assert entry["cmd"] == "eval"
    assert entry["args"]["args"].startswith("<2 values, ")
    assert "quotes" not in json.dumps(entry)


def test_results_that_are_not_text_are_logged_by_size(daemon):
    # eval returns whatever the page's code returns: fields like `body` or `url` in it are data, not
    # parts of a command result. fetch returns a parsed JSON body.
    value = {"body": 1600, "text": 3, "url": "https://from-the-page.test/", "busy": "dom"}
    fetched = {"status": 200, "url": "https://api.test/items", "body": {"items": [1, 2, 3]}}
    ext = fake_extension(daemon["port"], daemon["token"], results={"eval": value, "fetch": fetched})
    b = Browser("real", autostart=False)
    assert b.eval("({body: 1600})") == value
    assert b.fetch("https://api.test/items")["body"] == {"items": [1, 2, 3]}
    b.close()
    ext.close()
    from webpilot import session_log

    eval_entry, fetch_entry = session_log.read([session_log.session_name()])[-2:]
    assert eval_entry["cmd"] == "eval" and eval_entry["ok"]
    assert eval_entry["out_chars"] == len(json.dumps(value, ensure_ascii=False))
    assert "url" not in eval_entry and "busy" not in eval_entry
    assert fetch_entry["cmd"] == "fetch" and fetch_entry["status"] == 200
    assert fetch_entry["url"] == "https://api.test/items"
    assert fetch_entry["out_chars"] == len(json.dumps({"items": [1, 2, 3]}, ensure_ascii=False))


def test_eval_cli_reads_args_from_files_and_json(daemon, tmp_path):
    from typer.testing import CliRunner

    from webpilot.cli import app

    ext = fake_extension(daemon["port"], daemon["token"])
    notes = tmp_path / "notes.md"
    notes.write_text("# Title\n\nbody with 'quotes'\n", encoding="utf-8")
    runner = CliRunner()

    def sent(*cli_args: str) -> dict:
        result = runner.invoke(app, ["eval", *cli_args])
        assert result.exit_code == 0, result.output
        return json.loads(result.output)["args"]

    assert sent("(a, b) => a + b", "--arg", f"@{notes}", "--arg", "@@literal")["args"] == [
        "# Title\n\nbody with 'quotes'\n", "@literal"]
    assert sent("(o) => o.n", "--args-json", '[{"n": 1}, null]')["args"] == [{"n": 1}, None]
    assert "args" not in sent("document.title")
    both = runner.invoke(app, ["eval", "(a) => a", "--arg", "x", "--args-json", "[1]"])
    assert both.exit_code != 0 and "not both" in both.output
    not_array = runner.invoke(app, ["eval", "(a) => a", "--args-json", '{"a": 1}'])
    assert not_array.exit_code != 0 and "JSON array" in not_array.output
    ext.close()


def test_tab_override_is_sent(daemon):
    ext = fake_extension(daemon["port"], daemon["token"])
    b = Browser("real", tab=42, autostart=False)
    assert b.call("snapshot")["args"] == {"tabId": 42}
    b.close()
    ext.close()


def test_missing_extension_errors(daemon, monkeypatch):
    monkeypatch.setitem(__import__("webpilot.client").client.EXTENSION_WAIT, "temp", 0.2)
    b = Browser("temp", autostart=False)
    with pytest.raises(WebPilotError, match="Temporary browser is not connected"):
        b.call("ping")
    b.close()


def test_bad_token_rejected(daemon):
    cfg = {"port": daemon["port"], "token": "wrong"}
    with pytest.raises(WebPilotError, match="rejected"):
        Connection(cfg, autostart=False)


def test_web_origin_rejected(daemon):
    with connect(f"ws://127.0.0.1:{daemon['port']}", origin="https://evil.example") as ws:
        with pytest.raises(ConnectionClosed):
            ws.send(json.dumps({"type": "hello", "role": "client", "token": daemon["token"]}))
            ws.recv(timeout=2)


def test_malformed_client_requests_get_an_error(daemon):
    with connect(f"ws://127.0.0.1:{daemon['port']}") as ws:
        ws.send(json.dumps({"type": "hello", "role": "client", "token": daemon["token"]}))
        assert json.loads(ws.recv(timeout=2))["type"] == "welcome"
        for bad in ("not json", "[1, 2]"):
            ws.send(bad)
            assert json.loads(ws.recv(timeout=2)) == {"id": None, "ok": False, "error": "request must be a JSON object"}
        ws.send(json.dumps({"id": "s", "cmd": "daemon.status"}))
        assert json.loads(ws.recv(timeout=2))["ok"] is True  # the connection survived


def test_malformed_extension_messages_are_ignored(daemon):
    with connect(f"ws://127.0.0.1:{daemon['port']}", origin="chrome-extension://abc") as ext:
        ext.send(json.dumps({"type": "hello", "role": "extension", "token": daemon["token"]}))
        for bad in ("not json", "[1]", json.dumps({"id": ["x"], "ok": True})):
            ext.send(bad)
        ext.send(json.dumps({"type": "ping"}))
        assert json.loads(ext.recv(timeout=2)) == {"type": "pong"}


def test_session_log_domain_has_no_credentials_or_port():
    from webpilot.session_log import domain

    assert domain("https://user:pw@WWW.Example.com:8443/x") == "example.com"
    assert domain("http://localhost:8000/") == "localhost"
    assert domain(None) == ""


def test_actions_are_logged_without_typed_text(daemon, tmp_path):
    ext = fake_extension(daemon["port"], daemon["token"])
    b = Browser("real", autostart=False)
    b.type("#password", "hunter2")
    b.close()
    ext.close()
    from webpilot import session_log

    entry = session_log.read([session_log.session_name()])[-1]
    assert entry["cmd"] == "type"
    assert entry["args"]["text"] == "<7 chars>"
    assert "hunter2" not in json.dumps(entry)


def test_select_is_sent_and_logged_without_its_text(daemon):
    from typer.testing import CliRunner

    from webpilot import session_log
    from webpilot.cli import app

    ext = fake_extension(daemon["port"], daemon["token"])
    b = Browser("real", autostart=False)
    res = b.select("e16", "Teams", timeout=2)
    assert res["cmd"] == "select" and res["args"] == {"target": "e16", "text": "Teams", "timeout": 2}
    b.close()
    result = CliRunner().invoke(app, ["select", "e16", "I have a billing issue", "--wait-text", "Thanks"])
    assert result.exit_code == 0, result.output
    sent = json.loads(result.output)["args"]
    assert sent["target"] == "e16" and sent["text"] == "I have a billing issue" and sent["waitText"] == "Thanks"
    ext.close()

    entries = [e for e in session_log.read([session_log.session_name()]) if e["cmd"] == "select"]
    assert [e["args"]["text"] for e in entries[-2:]] == ["<5 chars>", "<22 chars>"]
    assert "billing" not in json.dumps(entries)


def test_fetch_args_are_sent_and_logged_without_secrets(daemon):
    ext = fake_extension(daemon["port"], daemon["token"])
    b = Browser("real", autostart=False)
    res = b.fetch("/api/x", method="post", headers={"Authorization": "Bearer s3cret"}, json={"q": 1},
                  timeout=30, allow_write=True)
    assert res["cmd"] == "fetch" and res["args"] == {
        "url": "/api/x", "method": "POST", "timeoutMs": 30000, "allowWrite": True, "body": '{"q": 1}',
        "headers": {"Authorization": "Bearer s3cret", "Content-Type": "application/json"}}
    b.close()
    ext.close()
    from webpilot import session_log

    entry = session_log.read([session_log.session_name()])[-1]
    assert entry["cmd"] == "fetch"
    assert entry["args"]["headers"] == ["Authorization", "Content-Type"]
    assert entry["args"]["body"] == "<8 chars>"
    assert "s3cret" not in json.dumps(entry)


def test_fetch_response_body():
    ok = {"status": 200, "headers": {"content-type": "application/json; charset=utf-8"}, "body": '{"a": [1]}'}
    assert _response_body(dict(ok), raw=False)["body"] == {"a": [1]}
    assert _response_body(dict(ok), raw=True)["body"] == '{"a": [1]}'
    bad = {"status": 200, "headers": {"content-type": "application/json"}, "body": "not json"}
    assert _response_body(dict(bad), raw=False)["body"] == "not json"
    png = {"status": 200, "headers": {"content-type": "image/png"}, "bodyBase64": "iVBORw=="}
    res = _response_body(png, raw=False)
    assert res["body"] == bytes([0x89]) + b"PNG" and "bodyBase64" not in res


def test_action_wait_args_are_sent(daemon):
    ext = fake_extension(daemon["port"], daemon["token"])
    b = Browser("real", autostart=False)
    assert b.click("text=Next|Próximo")["args"] == {"target": "text=Next|Próximo"}
    assert b.click("e3", timeout=2, wait_text="Question 5", wait_timeout=7)["args"] == {
        "target": "e3", "timeout": 2, "waitText": "Question 5", "waitTimeout": 7}
    res = b.submit("e4", wait_selector=".question")
    assert res["cmd"] == "submit"
    assert res["args"] == {"target": "e4", "waitSelector": ".question", "waitTimeout": 10}
    assert b.submit()["args"] == {}
    assert b.wait(text="Loading", gone=True)["args"] == {"text": "Loading", "timeout": 10, "gone": True}
    b.close()
    ext.close()


def wait_profiles(b: Browser, n: int) -> None:
    for _ in range(100):
        if len(b.status()["extensions"].get("real", {})) == n:
            return
        threading.Event().wait(0.02)
    raise AssertionError(f"expected {n} connected profiles")


def test_profiles_are_routed_by_name(daemon, monkeypatch):
    monkeypatch.setitem(__import__("webpilot.client").client.EXTENSION_WAIT, "real", 0.2)
    work = fake_extension(daemon["port"], daemon["token"], profile="work")
    home = fake_extension(daemon["port"], daemon["token"], profile="home")
    b = Browser("real", autostart=False)
    wait_profiles(b, 2)
    assert sorted(b.status()["extensions"]["real"]) == ["home", "work"]
    with pytest.raises(WebPilotError, match=r"several browser profiles are connected \(home, work\)"):
        b.call("ping")
    assert Browser("real", profile="home", autostart=False).call("ping")["profile"] == "home"
    monkeypatch.setenv("WEBPILOT_PROFILE", "work")
    assert Browser("real", autostart=False).call("ping")["profile"] == "work"
    with pytest.raises(WebPilotError, match=r"'other' is not connected \(connected: home, work\)"):
        Browser("real", profile="other", autostart=False).call("ping")
    work.close()
    wait_profiles(b, 1)
    monkeypatch.delenv("WEBPILOT_PROFILE")
    assert b.call("ping")["profile"] == "home"  # the only one left needs no name
    b.close()
    home.close()


def test_duplicate_profile_name_is_refused(daemon):
    first = fake_extension(daemon["port"], daemon["token"], profile="work")
    b = Browser("real", autostart=False)
    wait_profiles(b, 1)
    with connect(f"ws://127.0.0.1:{daemon['port']}", origin="chrome-extension://abc") as dup:
        dup.send(json.dumps({"type": "hello", "role": "extension", "mode": "real", "token": daemon["token"],
                             "profile": "work"}))
        with pytest.raises(ConnectionClosed) as e:
            dup.recv(timeout=2)
    assert e.value.rcvd.code == 4001
    assert b.call("ping")["profile"] == "work"  # the first connection is untouched
    b.close()
    first.close()
