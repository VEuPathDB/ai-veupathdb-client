from __future__ import annotations

import pytest
from pydantic import JsonValue, TypeAdapter

from veupathdb.devtools.fixtures import (
    ENFORCED_SCHEMAS,
    load_schema_pin,
    main,
    schema_checks,
    schema_file,
    schema_pin_drift,
    verify_body,
)
from veupathdb.testing.wdk_fixtures import (
    FIXTURES,
    SCHEMA_DIR,
    FixtureRequest,
    fixture_request,
    load_recorded,
)

_RECORD_TYPES: TypeAdapter[list[str]] = TypeAdapter(list[str])
_RECORD_TYPE: TypeAdapter[dict[str, JsonValue]] = TypeAdapter(dict[str, JsonValue])


def test_a_schema_annotation_name_resolves_to_its_upstream_file() -> None:
    assert schema_file("wdk.records.name.get") == "wdk/records/name/get.json"
    assert (
        schema_file("wdk.standard-post-response") == "wdk/standard-post-response.json"
    )


def test_the_vendored_tree_is_byte_identical_to_the_pin() -> None:
    assert schema_pin_drift(load_schema_pin()) == ()


def test_the_vendored_tree_holds_exactly_the_pinned_files() -> None:
    pin = load_schema_pin()
    on_disk = {
        path.relative_to(SCHEMA_DIR).as_posix() for path in SCHEMA_DIR.rglob("*.json")
    }
    assert on_disk == set(pin.files)
    assert len(pin.files) == 41


def test_the_pin_covers_every_enforced_schema_and_its_refs() -> None:
    pinned = set(load_schema_pin().files)
    assert {schema_file(name) for name in ENFORCED_SCHEMAS} <= pinned
    assert len(ENFORCED_SCHEMAS) == 14


def test_a_fixture_only_binds_a_schema_wdk_enforces() -> None:
    bound = {
        name
        for request in FIXTURES
        for name in (request.in_schema, request.out_schema)
        if name is not None
    }
    assert bound == {
        "wdk.answer.post-request",
        "wdk.records.get",
        "wdk.records.name.get",
    }
    assert bound <= set(ENFORCED_SCHEMAS)
    assert {schema_file(name) for name in bound} <= set(load_schema_pin().files)


def test_every_recorded_fixture_passes_the_schema_its_endpoint_binds() -> None:
    failures = {
        (check.fixture, check.direction): check.errors
        for check in schema_checks()
        if check.errors
    }
    assert failures == {}


def test_each_binding_is_checked_in_the_direction_wdk_validates() -> None:
    checked = {
        (check.fixture, check.direction, check.schema_name) for check in schema_checks()
    }
    assert checked == {
        ("record_types", "response", "wdk.records.get"),
        ("record_type_build", "response", "wdk.records.name.get"),
        ("answer_report_by_molecular_weight", "request", "wdk.answer.post-request"),
    }


def test_a_recorded_list_response_with_one_wrong_element_fails() -> None:
    segments = _RECORD_TYPES.validate_python(load_recorded("record_types").json_body())
    errors = verify_body("wdk.records.get", [*segments, 7])
    assert len(errors) == 1
    assert errors[0].endswith("is not valid under any of the given schemas")


def test_a_recorded_object_response_with_a_retyped_field_fails() -> None:
    body = _RECORD_TYPE.validate_python(load_recorded("record_type_build").json_body())
    body["urlSegment"] = 4
    assert verify_body("wdk.records.name.get", body) == (
        "urlSegment: 4 is not of type 'string'",
    )


def test_a_recorded_object_response_with_an_extra_field_fails() -> None:
    body = _RECORD_TYPE.validate_python(load_recorded("record_type_build").json_body())
    body["notAWdkField"] = "x"
    assert verify_body("wdk.records.name.get", body) == (
        "<root>: Additional properties are not allowed ('notAWdkField' was unexpected)",
    )


def test_a_request_body_missing_a_required_member_fails() -> None:
    body = dict(fixture_request("answer_report_by_molecular_weight").body or {})
    del body["reportConfig"]
    assert verify_body("wdk.answer.post-request", body) == (
        "<root>: 'reportConfig' is a required property",
    )


def test_a_request_body_with_a_non_string_parameter_fails() -> None:
    body = dict(fixture_request("answer_report_by_molecular_weight").body or {})
    body["searchConfig"] = {"parameters": {"organism": 3}}
    assert verify_body("wdk.answer.post-request", body) == (
        "searchConfig/parameters/organism: 3 is not of type 'string'",
    )


def test_a_schema_the_pin_does_not_carry_is_refused() -> None:
    with pytest.raises(KeyError, match=r"wdk/users/id/get\.json"):
        verify_body("wdk.users.id.get", {})


def test_an_in_schema_without_a_request_body_is_refused() -> None:
    with pytest.raises(ValueError, match="an in_schema describes a request body"):
        FixtureRequest(
            name="bodyless",
            path="/record-types",
            reads="WDK-HTTP-004",
            method="POST",
            in_schema="wdk.answer.post-request",
        )


def test_the_verify_command_passes_over_the_whole_store() -> None:
    assert main(["verify"]) == 0
