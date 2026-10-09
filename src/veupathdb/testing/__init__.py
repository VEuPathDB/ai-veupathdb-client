"""What a consumer's suite reads: the recorded stores, the QA site list, the live tally and the account."""

from veupathdb.testing.fixture_store import FIXTURE_ROOT
from veupathdb.testing.qa_sites import (
    NEEDS_QA_RECORDING,
    QA_SITES_FILE,
    needs_qa_recording,
)
from veupathdb.testing.summary import (
    DriftLog,
    LiveLaneSummary,
    Observation,
    Outcomes,
    SiteTally,
    summary_path,
)
from veupathdb.testing.wdk_credentials import (
    NO_CREDENTIALS_REASON,
    WdkTestAccount,
    registered_wdk_token,
    wdk_test_account,
)

__all__ = [
    "FIXTURE_ROOT",
    "NEEDS_QA_RECORDING",
    "NO_CREDENTIALS_REASON",
    "QA_SITES_FILE",
    "DriftLog",
    "LiveLaneSummary",
    "Observation",
    "Outcomes",
    "SiteTally",
    "WdkTestAccount",
    "needs_qa_recording",
    "registered_wdk_token",
    "summary_path",
    "wdk_test_account",
]
