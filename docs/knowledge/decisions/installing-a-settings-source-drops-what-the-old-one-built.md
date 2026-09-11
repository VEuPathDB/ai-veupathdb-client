---
type: Decision
title: Installing a settings source drops what the old one built
description: use_veupathdb_settings_source fires every registered invalidator, so the site router, the cached sites config and the per-site client caches are rebuilt from the source in force. Documenting an ordering constraint instead was rejected.
tags: [settings, sites, lifecycle]
generated: { by: claude-code/opus-5, at: 2026-09-11T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-11T00:00:00Z }
status: stable
---

# What was decided

`veupathdb.settings.on_settings_source_change` registers a cache built from settings.
`use_veupathdb_settings_source` fires every registration after it installs the source.
`veupathdb.wdk.site_router.reset_site_router` is the public reset: it drops the router,
clears `load_sites_config`, and fires every per-site client cache registered through
`on_site_router_reset`. The WDK factory registers its VDI clients and the EDA factory
registers its EDA clients, each at import, so a cache that was never imported has
nothing to drop.

Two registries rather than one, because they answer different questions: settings
says a source changed, the router says the site list changed.

Neither reset closes a client already handed out. `close_all_clients` and
`close_all_eda_clients` do that, and the README says to call them first.

# The alternative that was rejected

State the ordering constraint in README and leave the caches alone: install the
settings source before the first client call. It costs no code, and it fails
silently in the one deployment this package already serves, where an application and
an in-process tool server both install a source. A host that installs second reads a
`SiteInfo` for a site it never configured, or a `KeyError` for one it did, and
nothing reports either.

A generation counter compared on every `get_site_router` call was also considered: it
invalidates lazily with no registry, but every per-site cache would have to carry and
compare the same counter, which is the registry written once per cache instead of once.

# What holds it

`tests/unit/test_site_router_reset.py` installs one source naming a one-site YAML,
reads the site list, installs a second naming a different YAML, and asserts the second
list is what the router serves. A second case asserts the reset drops the WDK, EDA and
VDI clients. `tests/conftest.py` no longer reaches into a private cache: it installs
the source and calls `forget_signing_keys`.
