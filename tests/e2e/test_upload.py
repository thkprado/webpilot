"""upload: local files given to a file input (visible, hidden behind a label or a button, multiple, in an iframe or
a shadow root) or dropped on a drop zone, arriving byte for byte; the errors and what the session log keeps."""

import hashlib
import json
import sys

import pytest
from helpers import page_log, ref

from webpilot import cli, client, session_log
from webpilot.client import WebPilotError

pytestmark = pytest.mark.e2e


@pytest.fixture
def notes(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("Meeting at noon.", "utf-8")
    return path


@pytest.fixture
def photo(tmp_path):
    path = tmp_path / "photo.png"
    path.write_bytes(bytes(range(256)) * 40)  # every byte value, so a text round trip would show
    return path


def entry(path, field, **extra):
    data = path.read_bytes()
    return {"field": field, "name": path.name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest(), **extra}


def received(b, n=1):
    """What the page's fields received, without the type (checked on its own where it matters)."""
    return [{k: v for k, v in e.items() if k != "type"} for e in page_log(b, n)]


def test_a_visible_input_gets_a_text_file(b, site, notes):
    b.goto(site.url("upload.html?noframe=1"))
    res = b.upload("#plain", notes)
    assert res["uploaded"] == 'input#plain "Resume" name=resume'
    assert res["files"] == [{"name": "notes.txt", "bytes": 16}]
    assert res["changed"] is True
    assert page_log(b, 1) == [{**entry(notes, "plain"), "type": "text/plain", "text": "Meeting at noon."}]


def test_a_binary_file_arrives_byte_for_byte(b, site, photo):
    b.goto(site.url("upload.html?noframe=1"))
    b.upload("#plain", photo)
    log = page_log(b, 1)
    assert log[0]["type"] == "image/png"
    assert received(b) == [entry(photo, "plain")]


def test_hidden_inputs_behind_a_label_and_a_button(b, site, notes, photo):
    b.goto(site.url("upload.html?noframe=1"))
    res = b.upload("text=Choose avatar", photo)  # the label's control
    assert res["uploaded"] == 'input#avatar "Choose avatar" accept=image/*'
    button = ref(b.snapshot(interactive=True)["text"], "button", "Attach document")
    res = b.upload(button, notes)  # the only file input in the button's form
    assert res["uploaded"].startswith("input#doc")
    assert received(b, 2) == [entry(photo, "avatar"), {**entry(notes, "doc"), "text": "Meeting at noon."}]


def test_several_files_on_a_multiple_input(b, site, notes, photo):
    b.goto(site.url("upload.html?noframe=1"))
    res = b.upload("#many", notes, photo)
    assert [f["name"] for f in res["files"]] == ["notes.txt", "photo.png"]
    assert [e["name"] for e in page_log(b, 2)] == ["notes.txt", "photo.png"]


def test_several_files_on_a_single_input_fail(b, site, notes, photo):
    b.goto(site.url("upload.html?noframe=1"))
    with pytest.raises(WebPilotError, match=r"2 files for a file input that takes one \(no multiple attribute\): "
                                            r"input#plain"):
        b.upload("#plain", notes, photo)
    assert page_log(b) == []


def test_drop_on_a_drop_zone(b, site, notes):
    b.goto(site.url("upload.html?noframe=1"))
    res = b.upload("#zone", notes, drop=True)
    assert res["dropped"] == 'div#zone "Drop files here"' and res["files"] == [{"name": "notes.txt", "bytes": 16}]
    assert "hint" not in res
    assert received(b) == [{**entry(notes, "zone"), "text": "Meeting at noon."}]
    res = b.upload("#dead", notes, drop=True)
    assert res["hint"].startswith("nothing on the page took the drop")


def test_inside_an_iframe_and_a_shadow_root(b, site, notes):
    b.goto(site.url("upload.html"))
    snap = b.snapshot(interactive=True)["text"]
    inner = ref(snap, "input:file", "Child file")
    assert inner.startswith("f")
    res = b.upload(inner, notes)
    assert res["uploaded"].startswith("input#inner") and res["frameUrl"].endswith("upload.html?child=1")
    res = b.upload(ref(snap, "button", "Pick in shadow"), notes)  # the only file input in its shadow root
    assert res["uploaded"].startswith("input#shadow")
    log = page_log(b, 2)
    assert {(e["field"], e.get("child", False)) for e in log} == {("inner", True), ("shadow", False)}


def test_errors_say_what_to_target(b, site, notes, tmp_path):
    b.goto(site.url("upload.html?noframe=1"))
    with pytest.raises(WebPilotError, match=r"several file inputs for button#both \"Attach ID\": "
                                            r"input#front .*name=front; input#back .*name=back; target one of them"):
        b.upload("#both", notes, timeout=1)
    with pytest.raises(WebPilotError, match="file not found: .*missing.txt"):
        b.upload("#plain", tmp_path / "missing.txt")
    with pytest.raises(WebPilotError, match="element not found: #nowhere"):
        b.upload("#nowhere", notes, timeout=1)


def test_files_over_the_limit_fail_before_any_request(b, site, notes, monkeypatch):
    monkeypatch.setattr(client, "MAX_UPLOAD_BYTES", 10)
    with pytest.raises(WebPilotError, match=r"files too large to upload: 0.0 MB, the limit is 0 MB"):
        b.upload("#plain", notes)


def test_cli_uploads_and_the_log_keeps_only_sizes(b, site, notes, photo, monkeypatch, capsys):
    b.goto(site.url("upload.html?noframe=1"))
    monkeypatch.setattr(sys, "argv", ["webpilot", "--temp", "upload", "#many", str(notes), str(photo)])
    try:
        cli.run()
    except SystemExit as e:
        assert not e.code
    res = json.loads(capsys.readouterr().out)
    assert res["uploaded"].startswith("input#many") and len(res["files"]) == 2
    log = session_log.read([session_log.session_name()])[-1]
    assert log["cmd"] == "upload" and log["args"]["files"] == [16, 10240]
    assert "notes.txt" not in json.dumps(log) and "Meeting" not in json.dumps(log)
