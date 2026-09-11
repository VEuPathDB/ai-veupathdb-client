# Backlog

Everything known to be outstanding in this repository, ranked by what blocks a
second consumer first. Each item stands alone: a reader picks one up
without the work that wrote it.

Items are removed when done, not marked done. The [log](../log.md) records what
left, so this file and the items beside it are exactly what remains.

## Ranked

1. [EDA and VDI read the token only from the contextvar](eda-and-vdi-read-the-token-only-from-the-contextvar.md) - `VEUPATHDB_AUTH_TOKEN` authenticates a user-independent WDK read and refuses every EDA and VDI call, because only `VEuPathDBClient` resolves the three forms.
2. [The public surface is not declared](the-public-surface-is-not-declared.md) - 7 of 93 modules carry `__all__` and no test reads one; the two in-house consumers import 62 modules, 53 of them named nowhere in README, and both import a private one.
3. [The devtools ship without the readers they import](the-devtools-ship-without-the-readers-they-import.md) - `jsonschema` and `referencing` are dev-group only, so the five commands README advertises cannot run from an installed copy.
4. [The site router is built once and never reset](the-site-router-is-built-once-and-never-reset.md) - a settings source installed after the first client call changes no site list, and two consumers in one process cannot hold different ones.
5. [A refusal names a consumer's entity](a-refusal-names-a-consumers-entity.md) - the login refusal tells every consumer's users to sign in "to use searches, strategies and gene sets", and a saved gene set is not a WDK noun.
6. [36 rules are proven in another checkout](thirty-six-rules-are-proven-in-another-checkout.md) - 36 of 78 rules name a test this checkout cannot run, and one of those tests has already moved without anything failing.
7. [The WDK bundle documents a consumer's mapping](the-wdk-bundle-documents-a-consumers-mapping.md) - the tree states its subject as one product's mapping, 93 sentences keep that promise, and one of them is already stale.
8. [The oracle ranks sources for one consumer](the-oracle-ranks-sources-for-one-consumer.md) - `sources.md` says which repository beats the application's code and which two sites are the primary ones for one product's work.
9. [Three docstrings name a consumer's layers](three-docstrings-name-a-consumers-layers.md) - `SearchContext`, `bundle_rows` and `param_value_from_raw` explain themselves by naming another repository's layers, its agent tools and an LLM.
