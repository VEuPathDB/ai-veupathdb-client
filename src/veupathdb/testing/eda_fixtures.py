"""Where the recorded EDA bodies and the pinned upstream RAML live."""

from veupathdb.testing.fixture_store import FIXTURE_ROOT

FIXTURE_DIR = FIXTURE_ROOT / "eda"
UPSTREAM_DIR = FIXTURE_DIR / "upstream"
SCHEMA_PIN_FILE = UPSTREAM_DIR / "schema-pin.json"
