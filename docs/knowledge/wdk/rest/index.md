# WDK REST

The endpoint surface, and the deployment behavior that is not in the documentation.
These explain; they do not assert. Assertions live in [the rules](../rules/).

- [Endpoint surface](endpoint-surface.md) - every endpoint, its shapes, the PathFinder method behind it, and which of them WDK validates against a published schema
- [Transport quirks](transport-quirks.md) - what a live site does, including two beliefs that did not reproduce
- [VDI surface](vdi-surface.md) - the user-dataset service at `{site_origin}/vdi`: the endpoints PathFinder calls, the credential forms, the three status axes, and one measured install
- [Site-search contract](site-search-contract.md) - the separate service at the site origin, its paged form and its streaming form, and what each one costs
