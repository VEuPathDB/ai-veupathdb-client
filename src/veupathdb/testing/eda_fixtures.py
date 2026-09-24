"""Where the recorded EDA bodies and the pinned upstream RAML live."""

from veupathdb.eda.models import EdaDistributionResponse
from veupathdb.testing.fixture_store import FIXTURE_ROOT

FIXTURE_DIR = FIXTURE_ROOT / "eda"
UPSTREAM_DIR = FIXTURE_DIR / "upstream"
SCHEMA_PIN_FILE = UPSTREAM_DIR / "schema-pin.json"


def recorded_distribution(name: str) -> EdaDistributionResponse:
    """One recorded ``/distribution`` body, by file name without the suffix."""
    return EdaDistributionResponse.model_validate_json(
        (FIXTURE_DIR / f"{name}.json").read_text()
    )


__all__ = [
    "FIXTURE_DIR",
    "SCHEMA_PIN_FILE",
    "UPSTREAM_DIR",
    "recorded_distribution",
]
