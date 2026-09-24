---
type: Reference
title: The VDI endpoints this client calls
description: Method, path, payload and response for every VDI user-dataset endpoint this client calls, each pinned to the RAML that defines it, plus the rnaseqrc upload contract, the two-axis install predicate, and the install latencies measured live.
tags: [vdi, user-datasets, rest, veupathdb, wdk-alignment, rnaseqrc]
generated: { by: claude-code/opus-5, at: 2026-09-05T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-24T00:00:00Z }
status: stable
---

# What this file is

VDI is a separate service from WDK. It lives at `{site_origin}/vdi` on every configured
site, and its contract is RAML, not OpenAPI: `GET /vdi/openapi.json` is 404 and `GET
/vdi/api` serves rendered HTML. This file records the part of that contract this client
depends on, pinned to the source that defines it. Why the application uses it this way is recorded in
`pathfinder: docs/knowledge/decisions/vdi-is-a-publish-target-not-a-store.md`.

Every citation is `VEuPathDB/vdi-service@d320b2464513093b29c4f638f0e836c95409d9b0`, under
`project/core/module/rest-service/`, unless it names another repository.

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
without a credential, and `VdiClient.plugins` sends none.

VDI keys every dataset to the user the token names, so every other `VdiClient` call takes
the token from the request's contextvar or the client's own `auth_token=` and never from
the deployment's settings; with neither it raises `WDKLoginRequiredError` and sends
nothing ([WDK-AUTH-005](../rules/auth-and-transport.md)).

# Endpoints

| method + path | request | response | RAML | client |
| --- | --- | --- | --- | --- |
| `POST /datasets` | `multipart/form-data`: one `details` part (JSON `DatasetPostMeta`) and one `dataFile` part per file | 202 + `Location`, body `{"datasetId": "<VdiId>"}`; 422 `invalid-input` for a `details` value outside the RAML | `api-schema/resources/dataset-list/method-post.raml`, `api-schema/types/by-path/datasets/post.raml` | `VdiClient.create_genelist` (one file), `VdiClient.create_rnaseqrc` (the rnaseqrc file set) |
| `GET /datasets/{vdi-id}` | none | 200 `DatasetDetails`; 404 deleted; 410 gone; 425 not yet in the object store | `api-schema/resources/dataset/method-get.raml`, `.../types/by-path/datasets/vdi-id/get.raml` | `VdiClient.get` |
| `GET /datasets` | `install_target`, `ownership` (`any`, `owned`, `shared`; default `any`) | 200 `DatasetListEntry[]`, newest first | `api-schema/resources/dataset-list/method-get.raml`, `.../types/by-path/datasets/get.raml:17-49` | `VdiClient.list_datasets(install_target, ownership="owned")` |
| `DELETE /datasets/{vdi-id}` | none | 204 | `api-schema/resources/dataset/method-delete.raml` | `VdiClient.delete` |
| `PUT /datasets/{vdi-id}/shares/{recipient-user-id}/offer` | `{"action": "grant" \| "revoke"}` | 204 | `api-schema/resources/dataset-shares/resource.raml`, `.../types/by-path/datasets/vdi-id/shares/put.raml` | not called; this client publishes and reads, it does not share |
| `GET /plugins` | none, no credential | 200 `PluginListItem[]` | `api-schema/resources/plugins/resource.raml`, `.../types/by-path/plugins/get.raml` | `VdiClient.plugins` |
| `GET /users/self/meta` | none | 200 `{"quota": {"limit", "usage"}}` in bytes | `api-schema/resources/users/resource.raml`, `.../types/by-path/users/user-id/meta/get.raml` | not called |

`details` carries `type: {name, version}`, `installTargets` (at least one), `name` (3 to
1024 chars), `summary` (3 to 4000), optional `description`, `origin`, `visibility` and
`dependencies` - `api-schema/types/common.raml` `DatasetMetaBase`, `DatasetTypeInput`,
`DatasetVisibility`. This client sends `origin: "direct-upload"` and one install target,
the site's own `project_id`, which is what the site's native export does
(`VEuPathDB/web-monorepo@905ce53ffd0213c9a1da4f6b6f9873768193f2d5`,
`packages/sites/genomics-site/webapp/wdkCustomization/js/client/components/records/gene-list-export-utils.tsx:366-382`).

`dependencies` is a list of objects, not strings: `DatasetDependency {resourceIdentifier
(3-50), resourceDisplayName (3-100), resourceVersion (1-50)}` (`common.raml:136-150`),
typed as `VdiDatasetDependency`. A value outside those lengths is refused at the POST with
422 and nothing is created. Measured on giardiadb.org with a 53-character identifier:

```json
{"status": "invalid-input", "errors": {"general": [],
 "byKey": {"$.details.dependencies[0]": ["exceeds the max allowed length of 50 bytes"]}}}
```

That body carries no `message`, so `VdiServiceError.detail` is built from `errors.general`
and `errors.byKey`: `POST /vdi/datasets: $.details.dependencies[0]: exceeds the max allowed
length of 50 bytes`.

`VdiId` is `^[a-zA-Z0-9_-]+$` (`common.raml`), which is why it can never be a WDK
`DatasetParam` value.

## The listing

`GET /datasets?install_target=PlasmoDB&ownership=owned` lists only the requesting
account's datasets. Measured on plasmodb.org, it differs from `GET /datasets/{vdi-id}` in
two ways:

- A failed or invalid import lists `"import": {"status": "invalid"}` with **no `messages`**
  and no install entry, while the same dataset's detail carries the plugin's message and a
  `meta: complete` install entry. VDI's text for a failure is read from the detail.
- Each row's `install` holds only the target the query names. `shares`, which the RAML
  declares, is absent from every row.

`created` is an offset timestamp in the listing (`2026-09-15T18:01:31.221543-04:00`) and a
UTC one in the detail (`...Z`).

## The plugins

`GET /plugins` lists each plugin, the types it serves with `maxFileSize` and
`allowedFileExtensions`, and optional `installTargets`. An empty or absent target list
means the plugin serves every site (`.../types/by-path/plugins/get.raml`); the `noop`
plugin lists `[]`. `VdiPlugin.installs_into(project_id)` reads it that way, and
`VdiPlugin.data_type(dataset_type)` finds a served type by name and version.

# The three status axes

`DatasetStatusInfo` (`common.raml`) reports `upload`, `import` and one `install` entry per
target. They move independently, and the enum members are:

- upload: `running`, `success`, `rejected`, `failed`
- import: `queued`, `in-progress`, `complete`, `invalid`, `failed`
- install: `queued`, `running`, `complete`, `failed-validation`, `failed-installation`,
  `ready-for-reinstall`, `missing-dependency`

An `install` entry has two axes of its own: `meta` (required) and `data` (optional)
(`common.raml` `DatasetInstallStatusListEntry`). The wire spells the import axis `import`,
which is a Python keyword, so the client's field is `import_` with a `validation_alias`. A
status this client does not know parses as its text rather than failing the read.

## The install predicate reads both axes of one project's entry

`meta: complete` is not an install. Every rnaseqrc upload measured reported an install
entry with `meta: complete` and no `data` within five seconds, while the import was still
`in-progress`, and some again at about 46 s with the import `complete` and `data` still
absent. The site's own predicate is (`VEuPathDB/web-monorepo@4a708e621925831280303df2a5d9f8bc98a5284b`,
`packages/libs/user-datasets/src/lib/Components/Management/DatasetManagement.tsx:352-368`):

```ts
status.import.status === 'complete' &&
status.install.some((it) => it.installTarget === projectId &&
  it.data?.status === 'complete' && (it.meta == null || it.meta.status === 'complete'))
```

`VdiDatasetStatus.disposition(project_id)` returns one of four `VdiInstallDisposition`
values, and `VdiDatasetDetails.installed_targets()` lists the targets whose disposition is
`installed`:

| state of this project's entry | disposition |
| --- | --- |
| upload `rejected` or `failed`; import `invalid` or `failed` | `failed` |
| upload not `success`, import absent or not `complete`, or no entry for the project | `continue` |
| `meta` or `data` is `failed-validation`, `failed-installation` or `missing-dependency` | `failed` |
| `meta` or `data` is `ready-for-reinstall` | `continue-slow` |
| `meta` and `data` both `complete` | `installed` |
| anything else, including a status this client does not know | `continue` |

An entry for another project never decides this one. `failure_messages(project_id)` returns
VDI's own text for each failed axis, upload first. The site's poller
(`.../Utils/polling-schedule.ts:31-65`) stops when every reported sub-status is `complete`,
so on the body with `meta: complete` and no `data` it stops one step early; the predicate
above does not. The schedule itself is the site's (`polling-schedule.ts:71-86`), as
`poll_interval_seconds`: 2 s before polls 1 to 5, 5 s before polls 6 to 11, then 15 s, and
60 s while `continue-slow`.

# The rnaseqrc upload

`GET /plugins` on plasmodb.org lists `rnaseqrc` 1.0, category "RNA-Seq raw counts", plugin
`wrangler`, `maxFileSize` 1073741824, `allowedFileExtensions` `[".txt", ".tsv", ".csv",
".tab"]`, `usesDataProperties` false, on the same 13 genomics targets as `genelist`. It is
not `rnaseq` 1.0 (normalized counts), which never becomes an EDA study
([genomics-and-wdk-relations](../../eda/genomics-and-wdk-relations.md)).

The contract is `VEuPathDB/web-monorepo@4a708e621925831280303df2a5d9f8bc98a5284b`,
`docs/superpowers/specs/2026-07-30-rnaseq-rc-upload-contract.md`, with the site's builder
at `packages/libs/user-datasets/src/lib/Service/utils/rnaseq-rc-data-files.ts`.
`RnaSeqRcUpload` enforces it and `VdiClient.create_rnaseqrc` sends it:

- One `details` part, then one `dataFile` part per file, each with its own file name,
  streamed from the open file. VDI packs several parts into one flat zip.
- The files, in order: one `unstranded` count file or a `sense` + `antisense` pair, a
  generated sample-info file, and a generated `manifest.tsv`.
- `manifest.tsv`: no header, `role<TAB>filename` per line, UTF-8, LF, a trailing newline,
  roles exactly `sense`, `antisense`, `unstranded`, `sample-info`; it does not list itself.
  Unstranded gives `unstranded\tHTSeq_run3.tsv\nsample-info\tsample-info.txt\n`.
- The sample-info file is `sample-info.txt`, or `sample-info-N.txt` for the lowest N that no
  count file already uses, compared without case. A count file named `manifest.tsv` in any
  case is refused, as are two count files with one name (compared without case) and a tab
  in a name.
- The sample details are 1 to 100,000 UTF-8 **bytes**, not characters, and not blank.
- The extension of each count file is checked against the plugin's
  `allowedFileExtensions`, read from `/plugins` before the POST. VDI does not do this for a
  multi-file upload: `verifyFileExtensions`
  (`src/main/kotlin/vdi/service/rest/server/services/dataset/upload-common.kt:60-83`)
  passes when any one file matches.

The count layout, the DESeq suitability rule and the AI sample annotation are the plugin's
(`VEuPathDB/vdi-plugin-wrangler@2a5e1714f8c7661979b0205dd342b8735ab6d0b4`, `doc/rnaseq-rc.md`).
Two measured behaviours that document does not state:

- **A sample-details column named `label` stops the import.** The same 12-sample matrix
  failed twice with it, stranded and unstranded, and installed four times without it.
  The terminal body is `import: failed` with `"import exited with unexpected status 255"`,
  not `invalid`, so the researcher gets no usable reason. The annotator writes its own
  `label` variable on the sample entity. The cause inside the plugin was not traced.
- **The reference genome is optional to VDI.** The same upload with `dependencies: []` was
  accepted and installed in 67.8 s, and its export matched the one with the genome
  ([genomics-and-wdk-relations](../../eda/genomics-and-wdk-relations.md)). Only the site's
  form requires it (`packages/libs/web-common/src/user-dataset-upload-config.tsx:572-575`).

## The reference genome

The site's form builds the dependency as `{resourceDisplayName: organism_full,
resourceIdentifier: "<projectId>-<buildNumber>_<name_for_filenames>_Genome",
resourceVersion: buildNumber}` (`user-dataset-upload-config.tsx:656-666`), from the WDK
service root and the `GenomeDataTypes` answer. Both answer with no credential.
`reference_genomes(site_id)` reads the same two and returns the same objects; on
plasmodb.org, build 71, it returns 64, including `PlasmoDB-71_Pfalciparum3D7_Genome` for
"Plasmodium falciparum 3D7". VDI stores the object exactly as sent. The `GenomeDataTypes`
report needs `"parameters": {}` ([WDK-ANS-010](../rules/searches-and-answers.md)).

Some identifiers are longer than the 50 VDI accepts: 3 of 16 on giardiadb.org (up to 53)
and 2 of 89 on tritrypdb.org (52); the other ten genomics sites stay within 50. No upload
can name those genomes, the site's form included, so `reference_genomes` leaves them out.

# Measured install latency

One five-gene `genelist` published to PlasmoDB on 2026-09-04, polled every five seconds
from the 202:

| elapsed | upload | import | install |
| ---: | --- | --- | --- |
| 1.7 s | `success` | `queued` | absent |
| 7.6 s | `success` | `complete` | `PlasmoDB: complete` |

The rnaseqrc import runs the plugin's AI sample annotation. Four uploads of one real
matrix on plasmodb.org on 2026-09-24, polled on the site's schedule: a stranded pair of
5,720 genes by 12 samples (545 KB), exported from the curated study `DS_e973eadd57`
through EDA tabular, with the genome dependency (three) or without it (one). Each cell is
the first poll that saw the state, so a state shorter than the poll gap can go unseen:

| state | first seen (s), four runs |
| --- | --- |
| POST answered 202 | 1.5, 1.6, 1.5, 1.7 |
| upload `success`, import `in-progress`, `meta: complete`, no `data` | 4.3, 4.3, 4.3, 4.5 |
| import `complete`, `meta: complete`, no `data` | 46.9, 45.6, not seen, not seen |
| `data: running` | 52.8, 51.6, 51.8, 51.9 |
| `data: complete` (installed) | 68.8, 67.5, 67.8, 67.9 |

The EDA permission entry `EDAUD_<vdiId>` appeared 1.1 to 1.2 s after `data: complete` in
every run that read it. The plugin's own four-sample fixture installed in 20.4 s
(unstranded) and 20.7 s (stranded). Failures ended sooner: `import: invalid` at 8.9 s for
negative counts, and `import: failed` at 40.2 s and 46.2 s for a `label` column.

`DELETE` returned 204 for eight datasets, and `GET /datasets/{id}` then returned 404
`{"status":"not-found"}`. Every `EDAUD_` permission entry was already gone at the first
`/eda/permissions` read after the deletes, 1.3 to 5.1 s after each `DELETE`, and
`/eda/studies` no longer listed any of them. No SLA, retry budget or duration appears
anywhere in `vdi-service`, so these are measurements and not guarantees.

# The quota

`GET /users/self/meta` answered `{"quota": {"limit": 10737418240, "usage": 180}}` for the
measuring account: 10 GiB. An upload over the remaining quota is not refused at the POST.
`submitUpload` runs `uploadFiles` on a worker pool after the 202, and
`verifyUploadFileSize` (`upload-common.kt:301-321`) throws `BadRequestException("total
upload size is larger than the remaining space allowed by the user quota (...)")`, which
the handler records as upload `rejected` with that message (`upload-common.kt:246-271`).
So an over-quota upload is a 202 followed by `upload: rejected`, and `failure_messages`
reports the quota text. This is read from source; a 10 GiB quota was not exceeded live.

# The genelist plugin

`GET https://plasmodb.org/vdi/plugins` lists `genelist` v1.0, category `Gene List`,
`maxFileSize` 1073741824, `allowedFileExtensions` `[".txt", ".csv", ".tsv"]`, and 13
install targets: AmoebaDB, CryptoDB, FungiDB, GiardiaDB, HostDB, MicrosporidiaDB,
PiroplasmaDB, PlasmoDB, ToxoDB, TrichDB, TriTrypDB, VectorBase, UniDB. The plugin's
importer splits on `[\s,;]+` and writes one id per line
(`VEuPathDB/vdi-plugin-genelist@cfb31e78a43b91f22037b1e36c7e2e4a9a17713e`,
`lib/python/eupath/GeneListDatasetImporter.py`), so this client uploads one id per line.

# The recorded bodies

The bodies above are package data under `veupathdb/testing/fixtures/vdi/`, reached as
`veupathdb.testing.FIXTURE_ROOT / "vdi"`, with `provenance.json` naming the method, URL,
status and elapsed seconds of each. The owner block and the account id inside VDI's
messages are replaced. `python -m veupathdb.devtools.vdi_capture record NAME ...` records
one install live through `VdiClient`, writes `NAME_<state>.json` per distinct state, and
deletes the dataset, confirming the 404 and the owned listing.
