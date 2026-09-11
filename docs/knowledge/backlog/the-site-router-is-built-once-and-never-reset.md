---
type: Backlog
title: The site router is built once per process and nothing public resets it
description: get_site_router caches a router over an lru_cached sites config, so a settings source installed after the first client call changes nothing and two consumers in one process cannot hold different site lists.
tags: [settings, sites, generality, lifecycle]
status: draft
---

# The site router is built once per process and nothing public resets it

**What I did.** Opened the process-wide caches and looked for a public way to
drop them: `src/veupathdb/wdk/site_router.py:210-221` (`_router_holder`,
`get_site_router`), `site_router.py:47` (`@lru_cache` on
`load_sites_config`), `src/veupathdb/wdk/factory.py:11-12` (`_vdi_clients`),
`src/veupathdb/eda/factory.py:11-12` (`_clients`), and
`src/veupathdb/settings.py:69` (`use_veupathdb_settings_source`). Grepped the
whole tree for a reset and read this package's own `tests/conftest.py`.

**What I got.** `get_site_router()` builds one `SiteRouter` from settings at
first use and holds it in `_router_holder` for the life of the process. The
router's sites come from `load_sites_config`, which is `@lru_cache`d on its path
argument. `close_all_clients()` and `close_all_eda_clients()` close clients but
leave the router and the config cache in place, and no function clears
`_router_holder` at all: the only matches in the tree are its own definition and
the three lines of `get_site_router`. This package's own suite already needs the
reset it does not publish: `tests/conftest.py:17,21` calls
`load_sites_config.cache_clear()` around every test and reaches into a private
`auth_login._signing_keys` beside it, and `tests/unit/test_settings_source.py:39`
repeats the `cache_clear()` in a fixture.

**Why that's wrong.** A settings source installed after the first client call
has no effect on the site list, and nothing says so: the host reads a
`SiteInfo` for a site it never configured, or a `KeyError` for one it did. Two
consumers in one process cannot hold different site lists at all, and that is
the deployment this repository already serves, where the application and the
in-process tool server run together. A second consumer discovers the ordering
constraint by writing a test that fails in the second test, as this suite did.

**Why it happens.** `_router_holder` and the `@lru_cache` on
`load_sites_config` are module-level state with no public reset, and
`use_veupathdb_settings_source` writes to a different holder
(`settings.py:69`), so installing a source cannot invalidate the router built
from the previous one.

**Fix.** In this repository. Publish a reset that drops the router, the config
cache and the cached clients together, call it from
`use_veupathdb_settings_source` so installing a source invalidates what was
built from the old one, and state the ordering in README next to the settings
section. A unit test installs one source, reads a site, installs a second source
naming a different YAML, and asserts the second site list is what the router
serves.

**What you'd get.** A host that installs its settings source at any point gets
the site list it configured, and this package's own conftest stops reaching into
private module state to get a clean process.
