"""blocked_domains, in a browser of its own: another config dir, daemon and temporary browser, with
`blocked_domains: ["localhost"]`. Pages are served on 127.0.0.1, so only `localhost` URLs are blocked."""

import pytest
from helpers import own_browser

from webpilot.client import WebPilotError

pytestmark = [pytest.mark.e2e, pytest.mark.xdist_group("blocked")]  # its browser starts once, on one worker

BLOCKED = "domain blocked by WebPilot config: localhost"


@pytest.fixture(scope="module")
def blocked(e2e_env, tmp_path_factory):
    """A Browser on a temporary browser whose config blocks localhost."""
    with own_browser(tmp_path_factory.mktemp("webpilot-blocked"), {"blocked_domains": ["localhost"]}) as b:
        yield b


def localhost(site, path: str) -> str:
    return site.url(path).replace("127.0.0.1", "localhost")


def test_goto_a_blocked_domain_is_refused(blocked, site):
    blocked.new_tab()
    for url in (localhost(site, "basic.html"), localhost(site, "basic.html").replace("localhost", "LocalHost.")):
        with pytest.raises(WebPilotError, match=BLOCKED):
            blocked.goto(url)
    with pytest.raises(WebPilotError, match=BLOCKED):
        blocked.new_tab(localhost(site, "basic.html"))
    with pytest.raises(WebPilotError, match=BLOCKED):  # judged by the page it shows
        blocked.goto("view-source:" + localhost(site, "basic.html"))
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
    # The goto itself fails once the tab lands there, without reporting the page's title.
    with pytest.raises(WebPilotError, match=f"the tab went to a page off limits \({BLOCKED}\)") as e:
        blocked.goto(site.url(f"redirect?to={localhost(site, 'nav-b.html')}"))
    assert "Nav B" not in str(e.value)
    for read in (blocked.snapshot, blocked.info, lambda: blocked.eval("1")):
        with pytest.raises(WebPilotError, match=BLOCKED):
            read()
    with pytest.raises(WebPilotError, match=BLOCKED):
        blocked.back()
    # A new tab is not blocked.
    assert blocked.new_tab(site.url("nav-a.html"))["title"] == "Nav A"
