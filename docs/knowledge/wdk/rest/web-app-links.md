---
type: Reference
title: The web app links the client reads
description: Which pages of a site's web app a link names, how the client reads a link into the search, record or strategy it shows, and why a link to another site or another page names nothing it can run.
tags: [web-app, links, routes, searches, records, strategies, rest, veupathdb]
generated: { by: claude-code/opus-5, at: 2026-11-10T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-11-10T00:00:00Z }
status: stable
---

# What this file is

A site's web app lives under `{web_base_url}/app`, for example
`https://qa.plasmodb.org/plasmo.qa/app`. `veupathdb.wdk.parse_site_link(url)` reads a link
under a configured site's app root into what the page shows, and `find_site_links(text)`
finds every such link in a text. A link under no configured site's app root names nothing,
so a QA deployment reads QA links and a production deployment reads production links.

# The routes

The shapes are the web client's own routes,
`VEuPathDB/web-monorepo: packages/libs/wdk-client/src/Core/routes.tsx`.

| Route | Link kind | What it carries |
|---|---|---|
| `/search/:recordClass/:question/result` | `SearchResultLink` | the record type, the search, and each `param.<name>=` query value |
| `/search/:recordClass/:question` | `SearchFormLink` | the same |
| `/record/:recordClass/:primaryKey+` | `RecordLink` | the record type and every part of the key |
| `/workspace/strategies/:strategyId/:stepId?` | `StrategyLink` | the strategy and the step the page opens |
| `/import/:signature` | `ImportLink` | the signature of a shared strategy |

Every other page is an `OtherPageLink` with its path.

The result route sends only the `param.` values the link carries
(`makeAnswerControllerRouteComponent`, `parseSearchParamsFromQueryParams`). Nothing fills a
missing value: WDK refuses a required parameter with no default, for example
`organism: Cannot be empty.` from `GenesByOrthologPattern`. `filterTerm`,
`filterAttributes` and `filterTables` filter the shown table only and are not read.

A strategy belongs to one account. WDK answers 404 for an id it does not hold and 403 for
a strategy another account owns (`VEuPathDB/WDK: StrategyService.getStrategyForCurrentUser`),
so a link to another account's strategy is read through its share link, the import route.
