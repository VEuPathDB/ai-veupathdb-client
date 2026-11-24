import json
from pathlib import Path

from mitmproxy import http
from tests.unit.wire._flows import PLASMO, SERVICE, answer, answered_json, control, flow

from veupathdb.testing.wire import ACCOUNT_EMAIL, FAKE_USER_ID, STACK, WireStore
from veupathdb.testing.wire.addon import WireAddon
from veupathdb.testing.wire.signing import SigningKey

CASSETTE = "feature@plasmodb/a.spec.ts/one-1"
REAL_ID = 376543210
EMAIL = "researcher@example.org"
QA_KEY = SigningKey.generate()
TOKEN = QA_KEY.sign({"sub": str(REAL_ID), "is_guest": False, "exp": 4102444800})
AUTH = {"cookie": f"Authorization={TOKEN}; JSESSIONID=SESSIONVALUE1234"}


def _round_trip(
    addon: WireAddon,
    method: str,
    path: str,
    status: int,
    body: object,
    sent: bytes = b"",
) -> http.HTTPFlow:
    made = flow(method, f"https://{PLASMO}{path}", sent, AUTH)
    addon.request(made)
    assert made.response is None
    made.response = http.Response.make(
        status,
        json.dumps(body).encode(),
        {
            "content-type": "application/json",
            "set-cookie": "JSESSIONID=SESSIONVALUE1234; Path=/",
        },
    )
    addon.response(made)
    return made


def _recorder(tmp_path: Path) -> WireAddon:
    addon = WireAddon("record", WireStore(tmp_path), frozenset({PLASMO}))
    _round_trip(
        addon,
        "GET",
        f"{SERVICE}/users/current",
        200,
        {
            "id": REAL_ID,
            "email": EMAIL,
            "isGuest": False,
            "properties": {"firstName": "Ada"},
        },
    )
    _round_trip(addon, "GET", SERVICE, 200, {"buildNumber": 69})
    return addon


def test_a_passing_test_is_written_redacted(tmp_path: Path) -> None:
    addon = _recorder(tmp_path)
    addon.request(control("POST", "begin", {"cassette": CASSETTE}))
    _round_trip(
        addon,
        "POST",
        f"{SERVICE}/users/{REAL_ID}/steps",
        200,
        {"id": 7, "owner": EMAIL, "displayName": "Ada"},
        json.dumps({"searchName": "GenesByTaxon"}).encode(),
    )
    _round_trip(addon, "GET", f"{SERVICE}/users/{REAL_ID}/steps/7", 200, {"id": 7})
    end = control("POST", "end", {"cassette": CASSETTE, "keep": True})
    addon.request(end)
    finish = control("POST", "finish")
    addon.request(finish)

    assert answered_json(end) == {"written": True}
    store = WireStore(tmp_path)
    cassette = store.read_cassette(CASSETTE)
    assert cassette is not None
    assert [(e.method, e.path, e.epoch, e.set_cookies) for e in cassette.exchanges] == [
        ("POST", f"{SERVICE}/users/{FAKE_USER_ID}/steps", 0, ["JSESSIONID"]),
        ("GET", f"{SERVICE}/users/{FAKE_USER_ID}/steps/7", 1, ["JSESSIONID"]),
    ]
    assert cassette.header.builds == {PLASMO: 69}
    response = cassette.exchanges[0].response
    assert response is not None
    assert json.loads(store.read_body(response)) == {
        "id": 7,
        "owner": ACCOUNT_EMAIL,
        "displayName": "E2E",
    }
    everything = b"".join(path.read_bytes() for path in tmp_path.rglob("*.jsonl"))
    for secret in (str(REAL_ID).encode(), EMAIL.encode(), b"SESSIONVALUE1234", b"eyJ"):
        assert secret not in everything
    stack = store.read_cassette(STACK)
    assert stack is not None
    assert [e.path for e in stack.exchanges] == [SERVICE]
    assert store.read_manifest().cassettes == 1


def test_a_failed_test_is_not_written(tmp_path: Path) -> None:
    addon = _recorder(tmp_path)
    addon.request(control("POST", "begin", {"cassette": CASSETTE}))
    _round_trip(addon, "GET", f"{SERVICE}/users/{REAL_ID}/steps/7", 200, {"id": 7})
    end = control("POST", "end", {"cassette": CASSETTE, "keep": False})
    addon.request(end)

    assert answered_json(end) == {"written": False}
    assert WireStore(tmp_path).read_cassette(CASSETTE) is None


def test_a_recorder_that_never_saw_the_account_writes_nothing(tmp_path: Path) -> None:
    addon = WireAddon("record", WireStore(tmp_path), frozenset({PLASMO}))
    addon.request(control("POST", "begin", {"cassette": CASSETTE}))
    _round_trip(addon, "GET", f"{SERVICE}/users/{REAL_ID}/steps/7", 200, {"id": 7})
    end = control("POST", "end", {"cassette": CASSETTE})
    addon.request(end)

    assert answer(end).status_code == 500
    assert list(tmp_path.rglob("*.jsonl")) == []


def test_a_leak_the_redactor_misses_is_refused(tmp_path: Path) -> None:
    addon = _recorder(tmp_path)
    addon.request(control("POST", "begin", {"cassette": CASSETTE}))
    _round_trip(
        addon, "GET", f"{SERVICE}/x", 200, {"note": "res&#101;archer@example.org"}
    )
    end = control("POST", "end", {"cassette": CASSETTE})
    addon.request(end)

    assert answer(end).status_code == 500
    outcome = answered_json(end)
    assert isinstance(outcome, dict)
    assert "email" in outcome["error"]
    assert WireStore(tmp_path).read_cassette(CASSETTE) is None


def test_the_login_and_the_current_user_are_never_recorded(tmp_path: Path) -> None:
    addon = _recorder(tmp_path)
    _round_trip(addon, "POST", f"{SERVICE}/login", 302, {})
    addon.request(control("POST", "finish"))
    stack = WireStore(tmp_path).read_cassette(STACK)
    assert stack is not None
    assert [e.path for e in stack.exchanges] == [SERVICE]


def test_an_auth_key_header_is_a_secret(tmp_path: Path) -> None:
    addon = _recorder(tmp_path)
    addon.request(control("POST", "begin", {"cassette": CASSETTE}))
    made = flow(
        "GET",
        f"https://{PLASMO}/eda/apps",
        b"",
        {**AUTH, "Auth-Key": "OPAQUEEDAKEY42"},
    )
    addon.request(made)
    made.response = http.Response.make(200, b'{"echo": "opaqueedakey42"}', {})
    addon.response(made)
    end = control("POST", "end", {"cassette": CASSETTE})
    addon.request(end)

    assert answered_json(end) == {"written": True}
    cassette = WireStore(tmp_path).read_cassette(CASSETTE)
    assert cassette is not None
    response = cassette.exchanges[0].response
    assert response is not None
    assert WireStore(tmp_path).read_body(response) == b'{"echo": "wire-redacted"}'
