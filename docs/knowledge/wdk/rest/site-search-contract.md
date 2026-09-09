---
type: Reference
title: The site-search contract, both forms of it
description: The paged form stops at fifty records; the streaming form carries the whole match set as tab separated lines. What each one takes, what it answers, and what PathFinder calls where.
tags: [wdk-alignment, rest, site-search, gene-lookup]
generated: { by: claude-code/opus-5, at: 2026-09-04T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-04T00:00:00Z }
status: stable
---

# What this describes, and what falsifies it

Site search is not WDK. It is a separate VEuPathDB service, served at the **site origin**
(`https://plasmodb.org/site-search`) and not under the WDK service base, so nothing in
[the endpoint surface](endpoint-surface.md) covers it and the WDK service base answers 404
for the path. Its own README calls it a facade over a backing SOLR instance.

The falsifier is
[VEuPathDB/SiteSearchService at `3c1851c233d2c4719d7185f973058d8c2272ea38`](https://github.com/VEuPathDB/SiteSearchService/tree/3c1851c233d2c4719d7185f973058d8c2272ea38/),
committed 2026-05-22. Every claim below is either a line in that tree or a measurement
against plasmodb.org on 2026-09-04, and each says which. It is a different repository from
the four in [sources.md](../sources.md), because a WDK sha cannot falsify a claim about a
service WDK does not contain.

# One resource, two forms, selected by `Accept`

The service declares `POST /site-search` twice on the same path, and the media type the
request accepts decides which one runs
([`Service.java` L62-74](https://github.com/VEuPathDB/SiteSearchService/blob/3c1851c233d2c4719d7185f973058d8c2272ea38/src/main/java/org/gusdb/sitesearch/service/Service.java#L62-L74)).

| | Paged form | Streaming form |
|---|---|---|
| `Accept` | `application/json` | `application/x-ndjson` |
| `pagination` | required | **refused** |
| `documentTypeFilter` | optional | **required** |
| `foundOnlyInFields` | allowed | allowed |
| Records per response | at most **50** | the whole match set |
| Per record | primary key, score, organism, `summaryFieldData`, `foundInFields` | primary key, score, project |
| Also carries | `totalCount`, `organismCounts`, `documentTypes`, `categories`, `fieldCounts` | nothing but the records |

The two ceilings are constants:
[`SearchRequest.java` L32-34](https://github.com/VEuPathDB/SiteSearchService/blob/3c1851c233d2c4719d7185f973058d8c2272ea38/src/main/java/org/gusdb/sitesearch/service/request/SearchRequest.java#L32-L34)
declares `MAX_RECORDS_IN_PAGED_RESPONSE = 50` and `MAX_RECORDS_IN_TABULAR_RESPONSE = 100000`.
A paged request for more than fifty is refused with `numRecords must be <= 50`
([L48-49](https://github.com/VEuPathDB/SiteSearchService/blob/3c1851c233d2c4719d7185f973058d8c2272ea38/src/main/java/org/gusdb/sitesearch/service/request/SearchRequest.java#L48-L49)).

The streaming form's two extra requirements come from the same constructor, called with a
different set of flags: a `pagination` key raises `pagination property is not allowed`
([L52-54](https://github.com/VEuPathDB/SiteSearchService/blob/3c1851c233d2c4719d7185f973058d8c2272ea38/src/main/java/org/gusdb/sitesearch/service/request/SearchRequest.java#L52-L54)),
and a missing `documentTypeFilter` raises
`'documentTypeFilter' and contained 'documentType' properties are required at this endpoint`
([L67-69](https://github.com/VEuPathDB/SiteSearchService/blob/3c1851c233d2c4719d7185f973058d8c2272ea38/src/main/java/org/gusdb/sitesearch/service/request/SearchRequest.java#L67-L69)).
**Both reach a client as a bare 500 with `Content-Length: 0`,** measured on plasmodb.org, so
neither is diagnosable from the response. Build the stream body by removing `pagination`
from the paged body and keeping everything else; the organism filter, the project filter and
the field filter all apply unchanged
([`SolrCalls.java` L141-168](https://github.com/VEuPathDB/SiteSearchService/blob/3c1851c233d2c4719d7185f973058d8c2272ea38/src/main/java/org/gusdb/sitesearch/service/SolrCalls.java#L141-L168),
reached from the stream writer with the organism filter on).

# The media type says ND_JSON and the body is not JSON

Each line is three tab separated columns, and only the first is JSON:

```
["PF3D7_0616000"]	33.85314	PlasmoDB
```

`<primaryKey JSON array>` TAB `<score>` TAB `<project>`, written field by field at
[`SolrCalls.java` L207-214](https://github.com/VEuPathDB/SiteSearchService/blob/3c1851c233d2c4719d7185f973058d8c2272ea38/src/main/java/org/gusdb/sitesearch/service/SolrCalls.java#L207-L214)
over the three fields the SOLR query asks for
([L192](https://github.com/VEuPathDB/SiteSearchService/blob/3c1851c233d2c4719d7185f973058d8c2272ea38/src/main/java/org/gusdb/sitesearch/service/SolrCalls.java#L192)).
A `gene` document has no `project`, so its third column is empty and the line ends with a
tab. Records arrive in `score desc, id asc` order
([L48](https://github.com/VEuPathDB/SiteSearchService/blob/3c1851c233d2c4719d7185f973058d8c2272ea38/src/main/java/org/gusdb/sitesearch/service/SolrCalls.java#L48)),
which is the same order the paged form serves, so the two agree record for record.

Nothing else is on the line. **A streamed record carries no organism, no product, no gene
name and no matched fields**, which is why PathFinder describes a streamed identifier from
WDK before showing it.

The pinned response is
`src/veupathdb/testing/fixtures/wdk/site_search_stream_genes.json`, recorded from
plasmodb.org on 2026-09-04. Re-record it with the request in
`pathfinder: apps/api/src/pathfinder/tests/live/test_site_search_stream_drift.py`, which
is also what checks it against the live service.

# The 100,000 ceiling is in the source and not in the deployment

[`Service.java` L226-231](https://github.com/VEuPathDB/SiteSearchService/blob/3c1851c233d2c4719d7185f973058d8c2272ea38/src/main/java/org/gusdb/sitesearch/service/Service.java#L226-L231)
counts the result before it writes anything and refuses a set larger than
`MAX_RECORDS_IN_TABULAR_RESPONSE`. plasmodb.org does not do this. Measured 2026-09-04:
`searchText: "kinase"`, `documentType: "gene"`, no organism filter, reports
`totalCount: 1175519` from the paged form and then streams **1,175,519 lines, 32,886,583
bytes**, with no error. Whatever build is deployed does not enforce the cap, so **a client
must bound its own read**; PathFinder's bound is `SITE_SEARCH_STREAM_LIMIT` in
`veupathdb-mcp/src/veupathdb_mcp/gene_lookup/site_search.py`.

Reading the stream is cheap up to that bound because the cost is time to first byte, not
volume. On that same 1,175,519 record query: first byte at 2.4 s, and 5,000 records
(138,941 bytes) read and the connection closed at 2.9 s.

# The project filter does not filter a gene document

One SOLR index serves every VEuPathDB site. `restrictToProject` is a field on
the request and the deployed service accepts it, but it does not restrict a
`documentType: gene` query. Measured on plasmodb.org 2026-09-05:
`searchText: "kinase"`, `documentType: "gene"` answers `totalCount 1175520`
without `restrictToProject` and `1175519` with `restrictToProject: "PlasmoDB"`.
The first five results are Cordyceps, Aspergillus, Blumeria and two Trypanosoma
genes.

**A client restricts by organism, not by project.** VEuPathDB's own client sends
the site's whole organism list when the user picked none
([`SiteSearchController.tsx` L369-377](https://github.com/VEuPathDB/web-monorepo/blob/8c1857af8f7da6feaa9ee888ed3472a0e753e89f/packages/libs/web-common/src/controllers/SiteSearchController.tsx#L369-L377),
`restrictSearchToOrganisms: organisms?.length === 0 ? allOrganisms : organisms`,
with the same list as `restrictMetadataToOrganisms`).

**That list is not `organismCounts`.** An unrestricted `documentType: gene`
query on plasmodb.org reports **831** organism keys, every organism in the
index, so the facet cannot be used to restrict the query that produced it. The
site's own list is the leaves of the `organism` parameter of the site's
`SequencesByTaxon` search, which is what the upstream client reads
([`hooks/organisms.ts` L7-30](https://github.com/VEuPathDB/web-monorepo/blob/8c1857af8f7da6feaa9ee888ed3472a0e753e89f/packages/libs/web-common/src/hooks/organisms.ts#L7-L30),
`TAXON_QUESTION_NAME`); plasmodb declares **64**. Sending it turns the same
kinase query into `totalCount 17516` over Plasmodium genes.
`veupathdb_mcp.gene_lookup.organisms.list_organisms` reads it and both request
forms send it; `veupathdb-mcp/tests/live/test_site_scoped_gene_search.py` pins
the result.


# What the two forms cost, measured

plasmodb.org, 2026-09-04, `searchText: "kinase"`, `documentType: "gene"`,
`restrictSearchToOrganisms: ["Plasmodium falciparum 3D7"]`, which matches 352 gene
documents.

| | Requests | Records | Latency | Bytes |
|---|---|---|---|---|
| Paged, one page | 1 | 50 | 1.43 s | 97,910 |
| Paged, whole match set (8 sequential pages) | 8 | 352 | 10.54 s | 588,186 |
| Streaming, whole match set | 1 | 352 | 0.55 s | 10,044 |

The two record sets are identical: same 352 identifiers, in the same order, with the same
scores to five decimal places.

# What PathFinder calls, and where

`src/veupathdb/wdk/site_search_client.py` has one method per form: `search` for the
paged one and `stream_records` for the streaming one.

| Caller | Form | Why |
|---|---|---|
| `veupathdb_mcp.gene_lookup.lookup`, first page | paged | The described records carry the organism, product and matched fields the ranking reads. |
| `veupathdb_mcp.gene_lookup.lookup`, past record 50 | streaming | A page the paged form cannot reach. The identifiers are described from WDK after the window is cut. |
| `veupathdb_mcp.catalog.search_collection` | paged | Reads `hyperlinkName` and `foundInFields` off each `search` document; the stream carries neither. |
| MCP `lookup_gene_records`, agent `lookup_gene_records`, the gene autocomplete | paged | Each is bounded at 50 records with no offset, so one page is the whole answer. |
