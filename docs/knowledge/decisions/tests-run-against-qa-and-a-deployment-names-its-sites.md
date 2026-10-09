---
type: Decision
title: Tests run against QA, and a deployment names its site list
description: The package ships no default site list, every test and every recorder reads the QA list at veupathdb.testing.QA_SITES_FILE, no recording made on production stays in the package, and check-test-sites.mjs fails on a production or beta host outside docs. Production and beta were rejected for tests because test load reached the production servers.
tags: [testing, sites, settings, recording, live-lane, ci]
generated: { by: claude-code/opus-5.5, at: 2026-10-09T00:00:00Z }
status: stable
---

# What was decided

- **A deployment names its site list.** `load_sites_config` takes the path
  `VEUPATHDB_SITES_CONFIG` names and raises `veupathdb.wdk.SitesConfigNotSetError`,
  naming the setting, when there is none. The router reads it at its first site read,
  so a process with no list fails there. The production list is
  `docs/sites/production.yaml`, a file a deployment that serves production copies; it is
  not in the wheel.
- **Every test reads QA.** The wheel carries one list, the QA sites
  (`qa.<site>.org/<project>.qa/service`), at `veupathdb.testing.QA_SITES_FILE`, a copy of
  the QA stage file of the consuming application. `tests/conftest.py` names it in the
  environment and in the settings source for every test, the `live_wdk` lane included.
- **Every recorder reads QA.** `fixtures record`, `eda_capture` and `vdi_capture` call
  `veupathdb.devtools.use_qa_sites` before their first request, whatever the process
  names, and `capture_wdk` keeps only exchanges with a QA host. No recorder takes an
  option that reaches another list.
- **No production recording stays in the package.** The bodies recorded on production
  moved to `fixtures-production-backup-2026-10-09/`, which no test reads and no build
  packs. `verify` names each missing body, and each test that reads one is skipped with
  `veupathdb.testing.NEEDS_QA_RECORDING`
  ([the backlog item](../backlog/the-production-recordings-are-recorded-again-on-qa.md)).
- **The guard.** `scripts/check-test-sites.mjs` fails on a production host (a site
  domain whose nearest label is not `qa` or `q2`: bare, `www.`, `beta.`, a numbered
  server, any other subdomain or a mail domain) in any file outside `docs/`, the backup
  directory and `src/veupathdb/settings.py`, whose OAuth default names the one server
  that signs every site's tokens. CI and pre-commit run it with its test. The consuming
  tool server runs the same script with its own allowlist.

# Rejected

- **Production.** Test load on a production site reaches the researchers who use it.
- **Beta.** `beta.<site>.org` is served by the production servers.
- **A bundled default list.** A process that named no list reached production without
  saying so.
- **A recorder flag that reaches production.** No recording needs one.

# What this costs

Outside the VEuPathDB network the QA sites answer with a pre-release login, so nothing
is recorded again until automated clients have a way through. Until then the hermetic
suite proves less: every rule whose test reads a recording is unproven in this
checkout, and every count, identifier and vocabulary a live test pins was measured on
production.

# What proves it wrong

`tests/unit/test_a_deployment_names_its_site_list.py`,
`tests/unit/devtools/test_a_recorder_reaches_only_the_qa_sites.py`,
`tests/unit/devtools/test_verify_names_a_missing_recording.py`,
`tests/packaging/test_wheel_carries_the_fixtures.py` and
`node scripts/check-test-sites.mjs`.
