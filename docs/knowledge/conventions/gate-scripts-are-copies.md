---
type: Convention
title: The gate scripts are copies, on purpose
description: check-knowledge.mjs and check-wdk-rules.mjs exist in this repository and in the consuming application. The duplication is deliberate, and the two copies are kept byte-identical apart from the bundle root they check.
tags: [conventions, gates, knowledge-bundle]
generated: { by: claude-code/opus-5, at: 2026-09-08T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-08T00:00:00Z }
status: stable
---

# The rule

`scripts/check-knowledge.mjs`, `scripts/check-wdk-rules.mjs` and their `.test.mjs`
files are copies of the consuming application's. A change to either copy is made in
both, in the same change. The only permitted difference is the bundle root each one
walks: this repository checks `docs/knowledge/wdk`, the application checks its own
mapping tree.

# Why there is no shared copy

The two repositories share Python distributions, not Node scripts. Publishing a
package for two files of about 400 lines fails YAGNI, and the vendored-tree pin
machinery in `src/veupathdb/devtools/pins.py` pins schema trees fetched from
upstream, not scripts authored here. Divergence is the cost, and a copy that has
drifted is a gate that passes in one repository and fails in the other.

# What the citation support is for

`check-knowledge.mjs` resolves a prefixed citation of a page in another repository
against a sibling checkout when one is present, fails on a page that does not exist
there, and reports the citation as unverified when the checkout is absent.

`check-wdk-rules.mjs` reads an anchor or a status prefixed with a repository name -
`veupathdb-py:`, `veupathdb-mcp:`, `assistant-platform:` - as a citation and does not
resolve it, because that repository is never checked out beside this one. The run
reports how many rules are anchored that way, so a bundle cannot hide behind
unresolvable paths.
