---
type: Reference
title: The oracle - what this bundle cites, pinned, and how to re-verify it
description: Four upstream repositories at fixed shas, two live sites, the gap between the pinned build and the deployed one, and the manual procedure that keeps the pins honest.
tags: [wdk-alignment, sources, verification, meta]
generated: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
status: stable
---

# The repositories

Every WDK claim in this bundle resolves to one of four repositories, at the sha named
here and nowhere else. A citation elsewhere in the bundle is a permalink at one of these
shas; `scripts/check-wdk-rules.mjs` rejects any GitHub link in the bundle that is not
pinned to a 40-character sha, in rule blocks and in prose alike.

| Repository | Pinned sha | Authoritative for |
|---|---|---|
| [VEuPathDB/WDK](https://github.com/VEuPathDB/WDK/tree/e534d2e6a5119165e1742c7a9e07a371217ddda5/) | `e534d2e6a5119165e1742c7a9e07a371217ddda5` | The platform itself. Domain model (`Model/src/main/java`), the REST surface and its status codes (`Service/src/main/java`), validation, the parameter system. Highest authority: when PathFinder and this repository disagree, PathFinder is wrong. |
| [VEuPathDB/web-monorepo](https://github.com/VEuPathDB/web-monorepo/tree/63d1705463d553c0ac19ee577c1b09666597b903/) | `63d1705463d553c0ac19ee577c1b09666597b903` | The reference client. `packages/libs/wdk-client` carries the TypeScript types PathFinder's own types must match, and the request shapes a working client actually sends. Useful as evidence of intended usage, not of platform behavior: the client can be wrong about WDK in a way WDK's own source cannot. |
| [VEuPathDB/ApiCommonModel](https://github.com/VEuPathDB/ApiCommonModel/tree/301b2be012af713411e9b0e216ed93c51d04c239/) | `301b2be012af713411e9b0e216ed93c51d04c239` | The site model. `Model/lib/wdk/model/questions` and `Model/lib/wdk/model/records` hold the XML that defines which searches exist, their parameters, and their record classes. This is where a search name comes from; WDK only executes what this declares. Cited by [WDK-SITE-001..006](rules/site-model-params.md). |
| [VEuPathDB/ApiCommonWebsite](https://github.com/VEuPathDB/ApiCommonWebsite/tree/830bb57fe07fc2e4dd37b6ea2e3baae0eaee5bee/) | `830bb57fe07fc2e4dd37b6ea2e3baae0eaee5bee` | The site-specific step-analysis plugins, in `Model/src/main/java/org/apidb/apicommon/model/stepanalysis`. This is where enrichment result shapes are actually defined: WDK runs a plugin and [passes its JSON through untouched](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/user/StepAnalysisInstanceService.java#L272-L284), so no column name in an enrichment result is knowable from the WDK repository. Cited by [WDK-ANS-007](rules/searches-and-answers.md). |

**ApiCommonModel was pinned before anything cited it, and that gap is now closed.** The
row used to carry a note saying no document linked a file in it, kept there as a declared
intention rather than as evidence. The `WDK-SITE` family cites four distinct paths in it -
`geneQuestions.xml`, `geneParams.xml`, `geneQueries.xml` and `Model/bin/phyleticPatternWebService.pl` -
and the enumeration command below now returns them. The note is removed rather than
softened, because a row that says "not yet cited" is wrong the moment it stops being true
and nothing checks it.

The lesson the gap taught is kept: pin a repository when a rule needs it, and delete the
row if the material is never written. A sha nothing uses looks like evidence and is not.

ApiCommonWebsite was added later than the other three, when a reviewer pointed out that
[WDK-ANS-007](rules/searches-and-answers.md) had been written from a live response while
claiming - wrongly - that no pinned repository could source it. That was a charter
violation for as long as it stood: `conventions/maintaining-this-bundle.md` admits a WDK
concept only on pinned upstream evidence. The lesson is worth keeping: **"I could not find
it" is not "it does not exist", and the two must never be written as if they were the
same.**

The sha was re-verified on 2026-08-10 after a reviewer reported a GitHub load error
against it. It resolves: the commits API returns it with committer date 2026-08-09T18:20:12Z
and subject "ref org and exp org", `raw.githubusercontent.com` serves
`Model/lib/wdk/apiCommonModel.xml` at it with 200, and three consecutive fetches of the
HTML tree URL returned 200. The reported error was transient.

ApiCommonWebsite's sha was resolved on 2026-08-10: committer date 2026-08-09T22:28:17Z,
subject "update client", and all four files the bundle needs
(`GoEnrichmentPlugin.java`, `PathwaysEnrichmentPlugin.java`, `WordEnrichmentPlugin.java`,
`EnrichmentPluginUtil.java`) are present in the tree at it.

# The pinned sha is not the build the sites are running

This is the most important caveat in the bundle, and it is here rather than in a document
nobody re-reads.

**A rule sourced only from pinned source describes what that source does, not necessarily
what plasmodb.org and toxodb.org do.** There is direct evidence of divergence.
[`TableFieldFormatter.getTableJson`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/TableFieldFormatter.java#L43-L58)
writes eleven keys on every table object, one of them
[`supportsSingleRecordOnly`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/core/api/JsonKeys.java#L94),
whose value is a primitive boolean and so cannot be dropped the way org.json drops a null.
On 2026-08-10 every table object returned by `record-types/pathway` on **both** sites had
exactly eight keys, and that was not among them. The deployed build therefore differs from
the pin in this formatter. Detail in
[searches-and-record-classes](model/searches-and-record-classes.md).

Two more divergences were measured on 2026-08-10, and they fail in opposite directions,
which is why one example was not enough.

**The deployment can be stricter than the pin.** At this sha nothing on the write path
reads `viewFilters` out of a `searchConfig` - the line is commented out - so source alone
says the key is inert. Both sites reject it outright instead: a `PUT
.../steps/{id}/search-config` carrying it is a **400** from a JSON-schema filter sitting in
front of the parser, `object instance has properties which are not allowed by the schema:
["viewFilters"]`. Inert and refused are not the same contract, and only the second one is
what a client meets. See [WDK-FILTER-003](rules/filters.md) and
[steps-and-search-config](model/steps-and-search-config.md).

**And the deployment can simply disagree.**
[`StepService.createCustomReportAnswer`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/user/StepService.java#L239-L282)
persists `estimatedSize` from `result.getFirst().getResultSizeFactory().getDisplayResultSize()`,
and `result.getFirst()` is
[the answer value built from the spec that carries the request's view filters](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/AnswerService.java#L411-L428).
Read literally, a view-filtered step report should therefore write the view-filtered
display size onto the step. It does not: on both sites a report whose
`displayViewTotalCount` was 4 left `estimatedSize` at 2365, while `lastRunTime` advanced -
so the write ran and chose the unfiltered number. The reading that would dissolve this -
that the display-size plugin ignores view filters, making 2365 correct - was tested and is
false: `displayViewTotalCount` is that same call on the view-filtered answer and it reads
4.

**No mechanism is offered here because none was found in pinned source, and that is a
statement about where to look rather than a shrug.** The answer would live in one of two
places, both outside the four repositories: the transcript record class's
`getResultSizePlugin()`, which is site model configuration - the same blind spot that made
[WDK-ANS-007](rules/searches-and-answers.md) need a fourth pinned repository - or the
ordering, since `estimatedSize` is written before the reporter streams and
`displayViewTotalCount` is computed during. Both leads are written out in
[WDK-FILTER-005](rules/filters.md). The measurement is a finding; the explanation is an
open question with an address.

So read the pin for what a field *means* and the deployment for what is *there*. Where the
two can disagree, a rule should carry a live check, and a rule that carries none should say
so. The following rules are currently **source-only and not live-confirmed** - each is a
status-code or error-message claim read off the pinned sha:

| Rule | Unconfirmed part |
|---|---|
| [WDK-STEP-003](rules/strategies-and-steps.md) | that `PUT .../search-config` rejects a changed answer parameter |
| [WDK-STEP-004](rules/strategies-and-steps.md) | that a half-wired combined step comes back 500 rather than 422 |
| [WDK-STEP-007](rules/strategies-and-steps.md) | that deleting a step inside a strategy is a 409 |
| [WDK-ANS-001](rules/searches-and-answers.md) | the step-report half only. The search-report half was confirmed live. |
| [WDK-VALID-009](rules/validation.md) | that `EXPIRED` and `INTERRUPTED` carry `requiresRerun`. Neither status was provoked on either site; the rest of the rule's file is live-confirmed throughout. |

Each was reachable with a guest session when this list was written and needs the
registered account now (below), and each should be confirmed the next time one of them
matters. None is marked `WITHDRAWN`, because there is no evidence against any of them - only
an absence of evidence for them.

`WDK-STRAT-005` was on this list and has been removed: the
[WDK-VALID-004](rules/validation.md) experiment pushed a step tree over a deliberately
invalidated leaf on both sites on 2026-08-10 and got a **204**, which confirms the rule's
whole claim - the endpoint accepts a strategy whose parameters are invalid. This ledger is
only useful if it also records what has since been settled.

## And the mirror image: rules no pinned source can refute

The list above was the only ledger for a long time, and it is half a ledger. A rule with no
live check is a risk. **A rule with no upstream is a different and larger one**, because the
charter admits a claim only when something can prove it wrong, and for these the only thing
that can is a re-run. Nothing in the gate re-runs anything, so a rule here goes stale in
total silence - worse than a source-only rule, whose citation at least still has to resolve.

These rules are **live-only**. Their `upstream` field is real and pinned, but it establishes
the setting rather than the claim, and the claim itself is a measurement:

| Rule | What only a re-run can confirm | Re-run |
|---|---|---|
| [WDK-SITE-001](rules/site-model-params.md) | the separator between census tokens, and that the census is colon-joined. The pinned SQL proves it is a `LIKE` pattern; it does not describe the string being matched. | the probe table in the rule, against `GenesByOrthologPattern` with `organism` at *P. falciparum* 3D7 |
| [WDK-SITE-002](rules/site-model-params.md) | that the ortholog-less branch is empty for a given organism. The pinned SQL proves the branch exists and fires on a `:Y`-free pattern; only measurement says what it returns, and it may be non-zero on a site not measured. | `hsap=1T` per organism, which isolates that branch |
| [WDK-SITE-004](rules/site-model-params.md) | that the census lists codes in ascending order. The pinned citation is the client's `.sort()`, which is intent rather than data. | the six ordered pairs in the rule |
| [WDK-SITE-005](rules/site-model-params.md) | that a clade code appears nowhere in the census. The pinned citation is the vocabulary query, which says what terms exist and not which are stored. | `%MAMM:Y%` against a non-zero `%hsap:Y%` |

All four are about `apidb.PhylogeneticProfile.profile_string`, which is built by loader code
outside the four repositories. There is no fifth repository to pin here that would help:
adding one is the fix when the missing evidence exists somewhere, as it did for
ApiCommonWebsite, and it is not the fix when the artifact is a database table.

# The live sites

Source says what WDK can do. A deployment says what it does, and per the section above the
two are not the same build. Two sites are used for live verification, chosen because they
differ in size and content while running the same platform, so a claim that holds on both is
unlikely to be an artifact of one site.

| Site | Service base | Used to confirm |
|---|---|---|
| plasmodb.org | `https://plasmodb.org/plasmo/service` | 325 searches on `record-types/transcript/searches`, verified 2026-08-10; **359** on 2026-08-22. Primary site for PathFinder's own work. |
| toxodb.org | `https://toxodb.org/toxo/service` | 234 searches on the same path, same date. Confirms that per-site search availability is real, and that platform behavior is not. |
| orthomcl.org | `https://orthomcl.org/orthomcl/service` | Used once, by [WDK-SITE-003](rules/site-model-params.md), and only as a contrast. It runs the same WDK platform over a different site model, and it is the site whose `GroupsByPhyleticPattern.phyletic_expression` grammar the `profile_pattern` default was written in. It is not a general verification site: nothing else in the bundle should be confirmed there, because a claim that holds on plasmodb.org and toxodb.org and orthomcl.org is not thereby a claim about the two sites PathFinder actually uses. |

The full list of configured sites and their base paths is in
`src/veupathdb/sites.yaml`. Each is `<host>/<project
segment>/service`, and the project segment is not derivable from the host: plasmodb.org
uses `plasmo`, toxodb.org uses `toxo`, tritrypdb.org uses `tritrypdb`.

**An anonymous live check no longer works, and this is a change.** Through 2026-08-17
every verification here was a request any anonymous client could repeat. On 2026-08-22
`GET /plasmo/service/record-types/transcript/searches/GenesByMolecularWeight` with no
cookie is a **401** pointing at the API-key page, so re-verifying any rule in this bundle
now carries the registered account. The nightly lane resolves it from `WDK_TEST_EMAIL` and
`WDK_TEST_PASSWORD`, and the fixture recorder from `VEUPATHDB_AUTH_TOKEN`; no credential
is written down here or anywhere else in the repository.

Some checks need a user without needing an account. `GET /service/users/current` returns a
**guest** - `{"isGuest": true, ...}` plus an `Authorization` cookie - and a guest can create
steps, strategies and step analyses. That is how the enrichment figures in
[WDK-ANS-007](rules/searches-and-answers.md) were measured. What has changed is that the
guest identity is no longer reachable for the service reads above, so a guest is a
fallback for account-scoped work rather than a way to avoid authenticating at all.

# Re-verifying, which is manual

A sha does not decay, which is the point of pinning and also the danger. **A rule pinned
to a sha nobody has re-checked is a rule nobody has re-verified.** The gate proves the
cited lines still exist at the sha they were pinned to; it cannot know that WDK's head has
moved past them, and it will stay green forever on a rule that stopped being true a year
ago. Nothing re-pins automatically, on purpose: an automatic bump would silently repoint a
rule at code that no longer says what the rule claims.

To re-verify:

1. Fetch the current head sha of the repository being re-checked.
2. Enumerate the files this bundle cites from that repository, and diff each between the
   pinned sha and head. The bundle is its own manifest, so extract the list rather than
   keeping one by hand, which would go stale the first time a rule was added:

   ```bash
   grep -rho --exclude=sources.md 'github\.com/VEuPathDB/[^)]*' docs/knowledge \
     | sed -E 's@#L[0-9]+(-L[0-9]+)?$@@' \
     | sed -E 's@github\.com/VEuPathDB/([^/]+)/(blob|tree|raw|blame)/[0-9a-f]{40}/@\1 @' \
     | sort -u
   ```

   That prints `<repo> <repo-relative path>`, one line per cited file, line anchors
   stripped and duplicates collapsed. Fetch each path at both shas from
   `raw.githubusercontent.com` and compare, or use your own tooling on a local checkout.

   On 2026-08-10 it yielded **81 files: 73 from WDK, 5 from web-monorepo, 3 from
   ApiCommonWebsite.** Treat that as a snapshot and nothing more - **the command is the
   authority, the number is a courtesy.** It has already gone stale twice, once per
   document added, because every new rule cites files and nobody updates a count that
   nothing checks. If the figure you get back differs, the figure here is what is wrong.

   It went stale again on 2026-08-14, and the only part of that worth recording is
   qualitative: **ApiCommonModel now appears in the output** for the first time, because
   the `WDK-SITE` family cites it. A re-verification pass must therefore diff four
   repositories, not three. No new figure is written here, because the last two proved a
   figure is the wrong thing to keep.

   Three details of that command are load-bearing rather than stylistic.

   It scans **`docs/knowledge`, not `docs/knowledge/wdk`**. `scripts/check-wdk-rules.mjs`
   only enforces pinning inside `wdk/`, but a pinned citation is allowed anywhere in the
   bundle and there is one today in `decisions/upstream-is-the-falsifier.md`. Step 5 tells
   you to update every permalink, and a scan narrowed to `wdk/` would silently skip that
   one and leave a stale sha behind in a document nothing checks.

   It excludes this file, which holds the repository pins rather than citations and whose
   own example patterns would otherwise match themselves.

   And it matches on `github.com/...` without the scheme, because the gate requires every
   full `https://github.com/` URL under `wdk/` to be sha-pinned, and a search pattern
   written out in prose is not a citation and cannot be pinned. Writing the scheme here
   fails the gate, which is the gate working correctly.
3. For each cited file that changed, re-read the cited lines at head and decide, per rule,
   whether the rule is still true. A rule whose lines merely moved is re-pinned. A rule
   whose behavior changed is rewritten or withdrawn, never quietly re-pinned.
4. Re-run any live confirmation the rule records, against both sites.
5. Update the sha in the table above and every permalink that used the old one, in the
   same change. Mixed shas across the bundle mean no single upstream state was ever
   checked, which is worse than a stale pin because it looks current.
6. Run `node scripts/check-knowledge.mjs && node scripts/check-wdk-rules.mjs`.

Step 3 is the whole procedure. The rest is bookkeeping.
