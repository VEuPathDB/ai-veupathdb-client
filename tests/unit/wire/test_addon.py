import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import respx
from httpx import Response
from mitmproxy import http
from tests.unit.wire._flows import (
    PLASMO,
    SERVICE,
    answer,
    answered_json,
    control,
    flow,
    registered,
)

from veupathdb.testing import HERMETIC_GUEST_TOKEN
from veupathdb.testing.wire import (
    ACCOUNT_EMAIL,
    FAKE_USER_ID,
    STACK,
    Cassette,
    CassetteHeader,
    Exchange,
    WireStore,
)
from veupathdb.testing.wire.addon import WireAddon, cassette_email
from veupathdb.wdk import validate_oauth_token

CASSETTE = "feature@plasmodb/a.spec.ts/one-1"
HOSTS = frozenset({PLASMO})
STEPS = f"{SERVICE}/users/{FAKE_USER_ID}/steps"


def _recorded(
    store: WireStore, cassette: str, *exchanges: tuple[Exchange, bytes]
) -> None:
    store.write_cassette(
        Cassette(
            header=CassetteHeader(cassette=cassette, recorded_at=datetime.now(UTC)),
            exchanges=[
                e.model_copy(update={"response": store.put_body(body)})
                for e, body in exchanges
            ],
        )
    )


def _exchange(
    seq: int, method: str, path: str, body: str | None = None, **kw: object
) -> Exchange:
    fields: dict[str, object] = {
        "seq": seq,
        "host": PLASMO,
        "method": method,
        "path": path,
        "body": body,
        "credential": "registered",
        "epoch": 0,
        "status": 200,
        "content_type": "application/json",
        **kw,
    }
    return Exchange.model_validate(fields)


@pytest.fixture
def store(tmp_path: Path) -> WireStore:
    return WireStore(tmp_path)


def _replay(store: WireStore) -> WireAddon:
    addon = WireAddon("replay", store, HOSTS)
    addon.request(control("POST", "begin", {"cassette": CASSETTE}))
    return addon


def _send(
    addon: WireAddon,
    method: str,
    path: str,
    body: bytes = b"",
    cassette: str | None = CASSETTE,
) -> http.HTTPFlow:
    made = flow(
        method, f"https://{PLASMO}{path}", body, registered(addon.key, cassette)
    )
    addon.request(made)
    return made


def test_a_recorded_request_replays_its_answer(store: WireStore) -> None:
    _recorded(
        store,
        CASSETTE,
        (_exchange(0, "GET", f"{STEPS}/7"), b'{"id": 7, "estimatedSize": 12}'),
    )
    addon = _replay(store)

    made = _send(addon, "GET", f"{STEPS}/7")

    assert answer(made).status_code == 200
    assert answered_json(made) == {"id": 7, "estimatedSize": 12}
    assert answer(made).headers["content-type"] == "application/json"


def test_an_unrecorded_request_is_a_418(store: WireStore) -> None:
    addon = _replay(store)

    made = _send(addon, "POST", STEPS, b'{"searchName": "GenesByTaxon"}')
    end = control("POST", "end", {"cassette": CASSETTE})
    addon.request(end)

    assert answer(made).status_code == 418
    assert answer(made).headers["X-Wire-Miss"] == "1"
    assert answered_json(made) == {
        "wireMiss": True,
        "cassette": CASSETTE,
        "method": "POST",
        "host": PLASMO,
        "path": STEPS,
        "reason": "unrecorded",
        "nearest": "",
        "differences": [],
    }
    outcome = answered_json(end)
    assert isinstance(outcome, dict)
    assert [m["path"] for m in outcome["misses"]] == [STEPS]
    assert outcome["report"].startswith("WDK replay: 1 request has no recording")


def test_a_host_off_the_allowlist_is_a_stack_miss(store: WireStore) -> None:
    addon = _replay(store)
    made = flow("GET", "https://example.org/anything")
    addon.request(made)
    finish = control("POST", "finish")
    addon.request(finish)

    assert answer(made).status_code == 418
    outcome = answered_json(finish)
    assert isinstance(outcome, dict)
    assert [(m["host"], m["reason"]) for m in outcome["misses"]] == [
        ("example.org", "host")
    ]


def test_a_request_without_a_token_reads_the_stack(store: WireStore) -> None:
    root = _exchange(
        0,
        "GET",
        SERVICE,
        credential="none",
        set_cookies=["Authorization", "JSESSIONID"],
    )
    _recorded(store, STACK, (root, b'{"buildNumber": 69}'))
    addon = WireAddon("replay", store, HOSTS)

    made = flow("GET", f"https://{PLASMO}{SERVICE}")
    addon.request(made)

    assert answered_json(made) == {"buildNumber": 69}
    assert answer(made).headers.get_all("set-cookie") == [
        f"Authorization={HERMETIC_GUEST_TOKEN}; Path=/",
        "JSESSIONID=wire-redacted; Path=/",
    ]


def test_a_registered_token_with_no_cassette_is_refused(store: WireStore) -> None:
    addon = _replay(store)
    made = _send(addon, "GET", f"{STEPS}/7", cassette=None)
    assert answer(made).status_code == 418
    assert answered_json(made) == {
        "wireMiss": True,
        "cassette": STACK,
        "method": "GET",
        "host": PLASMO,
        "path": f"{STEPS}/7",
        "reason": "no-cassette",
        "nearest": "",
        "differences": [],
    }


def test_the_current_user_is_the_cassettes_own(store: WireStore) -> None:
    addon = _replay(store)
    made = _send(addon, "GET", f"{SERVICE}/users/current")
    assert answered_json(made) == {
        "id": FAKE_USER_ID,
        "email": cassette_email(CASSETTE),
        "isGuest": False,
        "properties": {
            "firstName": "E2E",
            "lastName": "Account",
            "organization": "Strategist e2e",
        },
    }
    assert cassette_email(CASSETTE).startswith("e2e+")
    assert cassette_email(CASSETTE).endswith("@strategist.test")


def test_the_account_email_becomes_the_cassettes_own(store: WireStore) -> None:
    recorded = _exchange(
        0, "POST", f"{SERVICE}/x", body=json.dumps({"to": ACCOUNT_EMAIL})
    )
    _recorded(
        store, CASSETTE, (recorded, json.dumps({"email": ACCOUNT_EMAIL}).encode())
    )
    addon = _replay(store)

    sent = json.dumps({"to": cassette_email(CASSETTE)}).encode()
    made = _send(addon, "POST", f"{SERVICE}/x", sent)

    assert answered_json(made) == {"email": cassette_email(CASSETTE)}


async def test_the_jwks_verifies_a_token_the_key_signed(store: WireStore) -> None:
    addon = _replay(store)
    jwks = flow("GET", "https://auth.veupathdb.org/jwks")
    addon.request(jwks)
    key = flow("GET", "http://localhost:8080/__wire/signing-key")
    addon.request(key)
    private = answered_json(key)
    assert isinstance(private, dict)
    assert {"d", "x", "y"} <= private.keys()

    token = addon.key.sign({"sub": "e2e", "is_guest": False, "exp": 4102444800})
    with respx.mock:
        respx.get("https://auth.veupathdb.org/jwks").mock(
            return_value=Response(200, content=answer(jwks).content)
        )
        claims = await validate_oauth_token(token, "https://auth.veupathdb.org")

    assert claims is not None
    assert claims.is_guest is False


def test_openai_answers_a_bad_key(store: WireStore) -> None:
    addon = _replay(store)
    made = flow("POST", "https://api.openai.com/v1/responses", b"{}")
    addon.request(made)
    assert answer(made).status_code == 401


def test_begin_rewinds_the_cassette(store: WireStore) -> None:
    write = _exchange(0, "POST", STEPS, body='{"searchName": "a"}')
    _recorded(store, CASSETTE, (write, b'{"id": 7}'))
    addon = _replay(store)
    first = _send(addon, "POST", STEPS, b'{"searchName": "a"}')
    used_up = _send(addon, "POST", STEPS, b'{"searchName": "a"}')
    addon.request(control("POST", "begin", {"cassette": CASSETTE}))
    retried = _send(addon, "POST", STEPS, b'{"searchName": "a"}')

    assert answer(first).status_code == 200
    assert answer(used_up).status_code == 418
    assert answered_json(used_up) == {
        "wireMiss": True,
        "cassette": CASSETTE,
        "method": "POST",
        "host": PLASMO,
        "path": STEPS,
        "reason": "used-up",
        "nearest": f"POST {PLASMO} {STEPS}",
        "differences": [],
    }
    assert answer(retried).status_code == 200


def test_a_recorded_write_never_sent_fails_the_end(store: WireStore) -> None:
    _recorded(store, CASSETTE, (_exchange(0, "DELETE", f"{STEPS}/7"), b""))
    addon = _replay(store)
    end = control("POST", "end", {"cassette": CASSETTE})
    addon.request(end)
    outcome = answered_json(end)
    assert isinstance(outcome, dict)
    assert [u["path"] for u in outcome["unsent"]] == [f"{STEPS}/7"]
