---
type: Rules
title: Auth and transport rules
description: How a WDK request is identified, how WDK signals failure, and the two ways a 2xx response is not a result.
tags: [wdk-alignment, rules, auth, http]
generated: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
status: stable
---

# WDK-HTTP - the wire

### WDK-HTTP-001 - Every call but the one that resolves it addresses a concrete user id, never the `current` alias

- class: CONTRACT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/UserBundle.java#L34-L52
- anchor: src/veupathdb/wdk/strategy_api/base.py:_ensure_session
- status: ENFORCED by tests/unit/wdk/test_call_sites.py::test_wdk_http_001_only_the_resolvers_name_the_current_alias

`current` is a magic string. `UserBundle.createFromTargetId` rewrites it to whichever
identity the request authenticated as, for every verb alike, and returns a bundle whose
target is by construction the requesting user. A path built on `current` therefore cannot
fail an ownership check. If the token underneath has silently become a different guest,
`POST /users/current/steps` still returns 200 and the step lands under that guest, where
the researcher will never see it.

A concrete id removes that. The same request reaches
[`AbstractUserService.getUserBundle(Access.PRIVATE)`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/user/AbstractUserService.java#L53-L63),
the target is not the requesting user, and WDK throws `ForbiddenException`. Identical
reachability under a correct token, a loud 403 under a wrong one. That is the entire
argument for the rule, and it is the only part of it that is checkable.

`_ensure_session` resolves the id once per client from `GET /users/current` and every
later call reuses it. `src/veupathdb/wdk/current_user.py` is the other module allowed to
name the alias: reading who the token is has no concrete id to address yet.

The docstring on `_ensure_session` gives a different reason: that some deployments answer
405 to PUT, PATCH and DELETE on `/users/current`. That is unconfirmed. WDK does not
distinguish verbs here at the pinned sha, `wdk-client` defaults `userId` to `'current'` for
[PATCH](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Service/Mixins/StepsService.ts#L19-L27)
and for
[DELETE and PUT](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Service/Mixins/StepsService.ts#L114-L128)
alike, and it did not reproduce on either verification site. See
[transport-quirks](../rest/transport-quirks.md) for what was actually observed.

### WDK-HTTP-002 - Failure is a status code and a `text/plain` body, and 422 means well-formed but wrong

- class: HARD
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/provider/ExceptionMapper.java#L60-L125
- anchor: src/veupathdb/errors.py:WDKError
- status: UNENFORCED
- reason: enforced in the consuming application, at apps/api/src/pathfinder/tests/unit/ai/capabilities/test_wdk_failure_classification.py::test_wdk_http_002_a_422_serves_json_under_text_plain

One mapper converts the exceptions WDK raises deliberately into responses, so for those
the status code is the whole diagnosis:

| Status | Raised by | Means |
|---|---|---|
| 400 | `JSONException`, `RequestMisformatException`, `BadRequestException` | The request did not parse. A missing body, malformed JSON, a wrong shape. |
| 403 | `ForbiddenException` | The target user is not the requesting user, or the endpoint is registered-only. |
| 404 | `NotFoundException`, `PathParamException` | No such user, step, strategy or search - or a path parameter that is not the type the route declares. |
| 409 | `ConflictException` | A structural conflict, not a bad value. Deleting a step that belongs to a strategy is the canonical case. |
| 422 | `DataValidationException`, `WdkUserException` | The request parsed and the values are wrong: an invalid parameter value, a step that is not runnable, an invalid strategy structure. |
| 503 | `WdkServiceTemporarilyUnavailableException` | Retry later. |
| 500 | anything else | A WDK bug, with an `x-log-marker` response header to quote in a bug report. |

The table is not the whole of it. The mapper is registered for `Exception`, so it sees
essentially everything; what varies is whether it assigns a status or preserves one. Any
`WebApplicationException` outside the specific types above falls into a passthrough branch
and keeps the status it already carries, which covers 401 from `CheckLoginFilter` when an
endpoint requires a real token - WDK's own code, not the container's - and 405 from JAX-RS
when no method matches the route. When such an exception carries a cause, the mapper
recurses on `getCause()` and maps that instead, so a wrapper around a
`DataValidationException` still comes back 422. A status outside the table is therefore not
a contradiction of this rule. It is either a failure the mapper had no opinion of its own
about, or a response the application never produced, because every site fronts WDK with a
proxy that answers 502, 504 and 413 by itself. The status alone does not separate those
two; see [transport-quirks](../rest/transport-quirks.md).

Two consequences. First, every error body is `text/plain`, including the 422 body, which
contains JSON served under that content type; deciding how to read a WDK error by its
content type gets it wrong every time. Second, the 400/422 split is the difference between
"our serialization is broken" and "the scientist's parameter value is invalid", and only
one of those is worth showing a user. Nothing below 500 is worth retrying.

### WDK-HTTP-003 - A 2xx body of `{"status":"accepted","message":"WDK-DELAYED-RESULT"}` is not a result

- class: SILENT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/provider/ExceptionMapper.java#L106-L116
- anchor: src/veupathdb/wdk/_http.py:_request_attempt
- status: ENFORCED by tests/unit/wdk/test_delayed_result.py::TestRecognisedByShape::test_the_sentinel_body_is_a_delay
When the WSF plugin behind a process query has not finished,
[`ProcessQueryInstance`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/ProcessQueryInstance.java#L282-L284)
throws `WdkDelayedResultException`, and the mapper turns it into `202 Accepted` carrying
that sentinel body. It is the one WDK failure that arrives as a success.

`_request_attempt` calls `raise_for_status()`, which accepts 202, then returns the parsed
body. Callers that validate into a typed model get a confusing parse error; callers that
return raw JSON get the sentinel handed to them as data.

`wdk-client` guards this by shape rather than by status:
[it decodes the body of *every* ok response](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Service/ServiceBase.ts#L275-L287)
against
[the sentinel decoder](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Service/ServiceBase.ts#L36-L39)
and throws
[`DelayedResultError`](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Service/DelayedResultError.ts)
when it matches. Matching on 202 alone is narrower than the reference client. PathFinder
has neither guard.

### WDK-HTTP-004 - A published WDK schema binds a body only where an endpoint annotates it, and PathFinder's models are the contract everywhere else

- class: CONTRACT
- upstream: https://github.com/VEuPathDB/WDK/blob/f0a04136b658617a07c66151a49dd0787688084f/Service/src/main/java/org/gusdb/wdk/service/provider/JsonSchemaProvider.java#L84-L120
- anchor: src/veupathdb/devtools/fixtures.py:ENFORCED_SCHEMAS
- status: ENFORCED by tests/unit/devtools/test_wdk_fixture_schemas.py::test_every_recorded_fixture_passes_the_schema_its_endpoint_binds

WDK ships 78 JSON Schema files under `Service/doc/schema`. They are not the API contract.
`JsonSchemaProvider` reads a body's schema from the `@InSchema` or `@OutSchema` annotation
on the JAX-RS method, maps the dotted value onto a path with
[`cleanPath`](https://github.com/VEuPathDB/WDK/blob/f0a04136b658617a07c66151a49dd0787688084f/Service/src/main/java/org/gusdb/wdk/service/provider/JsonSchemaProvider.java#L144-L146),
and validates. An unannotated method reaches no schema at all, and 95 of WDK's 120
JAX-RS methods are unannotated. Twelve of the endpoints PathFinder calls are annotated
and bind fourteen schema names between them; those fourteen are `ENFORCED_SCHEMAS`, and
their transitive `$ref` closure - 41 files - is vendored under
`src/veupathdb/testing/fixtures/wdk/schema/` at the sha in `schema-pin.json`.
`python -m veupathdb.devtools.fixtures verify` validates every recorded fixture body
against them offline with draft-04.

Seven of the fourteen are request schemas, and a request is the direction WDK cannot check
for PathFinder: a body that breaks one is a 400 on the wire. Every body the client sends is
therefore built by the model that sends it and validated against its schema in
`tests/unit/wdk/test_request_bodies_match_wdk_schemas.py`,
which covers all seven names. Two constraints there bind the serialisation: a search config
may carry only `parameters`, `wdkWeight`, `filters` and `columnFilters`, so both writers of
`searchConfig` drop the rest, and `columnSelection` in a step's display preferences must
name at least one column.

Three facts bound how far that goes, all measured at the pinned sha.

**An annotation is not a promise the service keeps.** `wdk.answer.post-response` is bound
`@OutSchema` on the standard reporter, and a live 200 from
`POST /record-types/transcript/searches/GenesByMolecularWeight/reports/standard` fails it
with 5 draft-04 errors: `records[*].attributes` and `records[*].tables` arrive as objects
where the schema declares arrays, and the schema's `meta` subschema requires a key named
`meta` inside `meta`. The provider throws `InternalServerErrorException` on an out-schema
failure, so this body cannot be passing through it. The fixture store therefore binds that
endpoint's request schema and not its response schema.

**The endpoint that carries the parameter contract has its annotation commented out.**
[`QuestionService.java:124`](https://github.com/VEuPathDB/WDK/blob/f0a04136b658617a07c66151a49dd0787688084f/Service/src/main/java/org/gusdb/wdk/service/service/QuestionService.java#L124)
reads `//@OutSchema("wdk.questions.name.get") TODO: FIX!`. All six recorded search-detail
fixtures fail that schema, and none of the 20 parameters on the wire validates against any
of the eight `includes/params/*.json` variants.

**The parameter schemas cannot be satisfied by any document.**
[`base-param.json`](https://github.com/VEuPathDB/WDK/blob/f0a04136b658617a07c66151a49dd0787688084f/Service/doc/schema/wdk/includes/params/base-param.json#L4-L39)
sets `additionalProperties: false` and lists `length` in `required` without declaring it in
`properties`, so `length` is mandatory and forbidden at once; every concrete parameter
schema then composes that closed branch with an adding branch through `allOf`, which each
branch rejects. Last touched 2019-08-09.

So the rule has two halves. Where WDK annotates a body and the service holds to it, the
published schema is authority and drift against it is a gate failure. Everywhere else -
the parameter union above all - PathFinder's own models in
`src/veupathdb/wdk/wdk_models.py` and `wdk_parameters.py` are the contract, falsified
by a live payload rather than by a schema file. The parameter discriminants come from
[`JsonKeys.java:146-156`](https://github.com/VEuPathDB/WDK/blob/f0a04136b658617a07c66151a49dd0787688084f/Model/src/main/java/org/gusdb/wdk/core/api/JsonKeys.java#L146-L156),
edited 2026-08-03, which declares eleven; the schemas declare eight and include
`vocabulary`, a value the wire has not carried since before 2019. See
[the REST surface](../rest/endpoint-surface.md) for the per-endpoint table.

# WDK-AUTH - who the request is

### WDK-AUTH-001 - A request with no credential is not rejected; WDK mints a new guest user for it

- class: SILENT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/filter/CheckLoginFilter.java#L135-L148
- anchor: src/veupathdb/wdk/_http.py:_effective_token
- status: ENFORCED by tests/unit/wdk/test_http.py::TestAUserResourceNeedsTheUsersOwnToken::test_a_step_read_is_refused_and_never_leaves

`CheckLoginFilter` runs before every endpoint. With no bearer token it does not return
401: `isValidTokenRequired` is false and `isGuestUserAllowed` is true by default, so it
calls
[`useNewGuest`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/filter/CheckLoginFilter.java#L190-L200),
creates an unregistered user, and attaches the new token to the response.

A new one, every time. Three consecutive unauthenticated `GET /users/current` calls to
plasmodb.org on 2026-08-10 returned user ids 1248677203, 1248677213 and 1248677233, all
with `isGuest: true`. The same three calls sharing a cookie jar returned 1248677243 three
times.

So a client that drops the credential between requests is not unauthenticated. It is a
different person on each request, and WDK will answer every one of them successfully. A
step created on request one is owned by a user that no longer exists by request two;
`GET /users/current/strategies` returns `[]` rather than an error, because for that guest
it is true. This is the shape of every silent-empty in this system: a well-formed request,
a 200, and an empty answer that reads like a scientific negative.

The filter still behaves this way; what changed on 2026-08-19 is what the minted guest
can then do, which is nothing ([transport-quirks](../rest/transport-quirks.md)). So the
hazard is no longer a silent wrong answer, it is a 403 on every call. PathFinder mints
no guests and refuses a user-scoped WDK call that carries no registered token before it
leaves the process, which is what the anchor pins
(`pathfinder: docs/knowledge/decisions/wdk-requires-registered-login.md`).

### WDK-AUTH-002 - A request carries exactly one `Authorization` cookie pair

- class: SILENT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/filter/CheckLoginFilter.java#L208-L218
- anchor: src/veupathdb/wdk/_http.py:_inject_auth_cookie
- status: ENFORCED by tests/unit/wdk/test_http.py::test_replaces_jar_authorization_cookie

`findRawBearerToken` prefers the `Authorization` header and otherwise reads
`requestContext.getCookies().get(AUTHORIZATION)` - a lookup into a map keyed by cookie
name. Two pairs with that name go in, one comes out, and which one is not something WDK
specifies. Sending both is asking a coin to pick the user.

That is easy to do by accident. WDK's
[response filter](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/filter/CheckLoginFilter.java#L220-L237)
sets a guest `Authorization` cookie on every response to a request that arrived **without
a usable token**, absent or expired, because that is when and only when `useNewGuest` sets
the `tokenCookieValueToSet` property the filter is guarded on. That is narrower than "every
response", and it is still wide enough to be the hazard: the unauthenticated warmup calls
a container makes at boot are exactly the case, and they deposit a guest token in the
shared jar that outlives them. httpx then merges that jar into the cookie header before
per-request injection runs, so appending the real token would send the stale guest
alongside it. `_inject_auth_cookie` strips every jar-held `Authorization` pair from the
built request and appends exactly one.

The legacy `wdk_check_auth` cookie is cleared on every response unconditionally, which is
what makes the whole filter look like it always writes cookies. It is a different cookie
and it carries no credential.

### WDK-AUTH-003 - When the effective token changes on a shared client, the previous identity's session cookie must not survive

- class: CONTRACT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/cache/TemporaryUserDataStore.java#L16-L23
- anchor: src/veupathdb/wdk/_http.py:_init_wdk_session
- status: ENFORCED by tests/unit/wdk/test_http.py::test_clears_jsessionid_cookie_on_reinit

PathFinder shares one httpx client per site across every user, so it shares one cookie
jar. A `JSESSIONID` set while acting as user A is still in that jar when the next request
acts as user B.

Nothing is gained by keeping it. WDK's short-lived per-user state is keyed by user id, not
by servlet session, and the class that holds it says so outright: "Traditionally, this
data was stored in the user's session object; instead, we store it now in a userId-keyed
map". Identity travels in the bearer token ([WDK-AUTH-002](#wdk-auth-002---a-request-carries-exactly-one-authorization-cookie-pair)),
not in the container session. A carried-over `JSESSIONID` can therefore only ever bind a
request to the wrong container session, which is a hazard with no upside.

`_http.py` deletes the cookie and re-initializes whenever the effective token changes.
Note what the anchor is and is not: it pins PathFinder's conformance. The separate claim
that a *missing* `JSESSIONID` makes a process query return zero remains unverified and is
deliberately not a rule here - see
[transport-quirks](../rest/transport-quirks.md).
### WDK-AUTH-004 - Logging out swaps your cookie for a guest one; the bearer token stays valid

- class: SILENT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/SessionService.java#L277-L311
- anchor: src/veupathdb/wdk/auth_login.py:password_logout
- status: ENFORCED by tests/unit/wdk/test_auth_login.py::test_the_logout_sends_the_token_as_the_authorization_cookie

`processLogout` resolves the requesting user and returns early when that user is a guest.
A request carrying no credential is a guest ([WDK-AUTH-001](#wdk-auth-001---a-request-with-no-credential-is-not-rejected-wdk-mints-a-new-guest-user-for-it)),
so a logout sent without the token ends nobody's session and answers as though it did.

**Sending the credential is necessary and it is not sufficient.** Measured on
plasmodb.org on 2026-08-14 with a registered account, against
`GET /service/logout` carrying the user's `Authorization` cookie:

| | Result |
|---|---|
| Response | **307** to the site root |
| `Set-Cookie: Authorization` | a **different** token, `Max-Age=94608000` |
| That returned token | `isGuest: true`, a new user id |
| **The original token, afterwards** | **`isGuest: false`, the same user id** |

So the endpoint replaces the caller's cookie with a fresh guest one. It does not revoke
anything. The bearer token is a JWT whose
[max age is three years](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/SessionService.java#L241-L252),
and nothing observed here shortens it.

Two consequences, and the second is the one to carry:

- A logout that forwards no credential is a no-op that reports success. That part is the
  caller's to get right, and `password_logout` sends the token, reports what WDK answered,
  and warns when no session ended.
- **A logout that does everything right still leaves the token working.** "Log out" means
  the browser forgot the credential, on every VEuPathDB site, and a copy of that cookie
  taken beforehand keeps working. No client can fix this; the platform exposes no
  revocation. Treat a leaked WDK token as valid until it expires.

The same token was checked on toxodb.org and the portal after logout and answered
`isGuest: false` with the same user id on both, so this is not per-site.

