---
type: Reference
title: The JBrowse endpoints this client calls
description: The track list and the store a site's JBrowse service serves, the ranged read a genome window takes, the FASTA and index paths under the data prefix, and what QA PlasmoDB answered on 2026-10-21.
tags: [jbrowse, genome-sequence, rest, veupathdb]
generated: { by: claude-code/opus-5, at: 2026-10-21T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-10-21T00:00:00Z }
status: stable
---

# What this file is

A site serves its genome browser data under the web base, beside the WDK service:
`{web_base_url}/service/jbrowse/...`, for example
`https://qa.plasmodb.org/plasmo.qa/service/jbrowse/...`. It is not a WDK endpoint, so
[the endpoint surface](endpoint-surface.md) does not list it. The package is
`veupathdb.jbrowse`; `get_jbrowse_client(site_id)` keeps one `JBrowseClient` per site.

The falsifier is a measurement. The recorded bodies and their provenance are
`veupathdb-py: src/veupathdb/testing/fixtures/jbrowse/provenance.json`, and
`veupathdb.devtools.jbrowse_capture` records them again.

# Endpoints

| method + path | request | response | client |
| --- | --- | --- | --- |
| `GET /service/jbrowse/{kind}/{abbrev}` | `kind` is `organismSpecific`, `rnaseq` or `rnaseqJunctions`; `abbrev` is the organism abbreviation (`pfal3D7`) | 200, a JSON track list: `tracks[]` with `label`, `key`, `storeClass`, `urlTemplate`, `metadata` | `JBrowseClient.track_list` |
| `GET /service/jbrowse/store?data=<path>` | `data` is a path under the site's JBrowse data root; an optional `Range: bytes=<first>-<last>` | 200 with the whole file; 206 with the range | `JBrowseClient.store_bytes` |

A track's `urlTemplate` names the store as `/a/service/jbrowse/store?data=...`. The client
reads only the `data` value and sends it to its own site's web base.

# The genome sequence

- The `refseqs` track of `organismSpecific` is an `IndexedFasta` store. The first segment
  of a store track's `data` path is the data prefix (`Pfalciparum3D7` for `pfal3D7`);
  `data_prefix` reads it.
- The genome is `{prefix}/genomeAndProteome/fasta/genome.fasta` and its samtools index is
  the same path plus `.fai`. `parse_fai` reads the index: name, length, offset, bases per
  line, bytes per line.
- `GenomeReader.window(abbrev, seqid, start, end)` clamps the window to `1..length`, maps
  each end to a byte through the index, and reads that byte range. The window is upper
  case with no line breaks, and a read that is shorter than the window is an error.

# What the client refuses and renews

- A ranged read must answer 206. A 200 to a ranged request means the store ignored the
  range and sent the whole file, so `store_bytes` refuses it.
- The client reads the status before the body. An answer it refuses or renews is closed
  without reading its body, so a refused 200 does not download the whole file.
- Any status that is not a success raises `JBrowseError`: HTTP 502 to the host, with the
  method, the URL and the status the site answered in `upstream_status`.
- The credential is the login token in `veupathdb_auth_token_ctx`, else the shared guest
  token, sent as the `Authorization` cookie. A 401 to the shared guest renews it once and
  sends the request again; a second 401 raises `WDKLoginRequiredError`. A login token is
  never renewed. The cookie form is the one [WDK-AUTH-002](../rules/auth-and-transport.md)
  describes.

# Measured on QA PlasmoDB, 2026-10-21

| request | status |
| --- | --- |
| `GET /service/jbrowse/organismSpecific/pfal3D7` | 200, 75 tracks, data prefix `Pfalciparum3D7` |
| `GET /service/jbrowse/store?data=Pfalciparum3D7/genomeAndProteome/fasta/genome.fasta.fai` | 200 |
| `GET /service/jbrowse/store?data=Pfalciparum3D7/genomeAndProteome/fasta/genome.fasta` with `Range: bytes=7139187-7139278` (`Pf3D7_07_v3:403222-403312`) | 206 |
