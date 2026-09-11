---
type: Backlog
title: EDA and VDI read the token only from the contextvar, while WDK honours three forms
description: VEUPATHDB_AUTH_TOKEN authenticates a user-independent WDK read and refuses every EDA and VDI call, because only VEuPathDBClient implements the three-form resolution.
tags: [auth, eda, vdi, generality, packaging]
status: draft
---

# EDA and VDI read the token only from the contextvar, while WDK honours three forms

**What I did.** Opened the three token resolvers in the current tree:
`src/veupathdb/wdk/_http.py:165-175` (`VEuPathDBClient._effective_token`),
`src/veupathdb/eda/client.py:74-78` (`EdaClient._token`) and
`src/veupathdb/wdk/vdi/client.py:101-106` (`VdiClient._auth`). Read
`EdaClient.__init__` (`eda/client.py:43-54`), `src/veupathdb/eda/factory.py` and
`README.md:9-13`.

**What I got.** WDK resolves in order: the contextvar, then the constructor's
`auth_token`, then `settings.veupathdb_auth_token` (`_http.py:170-175`), and it
refuses early only on a path that acts for a user (`_acts_for_a_user`,
`_http.py:45`). EDA and VDI read `veupathdb_auth_token_ctx` and raise
`WDKLoginRequiredError` when it is empty. Neither `EdaClient.__init__` nor
`VdiClient.__init__` takes a token, and `get_eda_client(site_id)` passes a base
URL and nothing else. README:10-12 states the token is supplied "through
`veupathdb.auth_context.veupathdb_auth_token_ctx` or through
`VEUPATHDB_AUTH_TOKEN` for the user-independent reads", naming no service.

**Why that's wrong.** A host that exports `VEUPATHDB_AUTH_TOKEN` and sets no
contextvar gets a working `GET /record-types` and a 401 from every EDA and VDI
call. The refusal reads "VEuPathDB login required", so the host reads a wiring
mistake as an account problem and goes looking at the user's VEuPathDB login.
Three of this package's four services answer the same question differently, and
the README sentence that would say so covers all of them at once.

**Why it happens.** The three-form resolution exists once, in
`VEuPathDBClient._effective_token`. `EdaClient._token` and `VdiClient._auth`
read the contextvar directly, so nothing outside `veupathdb.wdk` can see a
constructor token or a settings token.

**Fix.** In this repository. Give the resolution one home that all three
clients import, add an `auth_token` keyword to `EdaClient.__init__` and
`VdiClient.__init__` so the constructor form works everywhere, and state in
README which forms each service accepts. One unit test per client asserts that
a settings token authenticates a call with an empty contextvar, and that a
contextvar token still wins over both. The behaviour change rides the next
release of `veupathdb-py` (`0.1.0a8`): raise the version here, tag it, then the
consuming application raises the `tag` in `pathfinder: apps/api/pyproject.toml`
and relocks.

**What you'd get.** A host that sets one environment variable reads an EDA
study exactly as it reads a WDK search list, and a host that carries per-request
identity keeps the contextvar as the form that overrides both others.
