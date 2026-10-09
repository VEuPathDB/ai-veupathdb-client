from pathlib import Path

from veupathdb.testing.fixture_store import FIXTURE_ROOT, package_file

QA_SITES_FILE = package_file("qa_sites.yaml")

NEEDS_QA_RECORDING = "needs a QA recording: re-record once QA access exists"


def needs_qa_recording(*recordings: str | Path) -> bool:
    return not all((FIXTURE_ROOT / recording).is_file() for recording in recordings)
