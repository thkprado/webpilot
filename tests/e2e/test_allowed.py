"""allowed_domains, in a browser of its own, with `allowed_domains: ["localhost"]` and
`blocked_domains: ["no.localhost"]`. Pages are served on 127.0.0.1, which is not allowed; `localhost` and its
subdomains reach the same server (the browser resolves *.localhost to the loopback address)."""

import pytest
from helpers import own_browser

from webpilot.client import WebPilotError

pytestmark = [pytest.mark.e2e, pytest.mark.xdist_group("allowed")]  # its browser starts once, on one worker

OUTSIDE = "domain not in allowed_domains of the WebPilot config: 127.0.0.1; ask the user"


@pytest.fixture(scope="module")
def allowed(e2e_env, tmp_path_factory):
    cfg = {"allowed_domains": ["localhost"], "blocked_domains": ["no.localhost"]}
    with own_browser(tmp_path_factory.mktemp("webpilot-allowed"), cfg) as b:
        yield b


def on(site, path: str, host: str = "localhost") -> str:
    return site.url(path).replace("127.0.0.1", host)


def test_only_allowed_domains_open(allowed, site):
    assert allowed.new_tab()["url"] == "about:blank"
    assert allowed.goto(on(site, "basic.html"))["title"] == "Basic"
    assert allowed.goto(on(site, "nav-a.html", "a.localhost"))["title"] == "Nav A"  # a subdomain
    with pytest.raises(WebPilotError, match=OUTSIDE):
        allowed.goto(site.url("basic.html"))
    with pytest.raises(WebPilotError, match=OUTSIDE):
        allowed.new_tab(site.url("basic.html"))
    with pytest.raises(WebPilotError, match="domain blocked by WebPilot config: no.localhost"):  # blocked wins
        allowed.goto(on(site, "basic.html", "no.localhost"))
    with pytest.raises(WebPilotError, match="not in allowed_domains of the WebPilot config: file: URL"):
        allowed.goto("file:///C:/")
    with pytest.raises(WebPilotError, match=r"opens www\.google\.com: it must be in allowed_domains"):
        allowed.search("anything")
    assert allowed.info()["title"] == "Nav A"  # nothing above left the page


def test_fetch_outside_the_allowed_domains_is_refused(allowed, site):
    allowed.goto(on(site, "basic.html"))
    with pytest.raises(WebPilotError, match=OUTSIDE):
        allowed.fetch(site.url("api/echo"))
    with pytest.raises(WebPilotError, match=OUTSIDE):  # checked again after the redirect
        allowed.fetch(f"/redirect?to={site.url('api/echo')}")
    assert allowed.fetch("/api/echo")["status"] == 200


def test_a_click_that_leaves_the_allowed_domains_fails_and_locks_the_tab(allowed, site):
    allowed.goto(on(site, "nav-a.html"))
    allowed.eval(f"document.body.insertAdjacentHTML('beforeend', '<a id=out href={site.url('nav-b.html')}>Out</a>')")
    with pytest.raises(WebPilotError, match=rf"the tab went to a page off limits \({OUTSIDE}\)") as e:
        allowed.click("#out")
    assert "Nav B" not in str(e.value)
    with pytest.raises(WebPilotError, match=OUTSIDE):
        allowed.snapshot()
    assert allowed.new_tab(on(site, "nav-a.html"))["title"] == "Nav A"
