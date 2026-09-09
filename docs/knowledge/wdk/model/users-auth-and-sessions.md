---
type: Reference
title: Users, auth, and what WDK means by a session
description: Guests against registered users, the Authorization bearer token, and which of the two identities in a request owns the answer.
tags: [wdk-alignment, auth, users, model]
generated: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
status: stable
---

Every permalink below is pinned to the sha recorded in [sources.md](../sources.md).

# Two kinds of user, and only one of them is a person

Every WDK request runs as a user. There is no unauthenticated mode.

A **registered user** is an account at VEuPathDB's central OAuth service, shared across
every site: the same login works on plasmodb.org and toxodb.org, and so does the token.
Their strategies persist and are theirs.

A **guest user** is a real row with a real numeric id that WDK creates on demand for a
request that arrived without a credential. A guest can do nearly everything a registered
user can - create steps, build strategies, run reports - which is what makes guests
useful and also what makes them dangerous.
[`getPrivateRegisteredUser`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/user/AbstractUserService.java#L65-L72)
is the only gate that rejects them, and few endpoints use it.

Guests are not a fallback. WDK mints a **new** one per credential-less request, so a
client that fails to carry its token is not one anonymous user, it is a stream of
strangers ([WDK-AUTH-001](../rules/auth-and-transport.md)). Nothing errors. This is the
single most important fact on this page.

# The credential is a bearer token in a cookie named `Authorization`

WDK looks for the token in an
[`Authorization` header first and an `Authorization` cookie second](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/filter/CheckLoginFilter.java#L208-L218).
The cookie is the path everything in practice uses, and PathFinder uses it too:
`_inject_auth_cookie` in `src/veupathdb/wdk/_http.py` writes exactly one such pair
onto each outgoing request ([WDK-AUTH-002](../rules/auth-and-transport.md)).

The token is a JWT. Its payload carries `is_guest`, which is how a guest token is told
from a real one without asking the server;
`src/veupathdb/wdk/auth_login.py:_is_guest_jwt` decodes exactly that claim, and
treats anything it cannot decode as a guest, because the failure of an undecodable token
should be "no privileges" rather than "assume privileges".

**How PathFinder obtains one.** `auth_login.py:password_login` POSTs `{email, password,
redirectUrl}` to the site's `/login` and reads the `Authorization` value off the
`Set-Cookie` headers of the response, returning the first non-guest one. WDK's
[`SessionService.processDbLogin`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/SessionService.java#L174-L219)
is what serves that: it exchanges the credentials for a
bearer token through the OAuth user factory and attaches the cookie with a three-year
max-age. The endpoint stays enabled on OAuth-configured production sites specifically so
that programmatic clients can log in, which is a deliberate upstream decision recorded in
a comment there, not an accident PathFinder is exploiting.

**PathFinder no longer obtains a guest one at all.** An unauthenticated
`GET /users/current` still makes WDK create a guest and hand back its token, but as of
2026-08-19 the deployment refuses that identity on the service endpoints
([transport-quirks](../rest/transport-quirks.md)), so the token opens nothing. The
minting helper is deleted and a WDK-backed request without a registered token is refused
with 401 `WDK_LOGIN_REQUIRED`
(`pathfinder: docs/knowledge/decisions/wdk-requires-registered-login.md`).

Credentials themselves live only in the environment. Nothing in this bundle, and nothing
in any document, records one.

# Logging in migrates what the guest built

[`SessionService.transferOwnership`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/SessionService.java#L221-L227)
runs on both login paths, OAuth and password, before
the success response is written. It transfers dataset ownership and strategy ownership
from the guest that made the request to the user who just authenticated.

That is why the order of operations matters to a client. Work done as a guest and then
authenticated in the same token lineage follows the user. Work done as a guest whose token
was dropped belongs to a guest nobody can name again, and no later login will find it.

# Two identities per request: requesting and target

Every user-scoped route is `/users/{userId}/...`, and WDK resolves two distinct things
from it.

The **requesting user** is whoever the token says. The **target user** is `{userId}` in
the path.
[`UserBundle`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/UserBundle.java#L34-L52)
computes the relationship between them, and
[`getUserBundle(Access)`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/user/AbstractUserService.java#L53-L63)
turns that relationship into a status code: an unresolvable target is 404, and a target
that is not the requesting user is 403 when the endpoint asks for `Access.PRIVATE`.

Which endpoints ask for what is not uniform, so here is the whole of it. All eleven
concrete services under `service/user/` were read at the pinned sha:

| Access requested | Services | Effect |
|---|---|---|
| `Access.PRIVATE` | `StepService`, `StrategyService`, `DatasetService`, `PreferenceService`, and `StepAnalysisInstanceService` and `StepAnalysisFormService` through `getStepForCurrentUser` / `getRunnableStepForCurrentUser` | Guests are permitted, on their own data only. A mismatched target is 403. |
| `Access.PRIVATE` plus a guest rejection, via [`getPrivateRegisteredUser`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/user/AbstractUserService.java#L65-L72) | `BasketService`, `FavoritesService`, and the PUT and DELETE on `ProfileService` | Registered users only. A guest gets 403 "You must log in to use this functionality." |
| `Access.PUBLIC` | [`ProfileService.getById`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/user/ProfileService.java#L40-L48), serving `GET /users/{userId}`, and [`StepAnalysisLookupMixin.getAnalysis`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/user/StepAnalysisLookupMixin.java#L44-L63), serving every `.../analyses/{analysisId}/result` verb | No ownership check from the bundle. Any caller reads any user's profile. The analysis lookup does its own two-stage check by hand instead, described below, which yields 404 or 403 depending on which stage fails. Cite `#L44-L63` for that claim, not the [`#L79-L99` overload](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/user/StepAnalysisLookupMixin.java#L79-L99), which delegates to it and only ever throws `NotFoundException`. |

`Access.ADMIN` exists on the enum and no service at this sha requests it.
`UserUtilityServices` is not user-scoped at all - it hangs off `@Path("/")` - so it has no
target user and none of this applies to it.

PathFinder reaches both `Access.PUBLIC` paths, so this is not academic.

- `GET /users/current`, the call that resolves its own id, is `ProfileService.getById`.
  `Access.PUBLIC` is immaterial there only because the target is `current`, which is the
  requesting user by construction. The same route with a number in it would let any caller
  read any user's profile.
- `POST`, `GET` and `GET .../status` on `.../analyses/{analysisId}/result` all route
  through [`StepAnalysisLookupMixin.getAnalysis`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/user/StepAnalysisLookupMixin.java#L44-L63).
  Ownership is still checked, but by hand inside that method, in two stages that produce
  different statuses:

  | Stage | Condition | Result |
  |---|---|---|
  | 1 | The analysis id does not resolve, or the `{userId}` in the path does not own the step the analysis hangs off | `NotFoundException`, **404** |
  | 2 | The path's user does own it, but the requester is not that user and supplied no matching `accessToken` query parameter | `ForbiddenException`, **403** |

  Stage 2 is the share-a-link path: it exists so a third party holding an analysis access
  token can read someone else's analysis, and it 403s when they do not hold one.
  **PathFinder can only ever hit stage 1.** It addresses a concrete id that is always its
  own ([WDK-HTTP-001](../rules/auth-and-transport.md)), so the target is the requesting
  user, stage 2's condition is false by construction, and 403 is unreachable for us.

  The operational consequence is therefore real but narrower than "this endpoint 404s
  instead of 403ing": for PathFinder, a 404 from an analysis result endpoint means either
  "no such analysis" or "wrong owner", and the two are indistinguishable from the status
  code alone. Everywhere else in the user-scoped surface those two cases are 404 and 403.

Every other user-scoped endpoint PathFinder calls is in the first row.

The alias `current` collapses the two: it makes the target the requesting user by
definition, so the ownership check cannot fail and a mismatch cannot be detected. That is
the argument for addressing a concrete id
([WDK-HTTP-001](../rules/auth-and-transport.md)), and it is a different and better
argument than the 405 folklore the code's docstring gives.

# "Session" means less than it looks like

WDK once kept short-lived per-user state in the servlet session. It does not any more.
[`TemporaryUserDataStore`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/cache/TemporaryUserDataStore.java#L16-L23)
is a user-id-keyed cache with a sixty-minute idle expiry, and its
class comment says so directly. The OAuth anti-forgery state token is what actually lives
there.

So identity is carried entirely by the bearer token. A `JSESSIONID` binds a request to a
container session and, at the pinned sha, to nothing that determines who the request is or
what it can see. That does not make it harmless on a shared client, where a stale one can
only ever bind a request to the wrong session, which is why PathFinder drops it whenever
the effective token changes ([WDK-AUTH-003](../rules/auth-and-transport.md)).

The stronger claim, that a missing `JSESSIONID` makes a process query return zero
results, is unverified and did not reproduce. It is written up as an open question in
[transport-quirks](../rest/transport-quirks.md), not as a rule.
