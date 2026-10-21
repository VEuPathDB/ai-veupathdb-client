---
type: Reference
title: The JBrowse endpoints this client calls
description: The track list and the store a site's JBrowse service serves, the ranged read a genome window takes, the FASTA and index paths under the data prefix, the tabix range read of a junction track, and what QA PlasmoDB answered on 2026-10-21.
tags: [jbrowse, genome-sequence, tabix, rna-seq-junctions, rest, veupathdb]
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
| `GET /service/jbrowse/{kind}/{abbrev}` | `kind` is `organismSpecific`, `rnaseq` or `rnaseqJunctions`; `abbrev` is the organism abbreviation (`pfal3D7`) | 200, a JSON track list: `tracks[]` with `label`, `key`, `storeClass`, `urlTemplate`, `metadata`; a multi-track (`MultiBigWig`) has `urlTemplates[]` of `url`, `name`, `color`, `alignment` instead of one `urlTemplate` | `JBrowseClient.track_list`; `JBrowseClient.junction_tracks` keeps the `GFF3Tabix` tracks of `rnaseqJunctions` |
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

# A tabix track

- A `GFF3Tabix` track is a bgzipped GFF3 file (BGZF, the SAM specification section 4.1)
  with a tabix index. The index is `tbiUrlTemplate` when the track names one, else the
  data path plus `.tbi`, the default of JBrowse's `GFF3Tabix` store
  (`GMOD/jbrowse: src/JBrowse/Store/SeqFeature/GFF3Tabix.js`). No track list on QA
  PlasmoDB names a `tbiUrlTemplate`.
- `TabixReader.lines(track, seqid, start, end)` reads the index once per path, takes the
  bins of the region (`reg2bins`, the SAM specification section 5.3), drops each chunk
  that ends before the linear index offset of the region's first 16 kb window and starts
  each kept chunk no earlier than that offset (section 5.1.3), and merges the
  overlapping chunks. Chunks whose blocks lie within one ranged read of each other share
  that read: from the first chunk's block to the last chunk's block plus 65535 bytes, the
  largest BGZF block. A chunk past that span starts a new read. More than 16 MiB over all
  reads of a region is refused before any read. Over 6,960 regions of the P. cynomolgi M
  junction file this reads 605 MB in 7,340 reads, the largest 222,328 bytes.
- The store clamps a range that runs past the end of the file: `Range:
  bytes=2656000-2721534` on the 2,656,099-byte pcynM junction file answers 206 with
  `Content-Range: bytes 2656000-2656098/2656099` and 99 bytes. So the 65535-byte
  overshoot near the end of the last indexed sequence is safe.
- The blocks are inflated and the lines filtered in a worker thread, not on the event
  loop.
- The region is 1-based and inclusive, the GFF convention. A line is kept when its
  sequence is the region's and its interval overlaps the region, so a feature that ends on
  the region start or starts on the region end is kept. The index header names the
  columns and whether they are 0-based; only a generic index (format 0, the one GFF and
  BED use) is read. A region that ends before it starts, or starts before base 1, raises
  `ValidationError` (HTTP 422).
- An index names only the sequences that hold a record. A sequence the index does not
  name raises `SequenceNotIndexedError`, a `TrackReadError` that names the track's data
  path and the sequence. An indexed sequence with no feature in the window returns no
  line. The two answers mean different things: the first can be a contig with no
  junction or a name the track spells differently, so a consumer must not read it as
  "no evidence". The pcynM junction index names 55 sequences, spelled as the gene
  record's `sequence_id` (`PcyM_07`, `PcyM_00_1`, `PcyM_MT`). The genome index has 56:
  `PcyM_API`, the apicoplast, holds no junction and is not named.
- Each block is checked: the gzip magic, the `BC` block size, the CRC32 and the inflated
  length. A chunk whose end lies in a block the read did not hold in full, a checksum
  that does not match, an index that ends early and sequence names that are not UTF-8
  raise `TrackReadError` (HTTP 502, `DATA_PARSING_ERROR`). A failed read drops the
  cached index of its track, so the next read takes the index again. A reader keeps an
  index for its own lifetime, so a consumer holds one reader for one run.
- `parse_gff_line` types one line as a `GffFeature`: nine columns, `.` for no score or
  phase, the strand one of `+ - . ?`. The attributes are split on `;` and `=`, each value
  on `,`, and then percent-decoded (GFF3 column 9), so `Parent=g1,g2` is
  `("g1", "g2")` and `Note=x%2Cy` is `("x,y",)`. An empty value (`genesourceid=`) holds
  no value, and a repeated attribute is refused.

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
| `GET /service/jbrowse/rnaseqJunctions/pcynM` | 200, one `GFF3Tabix` track, `PcynomolgiM/genomeBrowser/gff/unifiedIntronJunction.gff.gz`, no `tbiUrlTemplate` |
| `GET /service/jbrowse/rnaseq/pcynM` | 200, 112 `BigWig` tracks and 12 `MultiBigWig` tracks; each of the 336 `urlTemplates` entries has `url`, `name`, `color` and `alignment` |
| `GET /service/jbrowse/store?data=PcynomolgiM/genomeBrowser/gff/unifiedIntronJunction.gff.gz.tbi` | 200, a generic index of 55 sequences, columns 1, 4 and 5, meta `#` |
| `GET /service/jbrowse/store?data=PcynomolgiM/genomeBrowser/gff/unifiedIntronJunction.gff.gz` with `Range: bytes=1021821-1100077` (`PcyM_07:1380000-1384000`, the region of `PcyM_0736700`, `PcyM_07:1381622-1383462` on the + strand in its gene record) | 206, 35 junctions overlap the region |
| the same file with `Range: bytes=2656000-2721534`, past its last byte | 206, `Content-Range: bytes 2656000-2656098/2656099`, 99 bytes |
