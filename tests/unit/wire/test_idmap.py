import json

import pytest

from veupathdb.testing.wire import Exchange
from veupathdb.testing.wire.idmap import IdMap, UnmappedIdError

USERS = "/plasmo.qa/service/users/42"


def _create(path: str) -> Exchange:
    return Exchange(
        seq=0,
        host="qa.plasmodb.org",
        method="POST",
        path=path,
        body="{}",
        credential="registered",
        epoch=0,
        status=200,
    )


def _learned() -> IdMap:
    ids = IdMap(user_id=42)
    ids.learn(_create(f"{USERS}/steps"), b'{"id": 100}', b'{"id": 900}')
    ids.learn(_create(f"{USERS}/steps"), b'{"id": 101}', b'{"id": 901}')
    ids.learn(_create(f"{USERS}/datasets"), b'{"id": 555}', b'{"id": 777}')
    ids.learn(_create(f"{USERS}/strategies"), b'{"id": 100}', b'{"id": 300}')
    return ids


def test_a_minted_step_is_rewritten_in_paths() -> None:
    assert _learned().rewrite_path(f"{USERS}/steps/100/reports/standard") == (
        f"{USERS}/steps/900/reports/standard"
    )


def test_an_id_is_rewritten_by_its_kind() -> None:
    assert (
        _learned().rewrite_path(f"{USERS}/strategies/100") == f"{USERS}/strategies/300"
    )


def test_a_percent_encoded_segment_is_read_as_its_id() -> None:
    assert _learned().rewrite_path(f"{USERS}/steps/%31%30%30") == f"{USERS}/steps/900"


def test_a_number_outside_an_owned_segment_is_kept() -> None:
    path = "/plasmo.qa/service/record-types/gene/searches/100"
    assert _learned().rewrite_path(path) == path


def test_a_step_tree_is_rewritten() -> None:
    body = json.dumps(
        {
            "stepTree": {
                "stepId": 101,
                "primaryInput": {"stepId": 100},
                "secondaryInput": {"stepId": "100"},
            }
        }
    )
    assert json.loads(_learned().rewrite_body(body)) == {
        "stepTree": {
            "stepId": 901,
            "primaryInput": {"stepId": 900},
            "secondaryInput": {"stepId": "900"},
        }
    }


def test_a_dataset_parameter_is_rewritten_and_other_values_are_kept() -> None:
    body = json.dumps(
        {
            "searchConfig": {
                "parameters": {"ds_gene_ids": "555", "min": "100x", "s": "100"}
            }
        }
    )
    assert json.loads(_learned().rewrite_body(body)) == {
        "searchConfig": {
            "parameters": {"ds_gene_ids": "777", "min": "100x", "s": "100"}
        }
    }


def test_an_id_no_write_minted_is_an_error() -> None:
    ids = _learned()
    with pytest.raises(UnmappedIdError, match="314"):
        ids.check("GET", f"{USERS}/steps/314", [], None)
    with pytest.raises(UnmappedIdError, match="315"):
        ids.check(
            "POST", f"{USERS}/strategies", [], json.dumps({"stepTree": {"stepId": 315}})
        )
    with pytest.raises(UnmappedIdError, match="316"):
        ids.check("GET", f"{USERS}/steps/900", [("stepId", "316")], None)


def test_an_id_of_another_kind_is_an_error() -> None:
    with pytest.raises(UnmappedIdError, match="777"):
        _learned().check("DELETE", f"{USERS}/steps/777", [], None)


def test_a_write_that_names_nothing_minted_is_refused() -> None:
    with pytest.raises(UnmappedIdError, match="preferences"):
        _learned().check("PUT", f"{USERS}/preferences", [], "{}")


def test_a_write_to_another_user_is_refused() -> None:
    with pytest.raises(UnmappedIdError, match="user 43"):
        _learned().check("POST", "/plasmo.qa/service/users/43/steps", [], "{}")


def test_a_recognized_create_and_a_minted_id_pass() -> None:
    ids = _learned()
    ids.check("POST", f"{USERS}/steps", [], '{"searchName": "a"}')
    ids.check("POST", "/plasmo.qa/service/users/current/steps", [], "{}")
    ids.check("DELETE", f"{USERS}/steps/900", [("stepId", "901")], None)
    ids.check("GET", "/plasmo.qa/service/record-types/gene/records", [], None)


def test_live_ids_are_what_was_minted_and_not_deleted() -> None:
    ids = _learned()
    ids.forget(f"{USERS}/steps/900")
    assert ids.live() == [("steps", "901"), ("datasets", "777"), ("strategies", "300")]
    assert ids.sweep_paths() == [
        ("qa.plasmodb.org", f"{USERS}/steps/901"),
        ("qa.plasmodb.org", f"{USERS}/datasets/777"),
        ("qa.plasmodb.org", f"{USERS}/strategies/300"),
    ]
