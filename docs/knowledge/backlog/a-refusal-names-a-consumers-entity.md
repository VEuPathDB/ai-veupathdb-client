---
type: Backlog
title: The login refusal names a saved gene set, which is a consumer's entity and not a WDK noun
description: WDKLoginRequiredError tells the end user to sign in "to use searches, strategies and gene sets"; the string is served verbatim to any consumer's users, and a saved gene set exists only in the consuming application.
tags: [errors, wording, generality]
status: draft
---

# The login refusal names a saved gene set, which is a consumer's entity and not a WDK noun

**What I did.** Read the refusal this package raises whenever a user-scoped call
has no registered token, and followed it to the wire:
`src/veupathdb/errors.py:105-116` (`WDKLoginRequiredError`), and the handler that
serves it, `pathfinder: apps/api/src/pathfinder/platform/error_handlers.py:86-108`.
Grepped `src/veupathdb` for consumer nouns.

**What I got.** The refusal carries `title="VEuPathDB login required"` and
`detail="Sign in to VEuPathDB to use searches, strategies and gene sets."`
(`errors.py:115`); its class docstring repeats the list (`errors.py:107`). The
handler copies `exc.title` and `exc.detail` into the problem response
unchanged, so the sentence is what an end user reads. A search and a strategy
are WDK nouns with endpoints behind them. A saved gene set is not: it is the
consuming application's own entity, stored by its own service, and no WDK
endpoint serves one.

**Why that's wrong.** A second consumer that never stores a gene set shows its
users a sign-in notice promising a feature the product does not have, and the
consumer cannot correct it without catching the refusal and rewriting the
sentence, which defeats the shared error hierarchy this package publishes
([the refusal base is generic in its code enum](../decisions/the-refusal-base-is-generic-in-its-code-enum.md)).
The same string also under-describes the refusal here, because it is raised for
every user-scoped path, EDA and VDI included.

**Why it happens.** The detail string was written for one product and lists that
product's features instead of stating the condition. Nothing gates the wording,
so the noun survived the split.

**Fix.** In this repository. State the condition, not a feature list: a detail
that says VEuPathDB serves registered users only and that this request carried
no registered token. A unit test asserts the detail names no entity this
package does not model. The one remaining product-shaped sentence in the tree,
`src/veupathdb/wdk/strategy_api/analyses.py:182` ("the gene set is too small"),
stays: there it names the set of genes an enrichment analysis ran over, which is
the analysis's own input.

**What you'd get.** Every consumer serves the same accurate refusal, and a
consumer with no gene sets does not have to rewrite a library string to avoid
promising one.
