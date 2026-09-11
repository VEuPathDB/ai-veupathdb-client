---
type: Backlog
title: The oracle page ranks its sources for one consumer and names that consumer's sites
description: wdk/sources.md states "when PathFinder and this repository disagree, PathFinder is wrong" and calls plasmodb the primary site for PathFinder's work; the ranking is the application's rule, stated inside the library the application is measured against.
tags: [knowledge-bundle, wrong-repo, sources, generality]
status: draft
---

# The oracle page ranks its sources for one consumer and names that consumer's sites

**What I did.** Opened the page that declares what this bundle cites and how to
re-verify it, `docs/knowledge/wdk/sources.md`, and read every line that names a
consumer. Compared them with the application's own statement of the same rule,
`pathfinder: CLAUDE.md` under "VEuPathDB Source of Truth", and with the tree
that would receive them, `pathfinder: docs/knowledge/wdk/pathfinder/`.

**What I got.** Four lines, all in tables that a second consumer reads as
instructions:

- `:20` "Highest authority: when PathFinder and this repository disagree,
  PathFinder is wrong."
- `:21` "`packages/libs/wdk-client` carries the TypeScript types PathFinder's
  own types must match".
- `:162` "Primary site for PathFinder's own work."
- `:164` "a claim that holds on plasmodb.org and toxodb.org and orthomcl.org is
  not thereby a claim about the two sites PathFinder actually uses."

The first is word for word the application's own rule, which the application
also states about itself. The last two make plasmodb.org and toxodb.org the
verification sites because one product uses them.

**Why that's wrong.** A second consumer reads a ranking written for somebody
else: it is told which repository beats its own code, and which two sites its
claims must hold on, by a page that has no way to know either. The two site
lines are worse than unhelpful, because a consumer on a different site pair
reads the bundle's live verification as already done for sites it does not use.
And the first line makes the library assert a rule about an application it must
never depend on, which is the same direction the import boundary already forbids
(`tests/unit/test_package_boundary.py`).

**Why it happens.** `sources.md` was written inside the application, where every
one of those four sentences is true and load-bearing, and it moved here whole.

**Fix.** In this repository, a move with two outcomes.

- What stays: the four pinned repositories and their shas, what each is
  authoritative for, the ordering among the upstreams themselves, the gap
  between a pinned build and a deployed one, the re-verification procedure, and
  the measured search counts per site as measurements.
- What moves to `pathfinder: docs/knowledge/wdk/pathfinder/`: "when the
  application and WDK disagree, the application is wrong", "the TypeScript types
  the application's types must match", and the naming of primary and secondary
  sites for one product's work. This bundle keeps a neutral statement that the
  live checks were run on plasmodb.org and toxodb.org, which is a fact about the
  measurements, not a rule about anyone's deployment.

The receiving card in the application's own backlog takes delivery, and the
lines leave here in the change that lands them there.

**What you'd get.** A consumer reads `sources.md` and learns which upstream
falsifies which claim and how to re-run the check on its own sites, with no
sentence telling it whose types to match.
