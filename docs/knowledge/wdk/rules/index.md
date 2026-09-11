# WDK rules

Each file holds one ID family. The statement in a heading is an assertion, not advice.

`class` sets test priority: `HARD` means WDK rejects the request, `SILENT` means WDK
accepts it and the science is wrong, `CONTRACT` means a client invariant that keeps
us aligned. `SILENT` is why this exists.

- [Auth and transport](auth-and-transport.md) - `WDK-HTTP-001..004` and `WDK-AUTH-001..003`
- [Strategies and steps](strategies-and-steps.md) - `WDK-STRAT-001..007` and `WDK-STEP-001..008`
- [Searches and answers](searches-and-answers.md) - `WDK-SEARCH-001..004` and `WDK-ANS-001..009`
- [Parameters and vocabularies](parameters-and-vocabularies.md) - `WDK-PARAM-001..011` and `WDK-VOCAB-001..007`
- [Site-model parameters](site-model-params.md) - `WDK-SITE-001..007`
- [Filters](filters.md) - `WDK-FILTER-001..006`
- [Validation](validation.md) - `WDK-VALID-001..011`
- The application's mapping rules (`pathfinder: docs/knowledge/wdk/pathfinder/rules/pathfinder-mapping.md`) - `WDK-MAP-001..008`

`WDK-SITE` is separated from `WDK-PARAM` by its falsifier rather than by its subject. A
`WDK-PARAM` rule is refuted by the WDK repository; a `WDK-SITE` rule is refuted by
ApiCommonModel, which declares the parameters WDK merely executes. The same distinction is
why [WDK-ANS-007](searches-and-answers.md) needed ApiCommonWebsite pinned.
