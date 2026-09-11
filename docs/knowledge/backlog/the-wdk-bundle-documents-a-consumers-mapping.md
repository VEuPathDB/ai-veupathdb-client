---
type: Backlog
title: The WDK tree states its subject as one consumer's mapping, and 93 sentences keep that promise
description: docs/knowledge/wdk says it documents how PathFinder maps onto WDK; the mapping prose belongs in the consuming application's own wdk/pathfinder tree, the WDK facts and this package's own facts stay.
tags: [knowledge-bundle, wrong-repo, generality]
status: draft
---

# The WDK tree states its subject as one consumer's mapping, and 93 sentences keep that promise

**What I did.** Read the subject line of the WDK tree, counted the consuming
application's name across `docs/knowledge/wdk` and `docs/knowledge/eda`, opened
the heaviest pages, and opened the tree that would receive the prose,
`pathfinder: docs/knowledge/wdk/pathfinder/`.

**What I got.** `docs/knowledge/wdk/index.md:3-4` states the subject as "How
VEuPathDB's WDK platform works, how PathFinder maps onto it, and the rules
PathFinder must not break". 93 occurrences of the application's name sit under
`docs/knowledge/wdk`, spread over 22 of its files, and 9 more under
`docs/knowledge/eda` over 5 files. The heaviest are
`wdk/rest/endpoint-surface.md` (11), `wdk/rules/parameters-and-vocabularies.md`
(10), `wdk/rest/vdi-surface.md` (9), `wdk/model/users-auth-and-sessions.md` (9),
`wdk/rules/auth-and-transport.md` (8) and `wdk/rules/validation.md` (7). The
tree already knows the right shape: `wdk/index.md:14` links the application's
mapping tree by its citation prefix, and that tree exists, with
`deliberate-divergences.md`, `layer-ownership.md`, `type-correspondence.md` and
its own `rules/`.

One of those sentences is already stale and proves the cost.
`wdk/rules/validation.md:87-93` says "`StepValidation`'s defaults are
`level="NONE"` and `is_valid=True`" and that "`WDKStrategyDetails.validation` is
declared `Field(default_factory=StepValidation)`". In the current tree
`StepValidation` declares `level: str` and `is_valid: bool` with no defaults and
a docstring saying a default would turn a missing key into a claim nobody made
(`src/veupathdb/domain/strategy/validation.py:24-36`), and the field is
`validation: StepValidation | None = None` (`src/veupathdb/wdk/wdk_models.py:138`).
The paragraph describes a fixed condition, under the wrong product's name, for
models that live in this package.

**Why that's wrong.** A second consumer reads a WDK reference whose stated
subject is another product, cannot tell which sentences are about WDK and which
are about that product's code, and has no way to check the ones that are not:
the code they describe is in a repository this checkout never sees. That is how
the paragraph above went stale with every gate green. The bundle's own promise
is that each claim names the upstream that can falsify it, and a claim about an
application nobody here can read has no such upstream.

**Why it happens.** The bundle was written inside the application and split out
with its subject line intact. Nothing fails on the application's name appearing
under `docs/knowledge/wdk`.

**Fix.** In this repository, a move, page by page, with exactly three outcomes
per sentence and no fourth.

- A statement about WDK's own behaviour **stays**, with the application's name
  removed and the actor named as the client or the caller.
- A statement about this package's own models, clients or defaults **stays**,
  with the application's name replaced by the package's: those symbols are in
  `src/veupathdb`, so the name was simply wrong.
- A statement about the application's mapping, its ownership of a concept, or a
  deliberate divergence **moves** to `pathfinder: docs/knowledge/wdk/pathfinder/`,
  and what is left here cites it by prefix instead of restating it.

`wdk/rules/validation.md:87-93` is deleted rather than moved: it is stale, and
WDK-VALID-002 is already enforced here by a test on the anchor it names.
`wdk/index.md:3-4` is rewritten to the subject that remains. The consuming
application's own backlog carries the card that takes delivery, so a page leaves
here only in the change that lands it there. A gate this repository owns alone
then fails on the application's name in this bundle outside a citation; it
cannot go into `scripts/check-knowledge.mjs`, whose copies must stay comparable
([the gate scripts are copies](../conventions/gate-scripts-are-copies.md)) and
whose other copy checks a bundle where that name is correct on every page.

**What you'd get.** A reader with no application checkout reads
`docs/knowledge/wdk` as a WDK reference in which every sentence names WDK or
this package, and the mapping lives in one repository, next to the tests that
prove it.
