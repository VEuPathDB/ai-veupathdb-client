---
type: Decision
title: The published surface is a list of packages, checked in name by name
description: Each published package declares __all__ and tests/unit/published_surface.json holds every list, so a rename that drops a name a consumer reads fails here. Declaring the surface module by module was rejected.
tags: [public-surface, api-surface, gates]
generated: { by: claude-code/opus-5, at: 2026-09-11T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-11T00:00:00Z }
status: stable
---

# What was decided

Sixteen surfaces are published: eight packages (`veupathdb`, `veupathdb.devtools`,
`veupathdb.domain`, `veupathdb.domain.parameters`, `veupathdb.domain.strategy`,
`veupathdb.eda`, `veupathdb.testing`, `veupathdb.wdk`) and eight modules
(`veupathdb.auth_context`, `veupathdb.devtools.eda_schemas`,
`veupathdb.devtools.fixtures`, `veupathdb.errors`, `veupathdb.model`,
`veupathdb.observability.otel`, `veupathdb.testing.eda_fixtures`,
`veupathdb.testing.wdk_fixtures`). Each declares `__all__`;
`tests/unit/published_surface.json` holds every list; `tests/unit/test_public_surface.py`
asserts that every surface is listed, that each `__all__` is the checked-in one, that
every name resolves, that no name is private, that a package publishes names its own
files declare, and that no name is a submodule.

`tests/unit/consumer_imports.json` records the names the two in-house consumers read,
measured from their trees and grouped under the surface each one reads them from, and a
seventh case asserts each group against that surface alone. A name a consumer reads
therefore cannot leave the surface it reads it from, even when another surface carries
the same name.

The eight modules stay modules because a package cannot hold them. The two fixture
stores both declare `FIXTURE_DIR`, the OTEL adapter imports a distribution only its
extra installs, and the two devtools import the readers only the `devtools` extra
installs; publishing any of them through a package `__init__` would make importing
that package require an extra, or would need a rename to break the collision.

`veupathdb.wdk._failures` stays private. The three names both consumers read from it
(`bundle_rows`, `validation_bundle`, `wdk_failure`) are published on `veupathdb.wdk`.

# The alternative that was rejected

Declare `__all__` on every module and gate all 93 of them. That records the tree
rather than a surface: it publishes the file layout, so moving a function between two
modules of the same package is a breaking change, and a consumer still has to read
93 lists to find an entry point. The tool server's gate is the model here, and it
gates packages for the same reason (`veupathdb-mcp: tests/unit/test_public_surface.py`).

Publishing everything from the root package alone was also rejected: importing any
one shape would then import the WDK transport, the EDA client and the devtools.

# What the consumers change at the next tag

Both move to the package surfaces. The module paths below no longer publish what they
publish today; nothing is re-exported from the old path.

| Today | At the next tag |
|---|---|
| `from veupathdb.domain.<module> import X` (search, wdk_values, eda_*) | `from veupathdb.domain import X` |
| `from veupathdb.domain.parameters.<module> import X` | `from veupathdb.domain.parameters import X` |
| `from veupathdb.domain.strategy.<module> import X` | `from veupathdb.domain.strategy import X` |
| `from veupathdb.wdk.<module> import X` (client, factory, site_router, auth_login, current_user, wdk_models, wdk_parameters, ai_expression, analysis_result, probe, step_tree, value_decoding, site_search_client, phyletic_tree, vdi.client, vdi.models) | `from veupathdb.wdk import X` |
| `from veupathdb.wdk._failures import bundle_rows, validation_bundle, wdk_failure` | `from veupathdb.wdk import bundle_rows, validation_bundle, wdk_failure` |
| `from veupathdb.wdk.strategy_api import StrategyAPI, is_internal_wdk_strategy_name, strip_internal_wdk_strategy_name, tag_internal_wdk_strategy_name` | `from veupathdb.wdk import ...` (the package `__init__` publishes nothing) |
| `from veupathdb.wdk.strategy_api.api import StrategyAPI` | `from veupathdb.wdk import StrategyAPI` |
| `from veupathdb.wdk.strategy_api.steps import StepsMixin` | `from veupathdb.wdk import StepsMixin` |
| `from veupathdb.eda.<module> import X` (client, factory, errors, models, analyses) | `from veupathdb.eda import X` |
| `from veupathdb.eda import factory` | `from veupathdb.eda import close_all_eda_clients, get_eda_analyses_client, get_eda_client` |
| `from veupathdb.wdk import auth_login, current_user, factory` | the names, from `veupathdb.wdk` |
| `from veupathdb.settings import VEuPathDBSettings, get_veupathdb_settings, use_veupathdb_settings_source` | `from veupathdb import ...` |
| `from veupathdb.logging import get_logger` | `from veupathdb import get_logger` |
| `from veupathdb.json_types import JSONArray, JSONObject` | `from veupathdb import JSONArray, JSONObject` |
| `from veupathdb.observer import set_observer` | `from veupathdb import set_observer` |
| `from veupathdb.text import strip_html_tags` | `from veupathdb import strip_html_tags` |
| `from veupathdb.testing.wdk_credentials import ...`, `from veupathdb.testing.summary import ...` | `from veupathdb.testing import ...` |
| `from veupathdb.testing import eda_fixtures` | `from veupathdb.testing.eda_fixtures import FIXTURE_DIR, UPSTREAM_DIR` |
| `from veupathdb.devtools.wdk_capture import capture_wdk` | `from veupathdb.devtools import capture_wdk` |

`veupathdb.errors`, `veupathdb.model`, `veupathdb.auth_context`,
`veupathdb.observability.otel`, `veupathdb.devtools.fixtures`,
`veupathdb.devtools.eda_schemas`, `veupathdb.testing.wdk_fixtures` and
`veupathdb.testing.eda_fixtures` keep the paths the consumers already use.
