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
    ids = IdMap()
    ids.learn(_create(f"{USERS}/steps"), b'{"id": 100}', b'{"id": 900}')
    ids.learn(_create(f"{USERS}/steps"), b'{"id": 101}', b'{"id": 901}')
    ids.learn(_create(f"{USERS}/datasets"), b'{"id": 555}', b'{"id": 777}')
    return ids


def test_a_minted_step_is_rewritten_in_paths() -> None:
    assert _learned().rewrite_path(f"{USERS}/steps/100/reports/standard") == (
        f"{USERS}/steps/900/reports/standard"
    )


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
                "parameters": {"ds_gene_ids": "555", "min": "100x", "n": "5"}
            }
        }
    )
    assert json.loads(_learned().rewrite_body(body)) == {
        "searchConfig": {"parameters": {"ds_gene_ids": "777", "min": "100x", "n": "5"}}
    }


def test_an_id_no_write_minted_is_an_error() -> None:
    ids = _learned()
    with pytest.raises(UnmappedIdError, match="314"):
        ids.check(f"{USERS}/steps/314", None)
    with pytest.raises(UnmappedIdError, match="315"):
        ids.check(f"{USERS}/strategies", json.dumps({"stepTree": {"stepId": 315}}))


def test_a_mapped_id_passes_the_check() -> None:
    ids = _learned()
    ids.check(f"{USERS}/steps/900", json.dumps({"stepTree": {"stepId": 901}}))


def test_live_ids_are_what_was_minted_and_not_deleted() -> None:
    ids = _learned()
    ids.forget(f"{USERS}/steps/900")
    assert ids.live() == [("steps", "901"), ("datasets", "777")]
