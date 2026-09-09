---
type: Reference
title: Transport behavior that belongs to the deployment, not to the API
description: What actually happens on the wire against a live VEuPathDB site, including two long-held beliefs that did not reproduce.
tags: [wdk-alignment, rest, http, auth]
generated: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
status: stable
---

# Why this file exists separately

[endpoint-surface.md](endpoint-surface.md) describes what WDK's source says the API is.
This file describes what a live site does, which is not always the same thing, and which
is the only source for anything a proxy, a container or an operator introduced. Unless a
section names its own date, what is here was observed against the two sites in
[sources.md](../sources.md) on 2026-08-10, with no credentials, using requests anyone can
repeat.

It also carries the negative results. A belief this codebase has acted on for months and
which does not reproduce is more valuable written down than a fact everyone already knew,
because until it is written down the next person pays for it again.

# The credential is a cookie, and an unauthenticated request is handed a new one

WDK reads the bearer token from an `Authorization` header if present and from an
`Authorization` cookie otherwise, and it will happily invent an identity for a request
that has neither ([WDK-AUTH-001](../rules/auth-and-transport.md)). When it does, and only
when it does, the response carries a `Set-Cookie: Authorization=...` for the guest it just
minted, with a three-year max-age.

**A guest identity no longer buys access, as of 2026-08-19.** The deployment now
refuses programmatic calls from unregistered identities: measured on plasmodb.org and
toxodb.org that day, `GET /record-types/transcript/searches/GenesByTaxon` answers 401
"Valid API Key required for this endpoint." with no cookie and 403 "This endpoint is
only available to registered users, and requires an API key." with a freshly minted
guest cookie, while a registered user's token answers 200. `POST /users/current/steps`
behaves the same way. The minting behavior below is unchanged and still describes the
wire; what changed is that the token it hands back opens nothing. PathFinder therefore
mints no guests at all, and requires a registered login for every WDK-backed feature
(`pathfinder: docs/knowledge/decisions/wdk-requires-registered-login.md`).

Be exact about the scope, because the loose version of this sentence caused a defect in
this bundle. The response filter is guarded on a request property that `useNewGuest` is
the only thing to set, so the cookie is written for a request that arrived with no token
or an expired one, not for a request that authenticated successfully. What *is*
unconditional is the clearing of the legacy `wdk_check_auth` cookie, which carries no
credential and is why the filter looks like it always writes cookies.

Two practical consequences fall out of that, both already rules:

- A shared HTTP client accumulates guest tokens in its jar - one per unauthenticated call
  it ever made, including boot-time warmup - so a request must be built to carry exactly
  one `Authorization` pair ([WDK-AUTH-002](../rules/auth-and-transport.md)).
- A shared client also accumulates a `JSESSIONID`, which must not outlive the identity
  that created it ([WDK-AUTH-003](../rules/auth-and-transport.md)).

Nothing from an unauthenticated response should ever be logged verbatim: that is precisely
the case where a guest JWT is sitting in the `Set-Cookie` header.

# Failure arrives as `text/plain`, and sometimes as 2xx

WDK's status codes are meaningful and the taxonomy is uniform
([WDK-HTTP-002](../rules/auth-and-transport.md)), and the one case where a failure is
delivered as a success has its own rule
([WDK-HTTP-003](../rules/auth-and-transport.md)). Both belong here as much as in the
rules: the taxonomy is a property of a single JAX-RS exception mapper, so it applies
identically to every endpoint in the table, which is what makes it safe to branch on.

Uniform is not the same as complete, and the gap is worth stating precisely because it is
easy to get backwards. The mapper is registered for `Exception`, so it sees essentially
everything, WDK-raised and container-raised alike. What it does not do is give everything a
status from its own table: a `WebApplicationException` that is not one of the specific
types listed there falls into a passthrough branch and keeps the status it already carries.

So the right split is not "reaches the mapper" against "bypasses it", it is "the mapper
chose the status" against "the mapper preserved one". Both of the interesting cases go
through the mapper:

- **401 from `CheckLoginFilter`** is WDK's own code raising `NotAuthorizedException` on an
  endpoint that requires a real token. It reaches the mapper and is passed through at 401.
- **405 from JAX-RS routing** is the container raising `NotAllowedException` because no
  method matched. It reaches the mapper too, and is likewise passed through at 405.

The passthrough branch has one more wrinkle: when the exception carries a cause, the mapper
recurses on `getCause()` and maps *that* instead. So a `WebApplicationException` wrapping a
`DataValidationException` comes back as 422, not as whatever status the wrapper held.

A status outside the table therefore has two possible readings, and **the status code alone
cannot tell them apart**:

- WDK saw the failure and the mapper had no status of its own to assign, so it preserved
  the one the exception already carried. 401 and 405 above are this case.
- The request never reached WDK. Every verification site fronts the application with a
  proxy - responses from both carry `Server: nginx/1.26.1` - and a proxy answers 502, 504,
  413 and its own timeouts without the application being involved at all.

The body is usually the better signal than the status: WDK's own error responses are
`text/plain` carrying WDK's message, and a 500 from the mapper adds an `x-log-marker`
header. A proxy error is typically an HTML page with neither. Treat that as a heuristic
rather than a rule; it is a property of a deployment, which is the whole subject of this
file, and no upstream source guarantees it.

# `/users/current` and the 405 that did not reproduce

`_ensure_session` resolves a concrete numeric user id before any other call, and its
docstring says why: "Some WDK deployments allow GET/POST using `/users/current/...` but do
NOT allow PUT/PATCH/DELETE on `/users/current/...` (405 Method Not Allowed)."

That behavior could not be confirmed anywhere.

- **Not in WDK.** `UserBundle` treats `current` as a magic string for the requesting user
  with no reference to the HTTP method, and the routes are declared on a
  `@Path("/users/{userId}")` template that cannot distinguish the two forms.
- **Not in the reference client.** `wdk-client` defaults `userId` to `'current'` on
  `deleteStep`, `updateStepSearchConfig`, `patchStrategyProperties`, `putStrategyStepTree`
  and `deleteStrategy` alike, so every mutating verb goes to `/users/current/...` from a
  stock VEuPathDB frontend.
- **Not on either live site.** `OPTIONS` against the mutating paths advertises the verbs:

  | Path | `Allow` on plasmodb.org | `Allow` on toxodb.org |
  |---|---|---|
  | `/users/current/steps` | `POST,OPTIONS` | `POST,OPTIONS` |
  | `/users/current/steps/{id}` | `HEAD,DELETE,GET,OPTIONS,PATCH` | `HEAD,DELETE,GET,OPTIONS,PATCH` |
  | `/users/current/steps/{id}/search-config` | `OPTIONS,PUT` | `OPTIONS,PUT` |
  | `/users/current/strategies/{id}` | `HEAD,DELETE,GET,OPTIONS,PATCH` | `HEAD,DELETE,GET,OPTIONS,PATCH` |
  | `/users/current/strategies/{id}/step-tree` | `OPTIONS,PUT` | `OPTIONS,PUT` |

  The advertised verbs are exactly the ones the JAX-RS classes declare, and
  `/users/{numeric}/steps/{id}/search-config` advertises the same set as the `current`
  form. No route treats the alias specially.

The 405 may still be real on a site not tested here, or may have been real and since
fixed. What is certain is that it is not a property of WDK. Resolving a concrete id
remains correct, for the identity reason in
[WDK-HTTP-001](../rules/auth-and-transport.md) rather than for this one; the docstring is
the weaker argument and should not be the one anyone relies on.

# The JSESSIONID silent-zero, which is unverified

The belief, stated in `CLAUDE.md`, in two docstrings in
`src/veupathdb/wdk/_http.py`, and in the consuming application's own devtools:
a WDK process query such as `GenesByOrthologPattern` returns zero results rather than an
error when the request carries no Tomcat `JSESSIONID`.

It did not reproduce.

`POST /record-types/transcript/searches/GenesByOrthologPattern/reports/standard` on
plasmodb.org, run three ways on 2026-08-10:

| Request | `profile_pattern` | `totalCount` |
|---|---|---|
| No cookies at all | `%hsap:N%pfal:Y%` | a large result |
| No cookies at all | `%ggor:N%hsap:N%mmus:N%pfal:Y%` | 3337 |
| Cookie jar seeded by `GET /plasmo/app`, which sets `JSESSIONID` | `%ggor:N%hsap:N%mmus:N%pfal:Y%` | 3337 |

A cookie-less process query returned a full result set, and the identical query with a
session cookie returned the same count. WDK's own source points the same way: the store
that holds short-lived per-user state is keyed by user id and its class comment says the
data used to live in the session object and no longer does.

The likelier explanation for what was originally observed is
[WDK-AUTH-001](../rules/auth-and-transport.md). A client that loses its `Authorization`
cookie is a new guest on every request, and a new guest owns nothing: strategies list
empty, steps 404, and a flow that spans several requests produces exactly the "well-formed
request, 200 response, empty answer" signature the JSESSIONID note describes. PathFinder's
`JSESSIONID` handling and its `Authorization` handling were written together, so a fix
attributed to one may have been delivered by the other.

This is not written as a rule, because a rule must be sourceable and this is not. It is
recorded as an open question. Anyone who reproduces the zero should capture the request,
the site, and whether an `Authorization` cookie was present, and then it can become a rule
with real evidence behind it.

# The search-metadata read is fast, and the word-enrichment plugin answers ERROR

Two measurements from 2026-09-04, both of which need a registered account.

**Reading a search's expanded metadata is not a timeout problem.** The hidden-default
sweep opens with one `GET /record-types/transcript/searches/{name}?expandParams=true` per
search. Over the 359 transcript searches, at six concurrent requests: 355 answered 200,
the median took 0.19 s, the 95th percentile 1.83 s and the slowest 6.46 s, and the whole
phase finished in 29.5 s. Nothing came near the 30 s client timeout, so a transport
failure in that phase is a blip and not a budget that is too small; raising the timeout
would buy nothing. Four searches answer 500 rather than 200 there -
`GenesByAntibodyArraypfal3D7_microarrayAntibody_Loffler_Natural_Infection`, the same name
with the `Wiz` suffix, `GenesByICEMRHostResponse` and `GenesByICEMRHostResponseWiz`.

**Word enrichment cannot complete on either verification site.** A `word-enrichment`
analysis created on a plain `GenesByMolecularWeight` step validates `RUNNABLE` with
`isValid: true`, `POST .../analyses/{id}/result` answers `202 {"status":"RUNNING"}`, and
the status settles on `ERROR`; `GET .../result` then answers 204. Measured on a 551-gene
step on plasmodb.org and a 992-gene step on toxodb.org, with the plugin's own published
defaults plus the site's own organism. GO and pathway enrichment on the same step
complete normally, so this is the one plugin and not the analysis machinery.

This matters for [WDK-ANS-007](../rules/searches-and-answers.md): the rule says a wrong
enrichment column name yields an empty column rather than an error, and the live check
that pins the five column pairs cannot read word's pair while the plugin refuses to run.
The check records the analyses the site could not complete and holds the other four to
their pinned columns.
