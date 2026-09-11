---
type: Rules
title: Validation rules, and the four things a missing count means
description: What a validation bundle asserts and at which level, why an invalid step and a step of zero records and a lost session are three different states, and the step-analysis protocol whose successes are 202 and 204.
tags: [wdk-alignment, rules, validation, estimated-size, step-analyses]
generated: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
status: stable
---

# WDK-VALID - what "valid" asserts, and what a missing number does not

### WDK-VALID-001 - A validation bundle is `level` and `isValid`, and `errors` appears only when `isValid` is false

- class: CONTRACT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/ValidationFormatter.java#L10-L22
- anchor: src/veupathdb/domain/strategy/validation.py:StepValidationErrors
- status: ENFORCED by tests/unit/domain/strategy/test_validation.py::test_wdk_valid_001_a_bundle_without_is_valid_is_refused

`getValidationBundleJson` puts `level` and `isValid` unconditionally and adds
`errors` inside `if (!isValid)`. `errors` is exactly
`{general: [string], byKey: {name: [string]}}` - unkeyed messages about the
object, keyed messages about a named parameter. The
[service's own schema](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/doc/schema/wdk/includes/validation-bundle.json#L5-L47)
lists `["level", "isValid"]` as required and `errors` as optional, with
`additionalProperties: false` on the `errors` object and on `byKey`.

Neither direction of that conditional means what it looks like. An absent
`errors` is not "we found no errors"; it is "valid, at whatever `level` says". A
present `errors` is not "we found errors" either: both members can be empty, and
on a `NONE` bundle they always are
([WDK-VALID-002](#wdk-valid-002---isvalid-false-at-level-none-means-nobody-checked-not-that-something-is-wrong)).

This client's `StepValidation` is the right shape - `level: str`, `is_valid: bool`,
`errors: StepValidationErrors | None` - and `StepValidationErrors` splits
`general` from `by_key` correctly.

**Its defaults are the problem, and they are worse than they look.**
`StepValidation.is_valid` defaults to `True`, so a renamed or missing `isValid`
key reads as valid. But `WDKStep.validation` is itself declared
`Field(default_factory=StepValidation)`, so a step document carrying **no
`validation` object at all** also produces `is_valid == True`, at
`level == "NONE"` - a pairing WDK never emits, since a real `NONE` bundle
reports `isValid: false`
([WDK-VALID-002](#wdk-valid-002---isvalid-false-at-level-none-means-nobody-checked-not-that-something-is-wrong)).
Two independent defaults each turn an absence of evidence into a positive claim
of validity, and they compose.

That is also the reason the conformance column here is empty rather than
merely unfilled. Both tests that looked like candidates were unable to enforce
anything **because of these defaults**:
`tests/integration/strategies/test_wdk_step_validation_surfacing.py` asserts
`isinstance(v, StepValidation)` and `v.is_valid` against a live strategy, and
both assertions hold if WDK renames the key, changes the shape, or stops sending
`validation` entirely - Pydantic fills in a `True` and the test goes green over
nothing. A test cannot constrain a wire format that the model will happily
fabricate. No test in the repository reads a raw WDK validation object, and
until the defaults are removed none usefully could.

### WDK-VALID-002 - `isValid: false` at level `NONE` means nobody checked, not that something is wrong

- class: SILENT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/user/StepService.java#L116-L129
- anchor: src/veupathdb/domain/strategy/validation.py:StepValidation
- status: ENFORCED by tests/unit/domain/strategy/test_validation.py::TestAVerdictNeedsALevel::test_invalid_at_level_none_is_not_a_rejection
`GET /users/{id}/steps/{stepId}` takes a `validationLevel` query parameter.
Asked at `NONE`, both plasmodb.org and toxodb.org returned, on 2026-08-10, for a
step that is correct by every other measure:

```json
{"level": "NONE", "isValid": false, "errors": {"general": [], "byKey": {}}}
```

The same step at `SYNTACTIC`, `SEMANTIC` and `RUNNABLE` returns
`isValid: true`. Nothing about the step changed between those four requests.

**`isValid` alone is not readable.** A `NONE` bundle is the platform saying "I
did not look", and it says so with the same boolean that means "this is broken",
plus an error object with nothing in it. Read `level` first, and treat `NONE`
as no information rather than as a verdict.

This is not an obscure level. It is what
[`overwriteStepTreeAndSave`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/user/StrategyService.java#L217-L248)
builds at, which is the write behind every structural edit this client makes
([WDK-STRAT-005](strategies-and-steps.md)).

### WDK-VALID-003 - Validity is a claim about a level, and no strategy endpoint makes it at `RUNNABLE`

- class: SILENT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/user/StrategyService.java#L149-L170
- anchor: src/veupathdb/wdk/wdk_models.py:WDKStrategyDetails
- status: ENFORCED by tests/unit/domain/strategy/test_validation.py::TestWhetherAnyoneChecked::test_level_none_means_unchecked
`getStrategy` builds the strategy at `RUNNABLE`, calls
`updateStaleResultSizesOnRunnableSteps` on it, then **builds a second strategy
at `SEMANTIC`** to stamp the last-view time and hands *that* one to the
formatter. The `RUNNABLE` object is used for its side effect and discarded. The
listing endpoint never reaches `RUNNABLE` at all:
[it builds at `SYNTACTIC` with `FILL_PARAM_IF_MISSING`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/user/StrategyService.java#L80-L95),
so its `isValid` is a syntactic judgement made after WDK substituted values for
whatever was missing.

Confirmed on both sites on 2026-08-10. Every step inside
`GET /users/{id}/strategies/{id}` reported `"level": "SEMANTIC"`, while the same
step read directly reported `"level": "RUNNABLE"`.

**The two endpoints then contradict each other about the same strategy.** Over a
strategy holding one deliberately invalidated step, read in the same minute on
both sites:

| Call | `isValid` |
|---|---|
| `GET /users/{id}/strategies/{id}` | **false** |
| `GET /users/{id}/strategies` | **true** |

Neither is wrong. The list fills in whatever is missing or invalid and then asks
a syntactic question, which the substituted value passes; the detail asks a
semantic question of the value actually stored, which it fails. A client that
reads whichever endpoint it happened to call gets a coin flip on "is this
strategy broken", and the more optimistic answer comes from the endpoint a
sidebar is most likely to use.

In the same documents, the combined root step sitting on top of that invalid
leaf reported `isValid: true` - at `SEMANTIC`, where an input's validity is not
consulted at all
([WDK-VALID-004](#wdk-valid-004---an-invalid-input-invalidates-its-consumer-but-only-at-runnable)).

Neither strategy endpoint returned a `validation` object at all - only the
boolean `isValid` - because
[`getDetailedStrategyJson`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/StrategyFormatter.java#L56-L67)
passes `includeValidationObject` false and
[a null there is dropped by org.json](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/StrategyFormatter.java#L44-L53).

So `strategy.isValid == true` does **not** mean the strategy runs. It means no
step failed a semantic check - the same conclusion
[WDK-STRAT-005](strategies-and-steps.md) reaches from the write side, and whether
it runs is answered by running it.

What the flag does cover is the whole tree: a strategy's bundle is
[aggregated over every step in its map rather than taken from the root](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/Strategy.java#L263-L269),
so one broken leaf invalidates the strategy while the root's own bundle stays
clean - which is exactly the pairing measured above.

### WDK-VALID-004 - An invalid input invalidates its consumer, but only at `RUNNABLE`

- class: HARD
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/AnswerParam.java#L110-L159
- anchor: src/veupathdb/domain/strategy/validation.py:rejects
- status: ENFORCED by tests/unit/domain/strategy/test_validation.py::test_wdk_valid_004_a_runnable_refusal_is_a_rejection

`AnswerParam.validateValue` does two different jobs. Below `RUNNABLE` it checks
that the stable value is an integer or the empty string and returns valid
without ever looking the step up. At `RUNNABLE` it resolves the id against the
step container and fails four ways: the id is not in the container, the input
has no valid search, the input's record class is not one this parameter accepts,
or **the input is itself not runnable** - reported as
`The step referenced by ID 'N' is not runnable because: ` followed by the
input's entire validation bundle, pretty-printed into the message string.

So propagation is a property of the level, not of the graph, and the strategy
detail only ever shows you the level where it does not happen
([WDK-VALID-003](#wdk-valid-003---validity-is-a-claim-about-a-level-and-no-strategy-endpoint-makes-it-at-runnable)).

Demonstrated end to end on plasmodb.org and toxodb.org on 2026-08-10. A leaf was
invalidated through `PUT .../search-config?allowInvalid=true`
([WDK-VALID-006](#wdk-valid-006---a-4xx-from-a-validating-endpoint-carries-a-validation-bundle-as-its-body-and-level-unspecified-marks-the-ones-that-are-prose)),
a combined step was wired over it and a good leaf with
`PUT .../strategies/{id}/step-tree` - **204**, because that write builds at
`NONE` - and the consumer then read:

| Level | Consumer |
|---|---|
| `SEMANTIC` | `{"level":"SEMANTIC","isValid":true}` |
| `RUNNABLE` | `isValid: false`, `byKey` on `bq_left_op_...`: `The step referenced by ID '440085983' is not runnable because: {...}` |

Two things fall out of that message. It is keyed under the **answer parameter**,
not reported as a general error, so a client looking in `general` for structural
problems finds nothing. And the `{...}` is the input's whole bundle rendered by
`ValidationBundle.toString(2)`, whose field names are `keyedErrors`,
`validationLevel` and `validationStatus` - **a different JSON shape from the
`{level, isValid, errors}` bundle wrapping it**, embedded inside a string. Do
not try to parse it; re-read the input step instead.

The empty-value case is exempt and this is deliberate, not a hole.
[`Param.validate`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/Param.java#L574-L590)
short-circuits an empty value to valid when the parameter allows empty, and
[`AnswerParam.isAllowEmpty` returns true](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/AnswerParam.java#L192-L205)
with a comment saying why: a combined step must be constructible before it is
wired. Verified live on plasmodb.org on 2026-08-10 - a combined step with two
empty answer parameters and no strategy returns `isValid: true` at `RUNNABLE`.
The guard that stops that from being a loophole is not validation at all:
[the `Step` constructor throws `WdkModelException`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/Step.java#L392-L402)
if a step has a strategy and a null answer parameter, or no strategy and a
non-null one. That is a 500, not a 422.

The consequence for a client is that "this step is fine" and "this step's
inputs are fine" are two different questions, and only the second requires
asking at `RUNNABLE`.

What a client owns of this rule is the claim it reads back, and that is what
`tests/unit/domain/strategy/test_validation.py` holds: a `SEMANTIC` pass is not
a `RUNNABLE` pass, a refusal at `RUNNABLE` is a rejection, it arrives keyed
under the answer parameter with `general` empty, and the input's own bundle
inside the message stays a string. Whether WDK propagates at other levels is
the upstream half, carried by the link above.

### WDK-VALID-005 - `estimatedSize: 0` is a real result of zero; an absent key, a `-1` and an empty list are three other things entirely

- class: SILENT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/StepFormatter.java#L106-L121
- anchor: src/veupathdb/wdk/wdk_models.py:estimated_size
- status: ENFORCED by tests/unit/wdk/test_wdk_models.py::TestANegativeSizeIsNotACount::test_minus_one_reads_as_no_count
This is the rule that matters most in this file, because collapsing these four
is how a genuine scientific negative and a bug stop being distinguishable to the
person reading the screen.

`translateEstimatedSize` maps any negative to null, and its own comment records
the effect - "returning null here means the actuall property will be omitted due
to JSONObject's API", typo verbatim. Upstream of it,
[`Step.getEstimatedSize`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/Step.java#L490-L500)
returns the stored size when the spec is valid and **-1** when it is not, while
its javadoc says it returns 0. The javadoc is wrong. Do not write a client
against it.

Measured on plasmodb.org and toxodb.org on 2026-08-10, in this order, one leaf
step per strategy:

| Call | plasmodb.org | toxodb.org |
|---|---|---|
| `GET .../steps/{id}` before any strategy read | **absent** | absent |
| `GET .../strategies/{id}` | top-level **-1**, step entry 3392 | top-level **-1**, step entry 3717 |
| `GET .../steps/{id}` again | 3392 | 3717 |
| `GET .../strategies` | 3392 | 3717 |
| a step whose search genuinely matches nothing | **0**, `isValid: true` | **0**, `isValid: true` |
| a step invalidated through `allowInvalid` | **absent** at every level | absent at every level |

Four distinguishable states, and each is a different sentence:

| On the wire | Means |
|---|---|
| `0` | the search ran and matched no records. A result. |
| absent, on a step | not computed yet, **or** invalid. The key cannot tell you which. |
| `-1`, on a strategy detail | the formatter was handed a copy that cannot run |
| `200 []` from `GET .../strategies` | possibly not your session any more |

The second row is the conflation that matters, and the measurement table proves
it in its first and last rows: a never-run step and an invalid step both answer
with an absent key, on both sites. **A real result of zero is the one state that
has a number.** Everything else that looks like "nothing found" is the absence
of a number, and only `validation` separates the causes.

The `-1` is structural, not a glitch.
[`getDetailedStrategyJson`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/StrategyFormatter.java#L56-L67)
overwrites the key with `strategy.getResultSize()` **without** passing it through
the translator, and
[`Strategy.getResultSize`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/Strategy.java#L519-L527)
delegates to
[`Step.getResultSize`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/Step.java#L502-L513),
which returns -1 for a spec that is not runnable - and the object being
formatted is the `SEMANTIC` rebuild, which is not runnable by construction
([WDK-VALID-003](#wdk-valid-003---validity-is-a-claim-about-a-level-and-no-strategy-endpoint-makes-it-at-runnable)).
So the strategy detail's own headline number is -1 for a strategy that is
perfectly fine, while the listing endpoint next door reports the true size.
**Read a strategy's size from the list, or from the step entries; never from the
detail's top-level key.**

The ordering in the table is the mechanism behind the third row, and it settles
what looked like a contradiction in [filters](../model/filters.md), where a step
read directly had no `estimatedSize` while its strategy reported one for that
same step.
[`updateStaleResultSizesOnRunnableSteps`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/Strategy.java#L558-L581)
runs on every `GET .../strategies/{id}` and writes each runnable step's size to
the database, so reading the strategy is what makes the step's number exist.

The fourth row is the one that does not look like it belongs, and it is why this
rule is `SILENT` rather than a formatting note. A client that has lost its
`Authorization` cookie is a new guest on every request
([WDK-AUTH-001](auth-and-transport.md)), and a new guest owns nothing. Measured
on plasmodb.org on 2026-08-10: a second guest listing strategies got `200 []`,
reading the first guest's step by concrete id got **403**, and reading it
through `/users/current/steps/{id}` got **404**. An empty workspace and a lost
identity are the same response.

The session half of that - how a client loses its identity, what the
accumulating cookie jar does to it, and the `JSESSIONID` silent-zero belief that
did **not** reproduce - is in
[transport-quirks](../rest/transport-quirks.md). Read it alongside this rule
rather than after it: the "is this us?" question below is unanswerable without
it.

Three questions, three different answers, and only one of them is a number a
scientist should be shown:

- **Is this zero?** `estimatedSize == 0` and `validation.isValid` at a level of
  `SEMANTIC` or better.
- **Is this broken?** `validation.isValid == false` at a level that is not
  `NONE`.
- **Is this us?** the strategy list is empty, or a concrete-id read is 403.

This client types `estimated_size` as `int | None`, so an absent key becomes
`None` correctly - and a `-1` becomes `-1`, a negative record count that will
propagate into whatever displays it.

**What the enforcing test would have to assert.** Written out because this is
the rule in this file whose breakage a researcher pays for, and because the
status field above is honestly empty; the test is not written here, and this
paragraph exists so that writing it later is transcription rather than
redesign.

It needs no network. `WDKStep` and `WDKStrategyDetails` in
`src/veupathdb/wdk/wdk_models.py` are plain Pydantic models, so four
`model_validate` calls over hand-built dicts cover the whole rule:

| Fixture | Assertion |
|---|---|
| a `WDKStep` payload with `"estimatedSize": 0` | `step.estimated_size == 0`, and specifically **not** `None` and **not** falsy-collapsed |
| the same payload with the `estimatedSize` key **removed** | `step.estimated_size is None` |
| the same payload with `"estimatedSize": 0` and `"validation": {"level": "SEMANTIC", "isValid": false, ...}` | `estimated_size == 0` **and** `validation.is_valid is False` - the two fields are independent, and a zero count does not imply invalidity |
| a `WDKStrategyDetails` payload with top-level `"estimatedSize": -1` | whatever the fix chooses - `is None`, or a raise - but **never** an `int` that a caller can render or sum |

The first two are the rule's core and the pair must be asserted together in one
test: separately they each pass under a model that collapses both to `None`,
which is the exact bug. `0 == None` is false and `0 is None` is false, so
`assert step.estimated_size == 0` alone is sufficient for row one only if the
model does not coerce; assert `is not None` explicitly so the intent survives a
future `Optional` refactor.

The fourth row is the only one that requires a product decision first, since
`-1` is accepted today. The first three can be written against the code as it
stands and should pass; if any fails, that is the defect this rule predicts.

Two things such a test must **not** do, both of which would recreate the
mistakes already caught in this bundle. It must not assert only that
`model_dump(model_validate(x)) == x`, which is invertibility and would pass
under a model that stored the count as a string. And it must not use a fixture
captured from a live site without recording which of the four states it was
captured in - the whole rule is that they look alike.

### WDK-VALID-006 - A 4xx from a validating endpoint carries a validation bundle as its body, and level `UNSPECIFIED` marks the ones that are prose

- class: HARD
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/ValidationFormatter.java#L24-L31
- anchor: src/veupathdb/errors.py:WDKError
- status: ENFORCED by tests/unit/rules/test_auth_and_transport_rules.py::test_wdk_valid_006_a_keyed_bundle_names_the_parameter

A validation bundle is not only a field on a resource. It is also what the
write endpoints return in the body of a 422, served as `text/plain` like every
other WDK error ([WDK-HTTP-002](auth-and-transport.md)).

Measured on plasmodb.org on 2026-08-10, and the shape on toxodb.org matched:

| Request | Status | Body |
|---|---|---|
| `POST .../steps`, unknown vocabulary term | 422 | `{"level":"SEMANTIC","isValid":false,"errors":{"general":[],"byKey":{"organism":[...]}}}` |
| `POST .../steps`, two required parameters omitted | 422 | `byKey` naming both, each `Cannot be empty.` |
| `PUT .../steps/{id}/search-config`, unknown term | 422 | same shape, level `SEMANTIC` |
| `POST .../analyses`, no parameters | 422 | same shape, level **`RUNNABLE`** |
| `POST .../steps/{id}/reports/standard` on a step not in a strategy | 422 | `{"level":"UNSPECIFIED","isValid":false,"errors":{"general":["Step 440085953 is not part of a strategy, so cannot run."],"byKey":{}}}` |

The last row comes from the second, single-argument overload of
`getValidationBundleJson`, which hard-codes `"UNSPECIFIED"` and puts the message
in `general`. **`UNSPECIFIED` therefore means "this is a sentence somebody wrote,
not the outcome of a validation run"**, and it never appears on a resource's own
`validation` field. It is the one level that tells you to show the message to a
human verbatim.

The operational consequence: a 422 body is JSON worth parsing, its `level` tells
you which check rejected you, and `byKey` names the parameter. Reading it as an
opaque string throws away the only structured account of what the scientist got
wrong.

Every row above is a write that did not happen, so the ordinary way a step goes
invalid is that the model changed under it rather than that a client sent
something bad. There is exactly one exception, and it is the only way to
reproduce an invalid step on demand:
[`putAnswerSpec` accepts an undocumented `allowInvalid` query parameter](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/user/StepService.java#L318-L337)
- the source calls it "for use by developers" - which bypasses the
throw-on-invalid path and stores the spec. Live on both sites,
`PUT .../steps/{id}/search-config?allowInvalid=true` with an unknown organism
term is a **204**, and the step then reads `isValid: false` at `SEMANTIC` and
`RUNNABLE`, `isValid: true` at `SYNTACTIC`, with no `estimatedSize` at any
level. It is the lever the propagation evidence in
[WDK-VALID-004](#wdk-valid-004---an-invalid-input-invalidates-its-consumer-but-only-at-runnable)
was pulled with.

### WDK-VALID-007 - `DISPLAYABLE` is a sixth level that the deployment emits and WDK's own step schema rejects

- class: HARD
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/user/StepAnalysisFormService.java#L108-L130
- anchor: src/veupathdb/wdk/wdk_models.py:WDKStepAnalysisTypeResponse
- status: ENFORCED by tests/unit/rules/test_validation_rules.py::test_wdk_valid_007_a_displayable_bundle_parses

[The schema include](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/doc/schema/wdk/includes/validation-bundle.json#L5-L47)
enumerates five levels and `DISPLAYABLE` is not among them.
`getStepAnalysisTypeDataFromName` builds its form spec at
`ValidationLevel.DISPLAYABLE` and passes the resulting bundle to the formatter
anyway, and that endpoint declares no `@OutSchema`, so nothing checks it.

Live on plasmodb.org and toxodb.org on 2026-08-10:

| Request | Result |
|---|---|
| `GET .../steps/{id}/analysis-types/word-enrichment` | 200, `{"level":"DISPLAYABLE","isValid":true}` |
| `GET .../steps/{id}/analyses/{analysisId}` | 200, `{"level":"DISPLAYABLE","isValid":true}` |
| `GET .../steps/{id}?validationLevel=DISPLAYABLE` | **500**, `instance value ("DISPLAYABLE") not found in enum (possible values: ["NONE","UNSPECIFIED","SYNTACTIC","SEMANTIC","RUNNABLE"])` |
| `GET .../steps/{id}?validationLevel=UNSPECIFIED` | 200 at **`RUNNABLE`** - the name is not a constant, so it fell back |
| `GET .../steps/{id}?validationLevel=<anything unrecognised>` | 200 at `RUNNABLE`, silently |

The third row is WDK rejecting its own response:
[`StepService.getStep`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/user/StepService.java#L116-L129)
carries `@OutSchema("wdk.users.steps.id.get-response")`, that schema embeds the
include above, and the level the service was asked for is not in it. The failure
is a 500 from the outbound validator, not a 400 for a bad query parameter.

**This is not a pin-versus-deployment divergence, and it must not be filed as
one.** Both halves of the contradiction are in the pinned repository at the same
sha - the schema include that omits `DISPLAYABLE` and the form service that
builds at it are two files in one checkout - so the deployment is faithfully
reproducing what the source says. What the live check adds is that the
inconsistency is reachable, not that the sites differ from the pin. The
divergence catalogue in [sources.md](../sources.md) is for cases where source
and deployment disagree; this one belongs nowhere near it, and a reader arriving
straight from that section is primed to make exactly that mistake.

The two `RUNNABLE` rows are the companion trap, and together they say something
sharper than "unknown levels fall back". The level is parsed with
`ValidationLevel.valueOf` inside `defaultOnException`, so a name the enum does
not have is not an error - it is a different question quietly answered. Since
`DISPLAYABLE` survives that parse and `UNSPECIFIED` does not, **the schema's
five-member enum contains one name the platform's own enum lacks and omits one
it has.** The two sets overlap; neither contains the other.

That inference rests on two live probes rather than on a reading of
`ValidationLevel`, which lives in `org.gusdb.fgputil` - not one of the four
repositories [sources.md](../sources.md) pins. We could not read the enum; that
is not a claim that it disagrees with anything beyond what was measured.

Two rules for a client. **Do not close the level enum** - accept an unknown
level as a string and branch on the ones you know, because the platform emits
one that its own schema forbids. And **do not send a level you have not seen
on the wire**, because a level that is legal in the model can be fatal on the
way out.

### WDK-VALID-008 - `GET .../analyses/{id}/result` answers 204 with an empty body until there is a result

- class: SILENT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/user/StepAnalysisInstanceService.java#L258-L285
- anchor: src/veupathdb/wdk/_analyses.py:get_analysis_result
- status: ENFORCED by tests/unit/rules/test_validation_rules.py::test_wdk_valid_008_an_empty_result_body_is_not_a_result

`getStepAnalysisResult` returns `Response.noContent()` when the factory has no
execution result for the instance. Confirmed on both sites on 2026-08-10:
fetching the result of a freshly created `word-enrichment` instance returns
**204, zero bytes, no content type**, and the same request after the run
completes returns 200 with the plugin's JSON.

The kick-off has its own non-200 success:
[`runAnalysis`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/user/StepAnalysisInstanceService.java#L293-L309)
returns `Response.accepted()` - a **202** carrying `{"status":"RUNNING"}`. That
is a deliberate 202, not the delayed-result sentinel that shares the code
([WDK-HTTP-003](auth-and-transport.md)); the two are told apart by the body, not
the status.

So neither end of the protocol is a 200, and the 204 is the dangerous one,
because a 204 satisfies every "did it succeed" check a client is likely to
write. `_request_attempt` turns an empty body into `None`, so
`get_analysis_result` sees no dict and raises `WDKAnalysisNotReadyError`. An
enrichment that could not be fetched then carries an `error`, which a genuine
"nothing was enriched" does not. Only
[`getStepAnalysisResultStatus`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/user/StepAnalysisInstanceService.java#L311-L322)
answers whether the run finished.


### WDK-VALID-009 - Six analysis statuses mean "re-run this instance", and two of them are also terminal

- class: CONTRACT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/analysis/ExecutionStatus.java#L3-L14
- anchor: src/veupathdb/wdk/strategy_api/analyses.py:_RETRIABLE_STATUSES
- status: ENFORCED by tests/unit/wdk/test_strategy_api_analyses.py::TestEveryRerunStatusIsRerun::test_expired_is_rerun
`ExecutionStatus` declares eleven constants, each with `requiresRerun` and
`isTerminal`. `requiresRerun` is true for `CREATED`, `STEP_REVISED`,
`INTERRUPTED`, `ERROR`, `EXPIRED` and `OUT_OF_DATE`. `isTerminal` is true for
`COMPLETE`, `INTERRUPTED` and `ERROR`. The two flags are not a partition, and
`INTERRUPTED` and `ERROR` carry both: the plugin stopped, and re-running is the
right response.

`requiresRerun` is not advice. It is the predicate WDK itself branches on:
[`StepAnalysisFactoryImpl.runAnalysis`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/analysis/StepAnalysisFactoryImpl.java#L338-L374)
re-executes when the execution is new, when the results directory is missing, or
when `existingExecution.get().getStatus().requiresRerun()` - resetting the
execution to `PENDING` and returning `RUNNING`. Otherwise it returns the
existing status and runs nothing.

So re-running means `POST` the result path on the **same** instance, and the
platform decides whether that actually re-executes. Creating a second instance
is unnecessary and loses the first's `analysisId`.

This client retries three of the six - `ERROR`, `OUT_OF_DATE`, `STEP_REVISED` -
and re-runs all five of the `requiresRerun` statuses it can observe, which is
what the platform does. `CREATED` is the sixth and needs no branch: an instance
in that state has not run yet and the poll simply waits.

The give-up message is chosen by what the status reports. `EXPIRED` means the
plugin ran past its timeout and `INTERRUPTED` means the server restarted
mid-run, so neither says anything about the data, and both say the run was cut
short rather than rejected. `ERROR`, `OUT_OF_DATE` and `STEP_REVISED` keep the
gene-set explanation.

An earlier revision of this rule attached the gene-set sentence to the
then-fatal `EXPIRED` branch. That was wrong and the correction is kept here
because the mistake is instructive: two raises in one function are easy to read
as one, and a rule that overstates a defect is as unusable as one that misses
it. The sentence remains a guess where it does fire - `OUT_OF_DATE` means the
cache was purged and `STEP_REVISED` means the step changed - which is a smaller
and rarer problem on a branch three failed re-runs deep.

This rule is `CONTRACT` because the divergence is ours: nothing in WDK rejects
the request, we simply give up early and tell the researcher something false
about why. It is also the one rule in this file with **no live confirmation** -
neither `EXPIRED` nor `INTERRUPTED` was observed on either site, both being
failure states that require a timeout or a server restart to provoke, and the
flags are internal to the model rather than visible on the wire. The evidence
here is pinned source only, which per [sources.md](../sources.md) is a weaker
claim than the rest of this file makes.

### WDK-VALID-010 - `GET .../analyses` returns two fields per instance, not the instance

- class: HARD
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/StepAnalysisFormatter.java#L84-L95
- anchor: src/veupathdb/wdk/_analyses.py:list_step_analyses
- status: ENFORCED by tests/unit/rules/test_validation_rules.py::test_wdk_valid_010_the_listing_carries_two_fields_per_instance
`instanceSummaryJson` puts `analysisId` and `displayName` and stops. The service
[builds the instances at `ValidationLevel.NONE`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/user/StepAnalysisInstanceService.java#L172-L181)
for that call, consistently: nothing in a two-field summary could carry a
validation. The
[full document](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/StepAnalysisFormatter.java#L53-L82)
- ten fields including `stepId`, `analysisName`, `status`, `parameters` and
`validation` - comes only from `GET .../analyses/{analysisId}`.

Confirmed on both sites on 2026-08-10:
`[{"displayName":"Word Enrichment","analysisId":203635253}]`.

**The listing needs its own model, and it now has one.**
`WDKStepAnalysisSummary` carries the two fields WDK emits;
`WDKStepAnalysisConfig` keeps the full instance shape the create and detail
endpoints return. Parsing the list against the instance model made every entry
fail validation, and `_validate_list` suppresses a bad entry by design so that
one cannot take down a whole list - which turned a total failure into an empty
list rather than an error.

That shape is the general hazard: per-item suppression is right for one bad
entry and indistinguishable from a correct empty answer when every entry is
bad. A model that matches the endpoint is what keeps the two apart.

### WDK-VALID-011 - An analysis form hands you defaults and analysis creation refuses to apply them

- class: SILENT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/user/StepAnalysisInstanceService.java#L117-L155
- anchor: src/veupathdb/wdk/strategy_api/analyses.py:get_analysis_type
- status: PARTIAL by tests/unit/rules/test_validation_rules.py::test_wdk_valid_011_a_form_default_is_not_applied_by_the_creation_call

`createStepAnalysis` validates the posted form parameters at
`ValidationLevel.RUNNABLE` with **`FillStrategy.NO_FILL`**, and throws
`DataValidationException` carrying the bundle if any are missing. The form
endpoint next door builds the same parameters at `DISPLAYABLE` with
[`FILL_PARAM_IF_MISSING`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/user/StepAnalysisFormService.java#L108-L130),
so it always returns a complete set of `initialDisplayValue`s.

Live on plasmodb.org and toxodb.org on 2026-08-10,
`POST .../analyses` with `{"analysisName":"word-enrichment","parameters":{}}`
returns **422** and
`byKey: {"organism":["Cannot be empty."],"pValueCutoff":["Cannot be empty."]}` -
naming the two parameters the form had just supplied values for.

The trap is that the defaults look applied. They are rendered, they are
per-site, they are correct, and they are inert until the client sends them back.
A caller that reads the form and copies every `initialDisplayValue` into the
create payload gets the analysis it asked for. A caller that proceeds with empty
parameters after a failed form read gets a guaranteed 422 rather than a degraded
run.
