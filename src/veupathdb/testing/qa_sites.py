from pathlib import Path

from veupathdb.testing.fixture_store import FIXTURE_ROOT, package_file

QA_SITES_FILE = package_file("qa_sites.yaml")

NEEDS_QA_RECORDING = (
    "needs a QA recording: record it from QA with the fixtures recorder"
)
QA_HOLDS_NO_AI_SUMMARY = (
    "QA holds no cached AI expression summary for this gene, and recording one "
    "would start the site's summary job"
)
QA_HOLDS_NO_CRASHED_IMPORT = (
    "QA holds no crashed VDI import, and no upload makes an import crash on demand"
)


def needs_qa_recording(*recordings: str | Path) -> bool:
    return not all((FIXTURE_ROOT / recording).is_file() for recording in recordings)
