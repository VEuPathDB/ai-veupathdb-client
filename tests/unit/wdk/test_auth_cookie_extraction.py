import base64
import json

from veupathdb.wdk.auth_login import (
    _is_guest_jwt,
    extract_auth_cookie,
)


def _mk_jwt(is_guest: bool, sub: str = "123") -> str:
    header = (
        base64.urlsafe_b64encode(
            json.dumps({"alg": "ES512"}).encode(),
        )
        .rstrip(b"=")
        .decode()
    )
    payload = (
        base64.urlsafe_b64encode(
            json.dumps({"sub": sub, "is_guest": is_guest}).encode(),
        )
        .rstrip(b"=")
        .decode()
    )
    return f"{header}.{payload}.sig"


def test_is_guest_jwt_true() -> None:
    assert _is_guest_jwt(_mk_jwt(is_guest=True)) is True


def test_is_guest_jwt_false() -> None:
    assert _is_guest_jwt(_mk_jwt(is_guest=False)) is False


def test_is_guest_jwt_malformed_is_treated_as_guest() -> None:
    assert _is_guest_jwt("not.a.jwt") is True
    assert _is_guest_jwt("") is True


def test_extract_picks_non_guest_over_guest_when_both_present() -> None:
    guest = _mk_jwt(is_guest=True, sub="guest-1")
    real = _mk_jwt(is_guest=False, sub="real-1")
    headers = [
        f"Authorization={guest};Version=1;Path=/;Max-Age=94608000",
        f"Authorization={real};Version=1;Path=/;Max-Age=94608000",
    ]
    assert extract_auth_cookie(headers) == real


def test_extract_prefers_non_guest_regardless_of_order() -> None:
    guest = _mk_jwt(is_guest=True, sub="guest-1")
    real = _mk_jwt(is_guest=False, sub="real-1")
    headers = [
        f"Authorization={real};Path=/",
        f"Authorization={guest};Path=/",
    ]
    assert extract_auth_cookie(headers) == real


def test_extract_returns_none_when_only_guest_present() -> None:
    guest = _mk_jwt(is_guest=True)
    headers = [f"Authorization={guest};Path=/"]
    assert extract_auth_cookie(headers) is None


def test_extract_returns_none_when_no_authorization_cookie() -> None:
    headers = ["wdk_check_auth=;Path=/;Max-Age=0"]
    assert extract_auth_cookie(headers) is None


def test_extract_ignores_unrelated_cookies() -> None:
    real = _mk_jwt(is_guest=False)
    headers = [
        "sessionid=abc;Path=/",
        f"Authorization={real};Path=/",
        "other=xyz;Path=/",
    ]
    assert extract_auth_cookie(headers) == real
