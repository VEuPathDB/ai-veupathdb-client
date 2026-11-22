"""A site that answers a service call with a page, not JSON, is a typed WDK error."""

from __future__ import annotations

import httpx
import pytest

from veupathdb.errors import WDKError
from veupathdb.wdk._http import HTTPClient

_SERVICE = "https://qa.plasmodb.org/plasmo.qa/service"
_LOGIN = "https://login.example.org/auth/bin/autologin?redirectUrl=x"
_LOGIN_PAGE = "<html><body>Pre-release login: secret-form-token</body></html>"


class _Site:
    def __init__(self, *, redirects: bool) -> None:
        self.redirects = redirects
        self.served: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.served.append(str(request.url))
        if request.url.host == "login.example.org":
            return httpx.Response(
                200, text=_LOGIN_PAGE, headers={"content-type": "text/html"}
            )
        if "/app" in request.url.path:
            return httpx.Response(200, text="")
        if self.redirects:
            return httpx.Response(307, headers={"location": _LOGIN})
        return httpx.Response(
            200, text=_LOGIN_PAGE, headers={"content-type": "text/html;charset=UTF-8"}
        )


async def _refused(site: _Site) -> WDKError:
    client = HTTPClient(
        base_url=_SERVICE, auth_token="registered", transport=httpx.MockTransport(site)
    )
    try:
        with pytest.raises(WDKError) as refused:
            await client.get("/record-types", attempts=1)
    finally:
        await client.close()
    return refused.value


async def test_a_page_in_place_of_json_names_the_url_status_and_type() -> None:
    refusal = await _refused(_Site(redirects=False))

    assert refusal.detail == (
        f"GET {_SERVICE}/record-types answered 200 with "
        "text/html;charset=UTF-8, not JSON."
    )
    assert "secret-form-token" not in str(refusal)
    assert refusal.__cause__ is None


async def test_a_redirect_off_the_site_is_refused_before_the_page_is_read() -> None:
    site = _Site(redirects=True)

    refusal = await _refused(site)

    assert refusal.detail == (
        f"GET {_SERVICE}/record-types answered 307 with a redirect to "
        "login.example.org, off the site's service."
    )
    assert not any("login.example.org" in url for url in site.served)
