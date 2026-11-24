from veupathdb.testing.wire import canonical_body, exchange_key

HOST = "qa.plasmodb.org"
PATH = "/plasmo.qa/service/users/900000001/steps"


def _key(body: bytes, query: list[tuple[str, str]] | None = None) -> str:
    return exchange_key(HOST, "POST", PATH, query or [], body)


def test_the_query_order_does_not_change_the_key() -> None:
    first = _key(b"", [("b", "2"), ("a", "1")])
    second = _key(b"", [("a", "1"), ("b", "2")])
    assert first == second


def test_a_datetime_and_key_order_do_not_change_the_key() -> None:
    first = _key(b'{"b": 1, "a": "2026-11-24T10:00:00Z"}')
    second = _key(b'{"a":"2027-01-01T00:00:00.123+00:00","b":1}')
    assert first == second


def test_a_uuid_does_not_change_the_key() -> None:
    first = _key(b'{"name": "0b6c1c2e-8f5d-4a53-9a42-0c1d2e3f4a5b"}')
    second = _key(b'{"name": "f47ac10b-58cc-4372-a567-0e02b2c3d479"}')
    assert first == second


def test_a_number_changes_the_key() -> None:
    assert _key(b'{"stepId": 5}') != _key(b'{"stepId": 6}')


def test_a_multipart_boundary_does_not_change_the_key() -> None:
    def part(boundary: str) -> bytes:
        return (
            f'--{boundary}\r\nContent-Disposition: form-data; name="a"\r\n\r\n1\r\n'
            f"--{boundary}--\r\n"
        ).encode()

    assert _key(part("a1b2c3d4e5f6")) == _key(part("0f9e8d7c6b5a"))


def test_a_body_that_is_not_json_is_kept_as_its_bytes() -> None:
    assert canonical_body(b"GENE1\nGENE2\n") == "GENE1\nGENE2\n"
    assert _key(b"GENE1\n") != _key(b"GENE2\n")


def test_the_method_host_and_path_are_in_the_key() -> None:
    other_path = exchange_key(HOST, "POST", PATH + "/7", [], b"")
    other_host = exchange_key("qa.toxodb.org", "POST", PATH, [], b"")
    other_method = exchange_key(HOST, "GET", PATH, [], b"")
    assert len({_key(b""), other_path, other_host, other_method}) == 4
