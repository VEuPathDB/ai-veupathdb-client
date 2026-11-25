---
type: Decision
title: A turn reads once, and a definition is kept for an hour
description: A site client keeps each search definition and record type it reads for an hour under the login that asked. Inside turn_reads it sends a strategy read and a step's standard report once until the turn writes to the account or reads fresh, and a search's context read, refresh and report once for the turn. A timed strategy cache, a holder in each caller, and the read-once scope were rejected.
tags: [wdk, http, load, strategy]
generated: { by: claude-code/opus-5.5, at: 2026-11-25T00:00:00Z }
verified: { by: claude-code/opus-5.5, at: 2026-11-25T00:00:00Z }
status: stable
---

# What was decided

`HTTPClient._request` is the one owner of every read it gives again; `held_reads.held_read`
names which reads those are and the model each one answers, and the key is the site, the
login token's hash, the method, the path and the exact parameters and body. An answer is
kept only when it parses as that model, so an empty or unreadable answer is read again.

- **Definitions, for an hour.** `GET /record-types/{type}` and
  `GET /record-types/{type}/searches/{name}` change only with a site release. One store
  per process (`held_reads.definitions()`) keeps what every site client read for
  `DEFINITION_SECONDS` on the event loop's clock, under the login that asked
  ([WDK-VOCAB-008](../wdk/rules/parameters-and-vocabularies.md)). It keeps at most
  `DEFINITION_BYTES` (64 MiB) of answer text across all sites and logins, drops the least
  recently used key first, and keeps no answer larger than that. A key names one login,
  but the answer text is stored once by its content hash, so byte-identical answers for
  two logins share one copy; the bound counts each distinct text once, and a text is freed
  when no key points to it. A vocabulary built for one user (WDK-VOCAB-008) differs in its
  bytes, so it is never shared: a login reads another login's copy only when WDK answered
  both with the same bytes. A site router reset empties the store.
- **A turn's site reads, for the turn.** Inside `turn_reads()`, a search's context read
  (`POST .../searches/{name}`), its refreshed dependent parameters and its standard report
  are sent once for each body. Their answers depend on the body and the site, not on the
  account.
- **A turn's account reads, until the account changes.** A strategy read
  (`GET /users/{user}/strategies/{id}`) and a step's standard report are sent once. A write
  (`changes_user_state`) forgets them when it ends, so the next read is what the write
  made. WDK's writes do not carry the strategy: `POST .../strategies` answers its id
  (`StrategyService.createStrategy`), and `PATCH .../strategies/{id}` and
  `PUT .../step-tree` answer nothing
  ([StrategyService.java](https://github.com/VEuPathDB/WDK/blob/6d0b82eeccc3e378c2dda0d49e4a4bc8b286b7ac/Service/src/main/java/org/gusdb/wdk/service/service/user/StrategyService.java#L97-L215)),
  so one read after the write is the copy.
- **A fresh read before a write.** `get_strategy(..., fresh=True)` forgets the turn's
  account reads and sends the read. A host reads fresh before it plans a write, so an edit
  made on the website, or in another process, is read and not overwritten.

Reads sent at once with one key are sent once: the second waits for the first. A read
still in flight when a write lands is not kept, and an account read waits while a write on
the same site and login is in flight, so it is never answered from before that write. An answer is kept as its JSON text and
parsed again for each caller, so no caller changes another's.

# What was rejected

- **A timed strategy cache.** A strategy changes with every edit on the website, so a
  read that outlives the turn can be wrong.
- **A holder in each caller.** A caller that reads through the client without the holder
  would read again, and each holder would need its own rule for writes.
- **The read-once scope beside the timed definitions.** Inside an hour the timed
  definitions answer what the scope answered, so `search_definitions_read_once` was
  deleted.
