"""blocked_domains, in a browser of its own: another config dir, daemon and temporary browser, with
`blocked_domains: ["localhost"]`. Pages are served on 127.0.0.1, so only `localhost` URLs are blocked."""

import json
import os
import time

import pytest
from helpers import free_port, running_daemon

from webpilot import config, temp_browser
from webpilot.client import Browser, WebPilotError

pytestmark = pytest.mark.e2e

BLOCKED = "domain blocked by WebPilot config: localhost"


@pytest.fixture(scope="module")
def blocked(e2e_env, tmp_path_factory):
    """A Browser on a temporary browser whose config blocks localhost."""
    home = tmp_path_factory.mktemp("webpilot-blocked")
    (home / "config.json").write_text(json.dumps({"blocked_domains": ["localhost"]}), "utf-8")
    port = free_port()
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("WEBPILOT_DIR", str(home))
        mp.setenv("WEBPILOT_PORT", str(port))
        token = config.load()["token"]
        with running_daemon(token, port):
            try:
                temp_browser.start(headless=os.environ.get("WEBPILOT_E2E_HEADED") != "1")
                with Browser("temp", autostart=False) as b:
                    deadline = time.monotonic() + 60
                    while "temp" not in b.status()["extensions"]:
                        assert time.monotonic() < deadline, f"blocked browser did not connect; see {home}"
                        time.sleep(0.2)
                    yield b
            finally:
                temp_browser.stop()


def localhost(site, path: str) -> str:
    return site.url(path).replace("127.0.0.1", "localhost")


def test_goto_a_blocked_domain_is_refused(blocked, site):
    blocked.new_tab()
    for url in (localhost(site, "basic.html"), localhost(site, "basic.html").replace("localhost", "LocalHost.")):
        with pytest.raises(WebPilotError, match=BLOCKED):
            blocked.goto(url)
    with pytest.raises(WebPilotError, match=BLOCKED):
        blocked.new_tab(localhost(site, "basic.html"))
    assert blocked.goto(site.url("basic.html"))["title"] == "Basic"  # other hosts are fine


def test_fetch_to_a_blocked_domain_is_refused(blocked, site):
    blocked.goto(site.url("basic.html"))
    with pytest.raises(WebPilotError, match=BLOCKED):
        blocked.fetch(localhost(site, "api/echo"))
    # A redirect is followed by the browser: the final URL is checked once the response is in.
    with pytest.raises(WebPilotError, match=BLOCKED):
        blocked.fetch(f"/redirect?to={localhost(site, 'api/echo')}")
    assert blocked.fetch("/api/echo")["status"] == 200


def test_a_redirect_to_a_blocked_domain_locks_the_tab(blocked, site):
    blocked.goto(site.url(f"redirect?to={localhost(site, 'nav-b.html')}"))  # lands on localhost
    for read in (blocked.snapshot, blocked.info, lambda: blocked.eval("1")):
        with pytest.raises(WebPilotError, match=BLOCKED):
            read()
    with pytest.raises(WebPilotError, match=BLOCKED):
        blocked.back()
    # A new tab is not blocked.
    assert blocked.new_tab(site.url("nav-a.html"))["title"] == "Nav A"
