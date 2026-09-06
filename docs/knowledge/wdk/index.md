# WDK

How VEuPathDB's WDK platform works, how PathFinder maps onto it, and the rules
PathFinder must not break.

These documents exist so that a disagreement with WDK is detectable in review, rather
than discovered by a researcher acting on a wrong answer. Every assertion here names the
upstream that would prove it wrong, and `scripts/check-wdk-rules.mjs` fails the build
when that evidence stops resolving.

- [Rules](rules/) - the assertions, one file per ID family. Start here.
- [Model](model/) - what WDK is
- [REST](rest/) - the endpoint surface, and deployment behavior that is not in the docs
- PathFinder (`pathfinder: docs/knowledge/wdk/pathfinder/`) - correspondence, ownership, and deliberate divergences
- [sources.md](sources.md) - the oracle, pinned, and how to re-verify it
