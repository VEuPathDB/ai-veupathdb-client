from veupathdb.settings import get_veupathdb_settings, use_veupathdb_settings_source
from veupathdb.testing.qa_sites import QA_SITES_FILE


def use_qa_sites() -> None:
    current = get_veupathdb_settings()
    if current.veupathdb_sites_config == str(QA_SITES_FILE):
        return
    in_force = current.model_copy(update={"veupathdb_sites_config": str(QA_SITES_FILE)})
    use_veupathdb_settings_source(lambda: in_force)
