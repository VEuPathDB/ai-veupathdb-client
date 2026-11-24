import pytest

from veupathdb.wdk._http import changes_user_state

SERVICE = "/plasmo.qa/service"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("PUT", f"{SERVICE}/users/900000001/strategies/7/step-tree"),
        ("PATCH", f"{SERVICE}/users/900000001/strategies/7"),
        ("DELETE", f"{SERVICE}/users/900000001/steps/7"),
        ("POST", f"{SERVICE}/users/900000001/steps"),
        ("POST", f"{SERVICE}/users/900000001/strategies"),
        ("POST", f"{SERVICE}/users/current/datasets"),
        ("POST", f"{SERVICE}/users/900000001/strategies/7/duplicated-step-tree"),
        ("POST", f"{SERVICE}/users/900000001/steps/7/analyses"),
        ("POST", "/eda/users/900000001/analyses/ClinEpiDB"),
        ("POST", "/vdi/datasets"),
        ("POST", "/users/current/steps"),
    ],
)
def test_a_create_or_an_edit_changes_user_state(method: str, path: str) -> None:
    assert changes_user_state(method, path) is True


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", f"{SERVICE}/record-types/gene/searches/GenesByTaxon/reports/standard"),
        (
            "POST",
            f"{SERVICE}/record-types/gene/searches/GenesByTaxon/refreshed-dependent-params",
        ),
        ("POST", f"{SERVICE}/record-types/gene/records"),
        ("POST", f"{SERVICE}/users/900000001/steps/7/analyses/3/result"),
        ("POST", f"{SERVICE}/users/900000001/steps/7/reports/standard"),
        ("POST", "/eda/apps/pass/visualizations/histogram"),
        ("GET", f"{SERVICE}/users/900000001/steps/7"),
        ("GET", "/vdi/datasets"),
    ],
)
def test_a_read_changes_no_user_state(method: str, path: str) -> None:
    assert changes_user_state(method, path) is False
