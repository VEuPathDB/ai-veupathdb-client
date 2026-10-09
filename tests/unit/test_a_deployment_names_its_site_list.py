from pathlib import Path

import pytest

from veupathdb.settings import VEuPathDBSettings, use_veupathdb_settings_source
from veupathdb.testing import QA_SITES_FILE
from veupathdb.wdk import SitesConfigNotSetError, list_sites, load_sites_config

QA_SITES = {
    "veupathdb": ("https://qa.veupathdb.org/veupathdb.qa/service", "UniDB"),
    "plasmodb": ("https://qa.plasmodb.org/plasmo.qa/service", "PlasmoDB"),
    "toxodb": ("https://qa.toxodb.org/toxo.qa/service", "ToxoDB"),
    "cryptodb": ("https://qa.cryptodb.org/cryptodb.qa/service", "CryptoDB"),
    "piroplasmadb": ("https://qa.piroplasmadb.org/piro.qa/service", "PiroplasmaDB"),
    "giardiadb": ("https://qa.giardiadb.org/giardiadb.qa/service", "GiardiaDB"),
    "amoebadb": ("https://qa.amoebadb.org/amoeba.qa/service", "AmoebaDB"),
    "microsporidiadb": (
        "https://qa.microsporidiadb.org/micro.qa/service",
        "MicrosporidiaDB",
    ),
    "tritrypdb": ("https://qa.tritrypdb.org/tritrypdb.qa/service", "TriTrypDB"),
    "trichdb": ("https://qa.trichdb.org/trichdb.qa/service", "TrichDB"),
    "fungidb": ("https://qa.fungidb.org/fungidb.qa/service", "FungiDB"),
    "hostdb": ("https://qa.hostdb.org/hostdb.qa/service", "HostDB"),
    "vectorbase": ("https://qa.vectorbase.org/vectorbase.qa/service", "VectorBase"),
    "orthomcl": ("https://qa.orthomcl.org/orthomcl.qa/service", "OrthoMCL"),
}


@pytest.mark.parametrize("unset", [None, "", "   "])
def test_an_unset_site_list_is_refused_by_name(unset: str | None) -> None:
    with pytest.raises(SitesConfigNotSetError, match="VEUPATHDB_SITES_CONFIG"):
        load_sites_config(unset)


def test_no_argument_is_an_unset_site_list() -> None:
    with pytest.raises(SitesConfigNotSetError, match="VEUPATHDB_SITES_CONFIG"):
        load_sites_config()


def test_a_process_with_no_site_list_fails_at_its_first_site_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VEUPATHDB_SITES_CONFIG", raising=False)
    use_veupathdb_settings_source(VEuPathDBSettings)

    with pytest.raises(SitesConfigNotSetError, match="VEUPATHDB_SITES_CONFIG"):
        list_sites()


def test_the_package_carries_no_production_site_list() -> None:
    package = Path(QA_SITES_FILE).parents[1]

    assert not (package / "sites.yaml").exists()
    assert not (package / "sites-plasmodb.yaml").exists()


def test_the_qa_list_names_every_site_at_its_qa_service() -> None:
    config = load_sites_config(str(QA_SITES_FILE))

    assert {
        site_id: (site.base_url, site.project_id)
        for site_id, site in config.sites.items()
    } == QA_SITES
    assert config.default_site == "veupathdb"
    assert [site_id for site_id, site in config.sites.items() if site.is_portal] == [
        "veupathdb"
    ]
