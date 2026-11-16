"""An extension rebuilt on disk but not reloaded in the browser says so: in errors and in `webpilot status`."""

import json
import time
from pathlib import Path

import pytest

from webpilot import WebPilotError, temp_browser

pytestmark = pytest.mark.e2e


def _build_json() -> Path:
    """dist/build.json of this worker's temporary browser, which loads its own copy of extension/dist."""
    return Path(json.loads(temp_browser._state_path().read_text("utf-8"))["profile"]) / "extension" / "build.json"


def _stale(b) -> str | None:
    (info,) = b.status()["extensions"]["temp"].values()
    return info.get("stale")


def test_a_rebuilt_extension_says_to_reload_it(b):
    path = _build_json()
    built = path.read_text("utf-8")
    assert json.loads(built)["build"]  # build.mjs wrote it
    with pytest.raises(WebPilotError) as err:
        b.call("no.such.command")
    assert "older than its build" not in str(err.value)  # the build on disk is the one running

    path.write_text(json.dumps({"build": "000000000000"}), "utf-8")  # as `npm run build` after a code change
    try:
        with pytest.raises(WebPilotError, match=r"unknown command: no\.such\.command; the WebPilot extension "
                                                r"running in the browser is older than its build") as err:
            b.call("no.such.command")
        assert "click reload" in str(err.value)
        deadline = time.monotonic() + 2
        while not _stale(b) and time.monotonic() < deadline:  # the extension tells the daemon after replying
            time.sleep(0.05)
        assert "click reload" in _stale(b)
        assert b.info()  # commands that work still work
    finally:
        path.write_text(built, "utf-8")
    with pytest.raises(WebPilotError) as err:  # a failure checks again: as after a reload
        b.call("no.such.command")
    assert "older than its build" not in str(err.value)
    deadline = time.monotonic() + 2
    while _stale(b) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert _stale(b) is None
