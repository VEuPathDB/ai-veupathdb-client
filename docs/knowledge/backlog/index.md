# Backlog

Everything known to be outstanding in this repository, ranked by what blocks a
second consumer first. Each item stands alone: a reader picks one up
without the work that wrote it.

Items are removed when done, not marked done. The [log](../log.md) records what
left, so this file and the items beside it are exactly what remains.

## Ranked

1. [Two states QA does not hold on request are recorded](two-states-qa-does-not-hold-on-request-are-recorded.md) - a cached AI summary and a crashed import have no QA recording
2. [The consumer import record is measured again](the-consumer-import-record-is-measured-again.md) - both consumers read names `consumer_imports.json` does not record
3. [The session page read is observed](the-session-page-read-is-observed.md) - the `/app` GET that opens a WDK session bypasses the observer, so a host's budget undercounts what it sends to the site.
