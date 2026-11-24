from veupathdb.testing.wire import (
    ACCOUNT_EMAIL,
    FAKE_USER_ID,
    Identity,
    Redactor,
)

IDENTITY = Identity(
    user_id=376543210,
    email="researcher@example.org",
    first_name="Ada",
    last_name="Lovelace",
    organization="Analytical Engines",
)
JWT = "eyJhbGciOiJFUzUxMiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJl"


def test_redaction_removes_every_account_value() -> None:
    body = (
        '{"id": 376543210, "email": "researcher@example.org", "token": "'
        + JWT
        + '", "properties": {"firstName": "Ada", "lastName": "Lovelace",'
        ' "organization": "Analytical Engines"}, "link": "researcher%40example.org"}'
    ).encode()

    redacted = Redactor(IDENTITY).body(body).decode()

    for secret in ("376543210", "researcher", "Ada", "Lovelace", "Analytical", "eyJ"):
        assert secret not in redacted
    assert ACCOUNT_EMAIL in redacted
    assert str(FAKE_USER_ID) in redacted


def test_the_path_names_the_fake_user() -> None:
    path = Redactor(IDENTITY).path("/plasmo.qa/service/users/376543210/steps/12")
    assert path == f"/plasmo.qa/service/users/{FAKE_USER_ID}/steps/12"


def test_a_longer_number_that_holds_the_id_is_kept() -> None:
    body = b'{"stepId": 13765432101}'
    assert Redactor(IDENTITY).body(body) == body


def test_a_name_inside_other_words_is_kept() -> None:
    body = b'{"description": "Adaptive genes"}'
    assert Redactor(IDENTITY).body(body) == body
