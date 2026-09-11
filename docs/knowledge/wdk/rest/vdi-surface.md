---
type: Reference
title: The VDI endpoints this client calls
description: Method, path, payload and response for every VDI user-dataset endpoint this client calls, each pinned to the RAML that defines it, plus the credential forms and the install latency measured live.
tags: [vdi, user-datasets, rest, veupathdb, wdk-alignment]
generated: { by: claude-code/opus-5, at: 2026-09-05T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-05T00:00:00Z }
status: stable
---

# What this file is

VDI is a separate service from WDK. It lives at `{site_origin}/vdi` on every configured
site, and its contract is RAML, not OpenAPI: `GET /vdi/openapi.json` is 404 and `GET
/vdi/api` serves rendered HTML. This file records the part of that contract this client
depends on, pinned to the source that defines it. Why the application uses it this way is recorded in
`pathfinder: docs/knowledge/decisions/vdi-is-a-publish-target-not-a-store.md`.

Every citation is `VEuPathDB/vdi-service@34eb6f2f331bc5a8cd686d63588102b46d30b4dd`, under
`project/core/module/rest-service/`.

# Credentials

`AuthFilter.findAuthUser` accepts three forms and rejects everything else
(`VEuPathDB/lib-jaxrs-container-core@2d1d138aca44af36c09ed4650b256aa999a75ad6`,
`src/main/java/org/veupathdb/lib/container/jaxrs/server/middleware/AuthFilter.java`, with
the header name in `.../utils/RequestKeys.java`):

| form | measured against `GET https://plasmodb.org/vdi/datasets` |
| --- | --- |
| `Authorization: Bearer <token>` | 200 |
| `Authorization: <token>` (no scheme) | 401 |
| `Authorization` cookie | 200 |
| `?access_token=<token>` | 200 |
| `Auth-Key: <token>` | 401 |
| no credential | 401 `{"status":"unauthorized","message":"HTTP 401 Unauthorized"}` |

The token is the same non-guest WDK `Authorization` value `password_login` returns.
This client sends the bearer header. `/plugins` is the only endpoint below that answers
without a credential.

# Endpoints

| method + path | request | response | RAML | client |
| --- | --- | --- | --- | --- |
| `POST /datasets` | `multipart/form-data`: `details` (JSON `DatasetPostMeta`) and `dataFile` (one text file, one gene id per line) | 202 + `Location`, body `{"datasetId": "<VdiId>"}` | `api-schema/resources/dataset-list/method-post.raml`, `api-schema/types/by-path/datasets/post.raml` | `VdiClient.create_genelist` |
| `GET /datasets/{vdi-id}` | none | 200 `DatasetDetails`; 404 deleted; 410 gone; 425 not yet in the object store | `api-schema/resources/dataset/method-get.raml`, `.../types/by-path/datasets/vdi-id/get.raml` | `VdiClient.get` |
| `GET /datasets` | none | 200 `DatasetListEntry[]` | `api-schema/resources/dataset-list/method-get.raml`, `.../types/by-path/datasets/get.raml` | not called; the row keeps the one id it published |
| `DELETE /datasets/{vdi-id}` | none | 204 | `api-schema/resources/dataset/method-delete.raml` | `VdiClient.delete` |
| `PUT /datasets/{vdi-id}/shares/{recipient-user-id}/offer` | `{"action": "grant" \| "revoke"}` | 204 | `api-schema/resources/dataset-shares/resource.raml`, `.../types/by-path/datasets/vdi-id/shares/put.raml` | not called; this client publishes and reads, it does not share |
| `GET /plugins` | none, no credential | 200 `PluginListItem[]` | `api-schema/resources/plugins/resource.raml` | not called; read once to pin the plugin name and its targets |

`details` carries `type: {name, version}`, `installTargets` (at least one), `name` (3 to
1024 chars), `summary` (3 to 4000), optional `description`, `origin`, `visibility` and
`dependencies` - `api-schema/types/common.raml` `DatasetMetaBase`, `DatasetTypeInput`,
`DatasetVisibility`. This client sends `origin: "direct-upload"` and one install target,
the site's own `project_id`, which is what the site's native export does
(`VEuPathDB/web-monorepo@905ce53ffd0213c9a1da4f6b6f9873768193f2d5`,
`packages/sites/genomics-site/webapp/wdkCustomization/js/client/components/records/gene-list-export-utils.tsx:366-382`).

`VdiId` is `^[a-zA-Z0-9_-]+$` (`common.raml`), which is why it can never be a WDK
`DatasetParam` value.

# The three status axes

`DatasetStatusInfo` (`common.raml`) reports `upload`, `import` and one `install` entry per
target. They move independently, and the enum members are:

- upload: `running`, `success`, `rejected`, `failed`
- import: `queued`, `in-progress`, `complete`, `invalid`, `failed`
- install: `queued`, `running`, `complete`, `failed-validation`, `failed-installation`,
  `ready-for-reinstall`, `missing-dependency`

An `install` array is absent until import completes. The wire spells the import axis
`import`, which is a Python keyword, so the client's field is `import_` with a
`validation_alias`.

# The genelist plugin

`GET https://plasmodb.org/vdi/plugins` lists `genelist` v1.0, category `Gene List`,
`maxFileSize` 1073741824, `allowedFileExtensions` `[".txt", ".csv", ".tsv"]`, and 13
install targets: AmoebaDB, CryptoDB, FungiDB, GiardiaDB, HostDB, MicrosporidiaDB,
PiroplasmaDB, PlasmoDB, ToxoDB, TrichDB, TriTrypDB, VectorBase, UniDB. The plugin's
importer splits on `[\s,;]+` and writes one id per line
(`VEuPathDB/vdi-plugin-genelist@cfb31e78a43b91f22037b1e36c7e2e4a9a17713e`,
`lib/python/eupath/GeneListDatasetImporter.py`), so this client uploads one id per line.

# Measured install latency

One five-gene `genelist` published to PlasmoDB on 2026-09-04, polled every five seconds
from the 202:

| elapsed | upload | import | install |
| ---: | --- | --- | --- |
| 1.7 s | `success` | `queued` | absent |
| 7.6 s | `success` | `complete` | `PlasmoDB: complete` |

`DELETE` then returned 204, `GET /datasets/{id}` returned 404 `{"status":"not-found"}`,
and the account's listing returned to zero entries. No SLA, retry budget or duration
appears anywhere in `vdi-service`, so this is one measurement and not a guarantee.
