---
type: Decision
title: A wire proxy replays what WDK answered, and refuses what it never saw
description: veupathdb.testing.wire records a host's WDK, EDA and VDI exchanges through a mitmproxy addon, replays them by key and write epoch, answers 418 for any request it holds no recording for, and refreshes a recording against a site by re-sending it with the minted ids mapped; a transport inside the clients and a plain HTTP replay server were rejected.
tags: [testing, e2e, replay, redaction]
generated: { by: claude-code/opus-5, at: 2026-11-24T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-11-24T00:00:00Z }
status: stable
---

# What was decided

`veupathdb.testing.wire` is the replay a host's end-to-end suite runs against. It installs with
the `wire` extra (`mitmproxy`, `cryptography`) and runs as
`python -m veupathdb.testing.wire serve --mode replay|record`.

| part | what it holds |
|---|---|
| `key` | host, method, path, sorted query and the body after three normalizers: a UUID, an ISO-8601 datetime and a multipart boundary become constants. Numbers are never normalized. |
| `changes_user_state` (`wdk/_http.py`) | the closed write set: `PUT`, `PATCH`, `DELETE`, and the creates the clients send with `idempotent=False`, the EDA analysis create and the VDI upload. Every other `POST` is a read. |
| `replay` | per key, writes in order and reads at the current write epoch; a poll repeats the last read of its epoch, and a read with none at its epoch takes the last one before it. |
| `addon` | the proxy. A token's `e2e_cassette` claim names the recording set; a request with no registered token reads `stack`. It answers `/users/current`, the OAuth JWKS (from a P-521 key made at start) and the OpenAI host itself, and never records them. |
| `redact` | every account value and every credential is replaced before a write, and a guard that shares no pattern with the redactor refuses to write a recording in which any of them is still found, in any encoding. |
| `refresh` | re-sends each recording to the site, maps every id a write minted into later requests, writes a consistent new set and a drift report. |

A request with no recording is answered with `418` and `X-Wire-Miss: 1`. WDK never sends 418, so
no client branch reads it, and it is a 4xx, so the client raises at once.

# Rejected

- **A transport inside the clients, switched by an environment variable.** It touches nine client
  constructions on a production path, and replay state would have to be shared between the api and
  worker processes of the host. The proxy holds it in one process.
- **Rewriting the site URLs to a plain HTTP replay server.** Record links, strategy URLs and the
  EDA and VDI origins derive from the site's scheme and host, so replay would change what a test
  asserts on.
- **Counting every non-search POST as a write.** Parameter refreshes, record reads and every EDA
  compute are POSTs; as writes they would move the epoch on a read and make two concurrent reads
  depend on their order.
