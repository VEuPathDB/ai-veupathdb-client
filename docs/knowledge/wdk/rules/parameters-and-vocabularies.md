---
type: Rules
title: Parameter and vocabulary rules
description: The eleven types and the exact string each takes, the two encodings a vocabulary value can have and which one is silently wrong, and why a dependent value is only meaningful under the parent it was read with.
tags: [wdk-alignment, rules, parameters, vocabularies, dependent-params, wire-format]
generated: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
status: stable
---

# WDK-PARAM - the eleven types and what each one puts on the wire

### WDK-PARAM-001 - There are eleven parameter types; `displayType` is a fifth-and-later axis and never changes the value shape

- class: CONTRACT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/core/api/JsonKeys.java#L147-L157
- anchor: src/veupathdb/domain/parameters/values.py:ParamKind
- status: ENFORCED by tests/unit/domain/parameters/test_value_codec_wire.py::test_wdk_param_001_display_type_is_a_separate_axis

`JsonKeys` declares exactly eleven `*_PARAM_TYPE` constants, and
[`ParamFormatterFactory`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/param/ParamFormatterFactory.java#L18-L55)
is the only thing that decides which one a parameter gets. `wdk-client`'s
[`Parameter` union](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkModel.ts#L224-L234)
is the same eleven: `string`, `number`, `number-range`, `date`, `date-range`,
`timestamp`, `single-pick-vocabulary`, `multi-pick-vocabulary`, `filter`,
`input-dataset`, `input-step`.

The larger counts in circulation come from counting `wdk-client`'s eight
exported enum interfaces as types. They are not types; they are
[the cross product](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkModel.ts#L143-L167)
of two `type` discriminants with four
[`displayType`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/AbstractEnumParam.java#L85-L117)
values, and `displayType` is not even stored for most parameters -
[it is derived from `isMultiPick` when unset](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/AbstractEnumParam.java#L195-L204).

The two axes are independent live. Across plasmodb.org's transcript searches on
2026-08-10, `single-pick-vocabulary` appears as `select`, `checkBox` and
`typeAhead`, and `multi-pick-vocabulary` as all four including `treeBox`.
`GenesByLocation.organismSinglePick` is a `multi-pick-vocabulary` drawn as a
`select`; toxodb.org agrees. **A client that branches on `displayType` to decide
whether to send a list is wrong on that parameter**, which is the whole reason
this is `CONTRACT` rather than a note.

This client's `ParamKind` is exactly the eleven and is correct.

### WDK-PARAM-002 - Every parameter value is a string, including the structured ones

- class: HARD
- upstream: https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkModel.ts#L284-L286
- anchor: src/veupathdb/wdk/wdk_models.py:WDKSearchConfig
- status: ENFORCED by tests/unit/domain/parameters/test_value_codec_wire.py::test_wdk_param_002_every_kind_encodes_to_a_string

`ParameterValue` is `string` and `ParameterValues` is `Record<string, string>`.
A `number-range`, a `date-range`, a `multi-pick-vocabulary` and a `filter` all
have JSON-shaped values, and all four are **stringified into** the map rather
than nested in it. WDK's name for that string is the *stable value*.

The service reads the map with a properties parser that requires strings
([`AnswerSpecServiceFormat.parse`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/request/answer/AnswerSpecServiceFormat.java#L49-L83)),
and the sibling endpoint that takes a single value reads it with `getString`,
which is a 400 on anything else - live on plasmodb.org, sending
`changedParam.value` as a JSON array to `refreshed-dependent-params` returns
**400** `JSONObject["value"] is not a string (class org.json.JSONArray)`.

This is the rule everything below depends on. A JSON object nested where a
string belongs does not mean the same thing more conveniently; it means
nothing.

### WDK-PARAM-003 - A single-pick value is a bare term, a one-element array means the same thing, and two elements is a 500

- class: HARD
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/AbstractEnumParam.java#L772-L804
- anchor: src/veupathdb/domain/parameters/values.py:SinglePickValue
- status: ENFORCED by tests/unit/domain/parameters/test_value_codec_wire.py::test_wdk_param_003_a_single_pick_wire_value_is_the_bare_term

Internally every enum value is a JSON array.
[`standardizeStableValue`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/AbstractEnumParam.java#L748-L770)
turns an incoming value into one - parsing it as JSON if it can, wrapping it as
a single element if it cannot - and `getExternalStableValue` unwraps it again on
the way out, returning `""` for zero elements, the element for one, and
**throwing `WdkRuntimeException` for more**.

Live on plasmodb.org and toxodb.org on 2026-08-10, against
`GenesByExonCount.scope` whose terms are `Gene` and `Transcript`:

| Sent | Result |
|---|---|
| `Gene` | `isValid: true` |
| `["Gene"]` | `isValid: true` |
| `["Gene","Transcript"]` | **HTTP 500**, `Internal Error` |
| `[]` | `Cannot be empty.` |
| `Gene,Transcript` | `Invalid value 'Gene,Transcript'.` |

So the bare term and the one-element array are interchangeable, which is a
mercy, and the two-element array is not a validation failure but an unhandled
runtime exception. `getMaxSelectedCount`
[returns 1 for any single-pick parameter regardless of the model](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/AbstractEnumParam.java#L241-L256),
so there is no configuration in which a second value is legal.

The last row matters for the next rule: **single-pick does not split on
commas.** `2,-3` is a real term of `GenesByMultiBlast.MatchMismatchScore` on
both sites and it survives intact.

Nothing enforces this. `test_value_round_trip.py::test_single_pick` looks
relevant and is not: it asserts only that `decode(encode(x)) == x`, never
inspecting the encoded string, so it would pass just as well if
`SinglePickValue.to_wire` wrapped the term in an array or in quotes. No test in
the repository asserts the literal wire form of a single-pick value, and none
covers the 500 or the comma behaviour. Compare
[WDK-PARAM-004](#wdk-param-004---a-multi-pick-value-is-a-json-array-a-bare-string-is-accepted-and-split-on-commas),
whose test does constrain the encoding.

### WDK-PARAM-004 - A multi-pick value is a JSON array; a bare string is accepted and split on commas

- class: SILENT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/AbstractEnumParam.java#L748-L770
- anchor: src/veupathdb/domain/parameters/values.py:MultiPickValue
- status: ENFORCED by tests/unit/domain/parameters/test_value_codec.py::test_non_empty_selection_still_works

`standardizeStableValue` catches the `JSONException` from a non-JSON value and,
for a multi-pick parameter, falls back to `stableValue.split(",")`. The method's
[own comment](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/AbstractEnumParam.java#L748-L756)
calls this a special case for legacy comma-delimited values in old databases.
It is still live on the wire.

Confirmed on plasmodb.org and toxodb.org on 2026-08-10 against
`GenesByMolecularWeight.organism`. Sending the bare string
`Plasmodium falciparum 3D7,Plasmodium vivax P01` returns `isValid: true` and the
spec comes back holding
`["Plasmodium falciparum 3D7","Plasmodium vivax P01"]` - **two organisms from
one string, with no warning.** The same request on toxodb.org produced
`["Toxoplasma gondii ME49","Toxoplasma gondii GT1"]`.

That is why this is `SILENT` and not a compatibility note. A client that never
learned the array encoding appears to work for as long as no term contains a
comma, and then silently changes meaning on the first one that does. Terms with
commas are not rare: `GenesByReactionCompounds.chebi_compound_id` is a
`multi-pick-vocabulary` with **2,715** comma-bearing terms on plasmodb.org, such
as `C09665 ((E,E)-alpha-farnesene)`. Sent bare, that one term becomes three
invalid ones.

Send `json.dumps(list_of_terms)`. This client does, and this is one of only two
rules here whose test constrains the **encoding** rather than merely its
invertibility. The named test asserts `json.loads(to_wire()) == ["bant", "bsub"]`
and, in the same file, `to_wire() == "[]"` for the empty selection - the wire
form itself, up to JSON equivalence, so no separator-joined codec passes it.

`test_value_round_trip.py::test_terms_made_of_the_separator` is the useful
companion and was named here first. It round-trips terms made **only** of
commas, which excludes exactly the encoding this rule warns about - but only
that one: a pipe-joined codec would satisfy it. The literal assertion is the
stronger evidence, so the status field points there.

The tool surface has to carry the same shape. Making the agent hand-encode the
array was its own bug, recorded in
`pathfinder: docs/knowledge/decisions/a-multi-pick-slot-takes-a-list.md`:
a multi-pick slot typed `str` produced a Pydantic error the model read as a WDK
rejection, and it told the user WDK had refused a payload WDK accepts.

### WDK-PARAM-005 - `number-range` and `date-range` require both `min` and `max`; a one-sided range is invalid

- class: HARD
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/NumberRangeParam.java#L96-L146
- anchor: src/veupathdb/domain/parameters/canonicalize.py:close_open_range
- status: ENFORCED by tests/unit/domain/parameters/test_canonicalize.py::TestBothEndsReachTheWire::test_an_open_top_takes_the_declared_maximum
`NumberRangeParam.validateValue` calls `getDouble("min")` and `getDouble("max")`
on the parsed object. A missing key throws, and the catch turns it into
`'<value>' must be is the format {"min":<min value>,"max":<max value>}` -
including the typo.
[`DateRangeParam.validateValue`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/DateRangeParam.java#L154-L207)
does the same with `getString`.

Confirmed on both sites on 2026-08-10. Against
`GenesByIntronJunctions.percent_max`, `{"min":"20","max":"100"}` and
`{"min":20,"max":100}` are both valid - the JSON values may be strings or
numbers - while `{"min":"20"}`, `{"max":"100"}`, `[20,100]` and `20` are each
rejected with that message. Against `metrics/Awstats.date`,
`{"min":"2025-01-01"}` is rejected the same way. Reversed bounds are a separate,
clearer error on both types.

**A one-sided range never reaches the wire.** `NumberRangeValue` and
`DateRangeValue` require only one endpoint and `to_wire` omits the absent one,
so the object would be refused. `domain/parameters/canonicalize.py:close_open_range`
fills the open end from the parameter's own declared limit, and leaves the value
alone when the parameter declares none, so WDK names it rather than the client
inventing a bound. Measured on plasmodb.org on 2026-09-04 against
`GenesByIntronJunctions.percent_max`: a raw push of `{"min":"20"}` is the 422
above, and the same input through the canonicalizer becomes
`{"min":20.0,"max":100.0}` and creates a step.

### WDK-PARAM-006 - A date-range whose bounds are well-formed JSON but badly formatted dates is a 500, not a validation error

- class: HARD
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/DateRangeParam.java#L154-L207
- anchor: src/veupathdb/domain/parameters/values.py:DateRangeValue
- status: ENFORCED by tests/unit/domain/parameters/test_values.py::test_wdk_param_006_a_bound_wdk_cannot_parse_is_refused

The `try` block does two different jobs and catches only one of their failures.
`new JSONObject(rawVal)` and `getString` throw `JSONException`, which is caught.
`LocalDate.parse(..., STANDARD_DATE_FORMAT)` throws `DateTimeParseException`,
which is not a `JSONException` and is not caught anywhere on the path.

Confirmed live on 2026-08-10 on plasmodb.org and toxodb.org:
`{"min":"01/01/2025","max":"12/31/2025"}` on `metrics/Awstats.date` returns
**HTTP 500** `Internal Error`, while `{"min":"2025-01-01"}` on the same
parameter returns 200 with a validation error and `2000-01-01` returns 200 with
`The date '2000-01-01' should not be earlier than '2024-01-01'`.

So the same parameter answers three different ways depending on which layer
notices. A client cannot treat 500 from this endpoint as a server problem; it
may simply be a date in the wrong format. `DateParam` is safe here -
[it catches `DateTimeParseException` directly](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/DateParam.java#L135-L170)
- so this is a defect of the range type alone.

### WDK-PARAM-007 - A numeric bound is usually a `string` parameter, and it rejects thousands separators

- class: HARD
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/StringParam.java#L171-L203
- anchor: src/veupathdb/wdk/wdk_parameters.py:is_number
- status: PARTIAL by tests/unit/rules/test_parameter_and_vocabulary_rules.py::test_wdk_param_007_a_numeric_bound_is_a_string_parameter_flagged_is_number

`StringParam.validateValue` parses the value as a double when `isNumber` is set,
and `StringParamFormatter`
[publishes `isNumber` alongside `length` and `isMultiLine`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/param/StringParamFormatter.java#L16-L27).
The `number` type exists but is rare: live on 2026-08-10 there is exactly **one**
`number` parameter across all transcript searches on either site
(`GenesByMultiBlast.NumQueryResults`), against 524 `string` parameters on
plasmodb.org and 371 on toxodb.org - of which `min_molecular_weight` and
`max_molecular_weight` are `type: "string"`, `isNumber: true`.

The trap is that `isNumber` does not mean "parses like a number in your
language". Validation applies the model's regex *after* the double parse, and
the site regex on these bounds forbids commas. Live on both sites,
`min_molecular_weight: "10,000"` is
`'10,000' is invalid (it might contain illegal characters). It must match the
regular expression '[+-]?\d+(\.\d+)?...'` while `"abc"` is `'abc' must be a
number`. The handler that would have stripped the comma
([`StringParamHandler.toInternalValue`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/StringParamHandler.java#L40-L60))
runs only after validation has already passed.

Treating these as free text rather than as numbers is what makes a client
discard their curated defaults, recorded in
`pathfinder: docs/knowledge/decisions/numeric-default-is-not-an-example.md`.

The status is `PARTIAL` and the split is clean. The named test covers the first
half: it builds `ParameterInfo(type="string", is_number=True)` for the five live
`GenesBySnps` bounds and asserts each keeps its default, and it would fail if
`is_number` stopped being honoured. **Nothing covers the second half** - no test
asserts that a thousands separator is rejected, or exercises any value against
the parameter's regex at all.

### WDK-PARAM-008 - The revise endpoint echoes the values WDK would substitute, not the ones you sent

- class: SILENT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/QuestionService.java#L176-L213
- anchor: src/veupathdb/wdk/_searches.py:get_search_details_with_params
- status: PARTIAL by tests/unit/rules/test_parameter_and_vocabulary_rules.py::test_wdk_param_008_the_revise_endpoint_answer_is_what_wdk_substituted
`getQuestionRevise` validates the posted values at `SEMANTIC` with `NO_FILL`,
**keeps that validation bundle**, and then - if the spec was invalid - builds a
second spec with `FILL_PARAM_IF_MISSING_OR_INVALID` and renders *that* one. The
response therefore describes two different states: `validation` is about your
values, `searchData.parameters[].initialDisplayValue` is about WDK's.

Confirmed on plasmodb.org and toxodb.org on 2026-08-10 against
`GenesByMolecularWeight`. Posting only `organism` returns
`min_molecular_weight` and `max_molecular_weight` as `10000` and `50000` - the
defaults - while `validation.errors.byKey` reports `Cannot be empty.` for both.
Posting an unknown organism term returns `organism: "[]"` with the term gone.

A client that reads the echoed values as confirmation of what it sent will
believe it supplied parameters it never supplied, and will believe a rejected
term was accepted in a different form. `validation.isValid` is the only field
that answers the question actually being asked.

The same substitution runs at `refreshed-dependent-params`, where the service's
own comment says the non-stale parameters' values "may have inadvertently
changed" and are omitted from the response for that reason
([WDK-VOCAB-005](#wdk-vocab-005---refreshed-dependent-params-returns-only-the-stale-dependents-and-200--means-nothing-to-refresh)).

The echo also has to be read against the *request that produced it*. The `GET`
definition and the fallback a client takes when the contextual `POST` fails echo
the published defaults, so every value the caller set differs there and none of
those differences is a substitution. Two more read rules follow from the shapes
above: a vocabulary echo is a selection, so `["b","a"]` and `["a","b"]` are the
same answer and a tree parent expanded to its leaves matches the leaves WDK
returns; and an empty selection (`"[]"`) on a parameter the caller left unset is
WDK offering nothing, not WDK choosing. Confirmed on plasmodb.org on 2026-08-17
against `GenesByOrthologPattern`: a full context echoes `profile_pattern`,
`organism`, and both species lists back unchanged with
`validation: {level: SEMANTIC, isValid: true}`, while the static `GET` echoes
`profile_pattern: "hsap=1T"` and `organism: "[]"` at
`level: DISPLAYABLE, isValid: true` - the level does not distinguish the two.

**The comparison is per kind, because only some kinds have a canonical wire
form.** A vocabulary is compared as its selection. A filter is compared as its
clause set - each clause by field, `isRange`, `includeUnknown` and its values as
a set - because WDK stores the stable value as the caller wrote it and echoes it
back verbatim, while `FilterValue.to_wire` re-emits only the five keys
`wdk-client` declares, in its own order. Confirmed on plasmodb.org on 2026-08-30
against `GenesByNgsSnps.variation_sample_meta`: a context binding every other
parameter validates at `SEMANTIC` with `isValid: true` and echoes
`{"filters": [{"value": ["Thailand", "Cambodia"], "includeUnknown": false, "isRange": false, "type": "string", "field": "VAR_8e68b3e5", "fieldDisplayName": "Country"}]}`
unchanged, which is not the string this client would have sent for the same
filter. An `input-step` is excluded from the report entirely: its value is a
handle WDK issued and the caller wired
([WDK-PARAM-009](#wdk-param-009---input-step-and-input-dataset-values-are-bare-ids-wdk-issued-and-a-dataset-is-bound-to-its-owner)),
so it is structural rather than a value anyone chose.

### WDK-PARAM-009 - `input-step` and `input-dataset` values are bare ids WDK issued, and a dataset is bound to its owner

- class: HARD
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/AnswerParamHandler.java#L25-L32
- anchor: src/veupathdb/domain/parameters/values.py:InputStepValue
- status: ENFORCED by tests/unit/domain/parameters/test_value_codec_wire.py::test_wdk_param_009_an_input_step_wire_value_is_the_bare_id

An `input-step` stable value is `Long.toString(step.getStepId())` and is read
back with `Long.parseLong`. An `input-dataset` stable value is the dataset id
([`DatasetParamHandler.toStableValue`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/DatasetParamHandler.java#L21-L27)),
and `toSignature` on the same class throws
`Dataset does not belong to current user` when the id resolves to someone
else's dataset. Neither is a value a client may compose: both are handles WDK
issued earlier in the session.

Live on both sites, `GeneByLocusTag.ds_gene_ids` (`input-dataset`) and
`GenesByCompoundsTransform.compound_result` (`input-step`) both report
`initialDisplayValue: ""`. Empty is the only value either has before it is
wired, which is the same invariant `POST /users/{id}/steps` enforces from the
other side ([WDK-STEP-002](strategies-and-steps.md)).

This rule was briefly marked `ENFORCED by
test_value_round_trip.py::test_input_step`, and that was wrong. That test is
invertibility over arbitrary text - it would pass if `to_wire` JSON-quoted the
step id - and it says nothing about `input-dataset` and nothing about
owner-binding. It is recorded here rather than quietly deleted because a
conformance column is worth exactly as much as its worst entry.

### WDK-PARAM-010 - `initialDisplayValue` is whatever the spec happens to hold; the model default behind it is never validated and never promised to return rows

- class: SILENT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/param/ParamFormatter.java#L42-L61
- anchor: src/veupathdb/wdk/wdk_parameters.py:initial_display_value
- status: ENFORCED by tests/unit/domain/parameters/test_specs.py::TestTheReportAgreesWithTheFill::test_the_report_matches_what_the_fill_added
`ParamFormatter.getBaseJson` writes the key from
`_param.getExternalStableValue(spec.get().get(_param.getName()))` - **the value this
particular spec holds**, converted to external form. It is not `getXmlDefault()`.
[`JsonKeys`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/core/api/JsonKeys.java#L142)
labels the constant `// aka "default"`, and that comment is the source of the
misreading.

The two coincide on exactly one endpoint. `GET /record-types/{rc}/searches/{name}` builds
its spec
[with no parameter values and `FillStrategy.FILL_PARAM_IF_MISSING`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/QuestionService.java#L135-L147),
so every slot is missing and every slot is filled from
[`getDefault`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/Param.java#L622-L628),
which for a plain `Param` returns `_xmlDefaultValue` verbatim. On the revise endpoint the
same key carries the caller's own values instead, which is
[WDK-PARAM-008](#wdk-param-008---the-revise-endpoint-echoes-the-values-wdk-would-substitute-not-the-ones-you-sent).
Reading the key as "the default" is right on one endpoint and wrong on the others.

**The declared default is not checked.** The setter promises otherwise, in a javadoc
directly above a body that does nothing but assign
([`Param.setDefault`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/Param.java#L305-L312)):

```java
  /**
   * Sets and validates a default value assigned in the model XML
   *
   * @param xmlDefaultValue incoming default value
   * @throws WdkModelException if incoming value is invalid
   */
  public void setDefault(String xmlDefaultValue) throws WdkModelException {
    _xmlDefaultValue = xmlDefaultValue;
```

The RelaxNG schema types the attribute as free text -
[`<attribute name="default" />`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/lib/rng/wdkModel.rng#L288-L296)
with no `<data type>` and no pattern, beside a `visible` that does carry
`<data type="boolean"/>`. And `Param.validate` has exactly two call sites in the
repository, both inside runtime spec construction, so there is no parse-time or load-time
pass over declared defaults at all.

The one partial exception is worth stating precisely, because it makes the general rule
look narrower than it is.
[`AbstractEnumParam.getDefault`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/AbstractEnumParam.java#L543-L576)
does check a declared default against the vocabulary, but lazily, when the value is first
generated, and it only throws for a **non-dependent** enum parameter; a dependent one gets
`LOG.warn` and carries on. No non-enum type has an analogue.

**And valid has never meant "returns rows".**
[`StringParam.validateValue`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/StringParam.java#L171-L202)
is the whole contract for a `string`: number-parseability if `isNumber`, the declared
regex if there is one, and the length cap. A string that matches nothing in the database
passes all three.

I read `Param.java`, `StringParam.java`, `AbstractEnumParam.java`, `DateParam.java`,
`DateRangeParam.java`, `ParamReference.java`, `ParameterContainer.java`, `Query.java`,
`ParameterContainerInstanceSpecBuilder.java`, `AnswerSpecBuilder.java`, the four
formatters and `QuestionService.java`, and found no code on any request path that
executes a default and asserts the result is non-empty. The only row-count assertion in
the repository is the offline
[`QuestionTest`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/test/sanity/tests/QuestionTest.java#L49-L62)
CLI sanity tester, which runs the *sanity* value set - `sanityDefault` where one is
declared - and so need never exercise the value a client is shown.

So `initialDisplayValue` is a model author's example, published through a fill strategy,
with no guarantee attached at any layer. A client may use it as a starting point for a
form. A client that treats it as a value known to work is reading a promise the platform
does not make, and
[WDK-SITE-003](site-model-params.md) is what that costs on a real search.

How far that was measured is a ruling of its own. The nightly sweep binds every
required parameter from its own published default and reads the count; on
plasmodb.org on 2026-08-22, of the 237 transcript searches carrying a hidden
required default, 19 answered 200 and exactly one of those returned zero rows,
while 158 were refused at `RUNNABLE` naming only *visible* parameters and 58
answered 500. The 219 the visible refusal blocks stay unmeasured on purpose:
the sweep stops at published defaults
(`pathfinder: docs/knowledge/decisions/hidden-default-sweep-stops-at-published-defaults.md`).

### WDK-PARAM-011 - `isVisible: false` is presentation only; a hidden parameter is still required, still validated, and still default-filled

- class: CONTRACT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/ParameterContainer.java#L18-L26
- anchor: src/veupathdb/domain/parameters/specs.py:fill_hidden_required_defaults
- status: ENFORCED by tests/unit/rules/test_parameter_and_vocabulary_rules.py::test_wdk_param_011_a_hidden_required_parameter_is_filled_from_its_default

`getRequiredParams()` returns `getParamMap()` - every parameter is a required parameter -
and the
[only override](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/Query.java#L195-L215)
widens that set rather than narrowing it. The validation loop
[iterates it unfiltered](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/spec/ParameterContainerInstanceSpecBuilder.java#L124-L131),
and `Param.validate` reads `allowEmpty` and the validation level, never visibility.

A grep for `isVisible()` across the whole repository at this sha returns five hits, and
after `TimestampParam`'s own override and `Group.isVisible` only **two** of them read a
parameter's flag: `ParamReference` assigns
[the `Hidden` group when no `groupRef` is given](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/ParamReference.java#L243-L248),
and `ParamFormatter`
[publishes the boolean](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/param/ParamFormatter.java#L42-L61).
Nothing else consults it. `Param`'s own javadoc says the flag decides
["whether param should be visible in the UI"](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/Param.java#L368-L381)
and that is the entire contract.

Hidden parameters are published rather than filtered out. The only inclusion filter on the
parameter list is
[`isForInternalUseOnly`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/param/ParamContainerFormatter.java#L50-L58),
a different flag, true only for `TimestampParam`.

Live on plasmodb.org on 2026-08-14, `GenesByOrthologPattern.profile_pattern` is reported
with `isVisible: false` and `allowEmptyValue: false`, and sending it as `""` is a **422**
carrying `byKey: {"profile_pattern": ["Cannot be empty."]}`. A parameter no form draws is
refused for being absent, by name, which is the whole rule in one response.

**So a client must supply hidden required parameters, and this is why this client fills
them.** `fill_hidden_required_defaults` supplies any parameter that is not visible, not
`allowEmptyValue`, absent from the caller's values, and has an `initialDisplayValue`. That
is the correct shape of the fix and it inherits the hazard of
[WDK-PARAM-010](#wdk-param-010---initialdisplayvalue-is-whatever-the-spec-happens-to-hold-the-model-default-behind-it-is-never-validated-and-never-promised-to-return-rows)
whole: what gets filled is an unvalidated example.

One more consequence, further downstream than it looks.
[`StepFactory`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/user/StepFactory.java#L75)
loads steps out of the database with `FILL_PARAM_IF_MISSING`, while
[`AnswerSpecBuilder.build`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/answer/spec/AnswerSpecBuilder.java#L72-L94)
defaults to `NO_FILL`. A parameter omitted at creation time is refused then, and silently
defaulted on every later read of the same step.

# WDK-VOCAB - vocabularies, trees, and the parents they were read under

### WDK-VOCAB-001 - A tree vocabulary's root may be a synthetic `@@fake@@` node that is not a selectable term

- class: SILENT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/param/TreeBoxEnumParamFormatter.java#L30-L51
- anchor: src/veupathdb/domain/parameters/wdk_vocab.py:WDKTreeBoxVocabNode
- status: ENFORCED by tests/unit/rules/test_parameter_and_vocabulary_rules.py::test_wdk_vocab_001_the_synthetic_root_is_not_a_selectable_term
`getVocabularyObject` returns the single real root only when there is exactly
one and it has children. Otherwise it builds a new `EnumParamTermNode` whose
term and display are both the constant `@@fake@@`, hangs every real root off it,
and serializes that. The client type
[has no room to say which it got](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkModel.ts#L111-L124):
a `TreeBoxVocabNode` is a `{data, children}` either way.

Live on plasmodb.org on 2026-08-10, `GenesByMolecularWeight.organism` has two
real roots (`Haemoproteidae` and `Plasmodiidae`) so its 90-node tree is rooted
at `@@fake@@`. Sending `["@@fake@@"]` is rejected - but as
`Number of selected values (0) is not allowed`, not as an unknown term, so the
error does not name the thing that was wrong.

**That rejection is conditional, which is what makes this `SILENT` rather than
`HARD`.** The synthetic root selects zero leaves, and whether zero is refused
depends on the same branch as
[WDK-VOCAB-002](#wdk-vocab-002---under-countonlyleaves-selecting-a-branch-term-counts-as-selecting-nothing):
`getMinSelectedCount` yields 0 on an `allowEmpty` parameter with no explicit
minimum, so `@@fake@@` is accepted there and the search runs against an empty
selection. `GenesByMolecularWeight.organism` happens to set a minimum. A rule
converted from the 422 alone would miss the case that produces a wrong number.

A client that flattens the tree by walking every node picks up a term that
cannot be sent - and, on the wrong parameter, one that *can* be sent and means
nothing. Skip the root or drop `@@fake@@` by name; there is no flag to test.

### WDK-VOCAB-002 - Under `countOnlyLeaves`, selecting a branch term counts as selecting nothing

- class: SILENT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/AbstractEnumParam.java#L457-L467
- anchor: src/veupathdb/wdk/strategy_api/base.py:_expand_tree_params_to_leaves
- status: ENFORCED by tests/unit/wdk/test_strategy_api_base.py::TestABranchBecomesItsLeaves::test_a_top_branch_expands_to_every_leaf_under_it

`getNumSelected` builds the parameter tree, marks the selected terms on it, and
returns `tree.getSelectedLeaves().size()` when the parameter is a `treeBox` with
`countOnlyLeaves` set - which is
[the default](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/AbstractEnumParam.java#L267-L284).
A branch selection does not propagate to its children, so it contributes zero.
And that count is checked
[before the terms are checked against the vocabulary](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/AbstractEnumParam.java#L401-L455),
with an early return, so the count error is the only error you see.

Confirmed on both sites on 2026-08-10. `GenesByMolecularWeight.organism` with
`["Plasmodium falciparum"]` - a genuine vocabulary node with 20 children -
returns `Number of selected values (0) is not allowed. Must be within
( 1, unlimited )`. The identical response comes back for a term that is not in
the vocabulary at all and for `@@fake@@`. Three different mistakes, one message,
and the message names none of them.

**Why this is `SILENT` and not `HARD`, given that every measurement above is a
422.** The rejection is not unconditional - it depends on a branch neither the
count check nor the message mentions.
[`getMinSelectedCount`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/AbstractEnumParam.java#L228-L229)
returns `_minSelectedCount > 0 ? _minSelectedCount : _allowEmpty ? 0 : 1`, and
validation
[compares `numSelected < getMinSelectedCount()`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/AbstractEnumParam.java#L425-L428).
So on a parameter that sets no explicit minimum and has
[`allowEmpty`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/Param.java#L384-L391),
the minimum is **0**, `0 < 0` is false, and a branch-only selection **passes
validation and runs the search with nothing selected**. `GenesByMolecularWeight.organism`
sets a minimum, which is why it 422s; a parameter that does not is where the
silent case lives.

A converter must not read the 422 above as the whole rule. A test that only
asserts the rejection pins the loud path and leaves the silent one open, which is
how a `SILENT` rule gets marked enforced by a test that cannot see its hazard.

So "0 selected" from a tree parameter means *the terms you sent matched no
leaves*, not *you sent nothing*. This client expands parent terms to leaves at
the WDK boundary for this reason, and its tree widget had to be taught the same
rule after a correctly-scoped step rendered as an empty required field
(`pathfinder: docs/knowledge/decisions/parent-term-is-a-selection.md`).

**This client expands in two independent places, and both are named by a
test.** `ParameterCanonicalizer` in `domain/parameters/` serves the validation
path; `_expand_tree_params_to_leaves` is a separate implementation in
`integrations/`, reached from `_prepare_search_config` on every `create_step`.
Delete either and a branch term reaches WDK on that path.

**Having both is not sufficient, because order decides which one runs first.**
Parameter validation resolves the search *with the values as they arrived* so it
can read WDK's verdict, and that verdict is authoritative. A branch term sent to
that resolve scores zero selected leaves, so WDK refuses values the client was
about to expand, and the refusal is reported to the model as if the branch term
were invalid input - while every hint the model was given says a branch term is
accepted. Canonicalize first, and re-ask only when canonicalizing changed the
wire payload.

**The synthetic root is a third case and it fails in the opposite direction.**
`@@fake@@` matches the vocabulary root, so expanding it yields *every* leaf: a
criterion that removes nothing rather than one that selects nothing. The
validation path already refuses the sentinel ([WDK-VOCAB-001](#wdk-vocab-001---a-tree-vocabularys-root-may-be-a-synthetic-fake-node-that-is-not-a-selectable-term));
the expansion at the WDK boundary leaves it alone for WDK to reject.

### WDK-VOCAB-003 - `dependentParams` lists the parameters that depend on this one, and its order is meaningless

- class: CONTRACT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/Param.java#L875-L894
- anchor: src/veupathdb/wdk/wdk_parameters.py:WDKEnumParam
- status: ENFORCED by tests/unit/rules/test_parameter_and_vocabulary_rules.py::test_wdk_vocab_003_the_order_of_dependent_params_carries_nothing

The model holds the edge from child to parent -
[`AbstractDependentParam._dependedParamRefs`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/AbstractDependentParam.java#L125-L153)
- and publishes only the reverse: `ParamFormatter.getBaseJson` writes
`dependentParams` from `getDependentParams()`, the back-links registered by
`addDependentParam`. The two names differ by two letters and mean opposite
directions.

Live on plasmodb.org on 2026-08-10, `GenesByInterproDomain.domain_database`
reports `dependentParams: ["domain_typeahead"]` while `domain_typeahead`, the
parameter that actually depends on something, reports `[]`. **To find a
parameter's parents you invert the map**; there is no field that gives them to
you.

The backing collection is a `HashSet`, so order is arbitrary. Live on
plasmodb.org the same dependency set appears as
`["hard_floor", "samples_fc_ref_generic", "samples_fc_comp_generic"]` on one
microarray search and in a different order on the next. Compare as sets.

This is not a corner case: **245 of the 320 declare at least one dependency** -
320 being the plasmodb.org transcript searches whose per-search document
(`GET /record-types/transcript/searches/{name}`) resolves, out of the 325 the
list endpoint returns. `dependentParams` is a parameter field, so it is only
readable from that document, and five of the 325 return 500.

### WDK-VOCAB-004 - A dependent value is only meaningful under the parent it was read with, and WDK accepts it under any parent whose vocabulary happens to contain it

- class: SILENT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/AbstractEnumParam.java#L401-L455
- anchor: src/veupathdb/domain/parameters/value_codec.py:coerce_context_values
- status: PARTIAL by tests/unit/rules/test_parameter_and_vocabulary_rules.py::test_wdk_vocab_004_a_dependent_value_travels_with_the_parent_it_was_read_under

Validation of an enum value is set membership against the vocabulary generated
under the *current* parent values, and nothing more. There is no record of which
parent a stored value was chosen under, so a value that appears in two parents'
vocabularies is valid under both and means something different in each.

Measured on plasmodb.org on 2026-08-10 through `refreshed-dependent-params` on
`GenesByMicroarraypfal3D7_microarrayExpression_Derisi_TimeSeries_RSRCPercentile`,
whose `profileset_generic` has three values:

| `profileset_generic` | leaves | overlap with HB3 |
|---|---|---|
| DeRisi HB3 Smoothed (default) | 46 | - |
| DeRisi 3D7 Smoothed | 46 | **44** |
| DeRisi Dd2 Smoothed | 45 | 43 |

`20 Hour` is in all three and returns `isValid: true` under HB3 and under 3D7
alike. `47 Hour` exists only under HB3 and is rejected under 3D7 - but only two
terms of forty-six are like that, so a mismatched pair validates cleanly about
96 percent of the time and silently selects another strain's time course.

A client that reads a dependent vocabulary with no context is handed the
search's defaults rather than the bound parent's list, and a value absent from a
refreshed vocabulary is a value the search will refuse.
`GenesByInterproDomain.domain_typeahead` holds thousands terms under `PFAM` and
5,405 under `INTERPRO` on plasmodb.org, 2,916 and 6,592 on toxodb.org,
re-measured on both sites on 2026-08-10.

The status is `PARTIAL` because the named test covers the loud half - a value
absent from the refreshed vocabulary - and nothing covers a value present in
both.

### WDK-VOCAB-005 - `refreshed-dependent-params` returns only the stale dependents, and `200 []` means nothing to refresh

- class: SILENT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/QuestionService.java#L295-L302
- anchor: src/veupathdb/wdk/_searches.py:get_refreshed_dependent_params
- status: ENFORCED by tests/unit/rules/test_parameter_and_vocabulary_rules.py::test_wdk_vocab_005_an_empty_array_names_no_stale_dependent

The response is a JSON array of parameter documents, and the service builds it
from `changedParam.getStaleDependentParams()` with an explicit instruction to
skip everything else, under a comment saying the other parameters' values may
have been altered by the fill strategy and are not to be trusted. Staleness is
per class:
[an enum parameter is always stale](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/AbstractEnumParam.java#L706-L710)
when a parent changes, a `FilterParamNew`
[only when the parent feeds its ontology or background query](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/FilterParamNew.java#L1012-L1035),
and
[a plain parameter never](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/Param.java#L896-L918).

Live on plasmodb.org on 2026-08-10, changing `profileset_generic` on the DeRisi
percentile search returns exactly `["samples_percentile_generic"]`, and changing
`any_or_all` - which has no dependents - returns **200 with `[]`**.

Both silences are the danger. A parameter absent from the response has not been
refreshed and has not been declared unchanged; it was merely not asked about. An
empty array is not a failure and not a confirmation. Merge the returned
parameters over your own copy and leave the rest alone - and do not read the
values of the ones that did come back as the values you sent
([WDK-PARAM-008](#wdk-param-008---the-revise-endpoint-echoes-the-values-wdk-would-substitute-not-the-ones-you-sent)).

### WDK-VOCAB-006 - The refresh endpoint splits its refusals between 400 and 422, and only the 422s are about your values

- class: HARD
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/request/ParamValueSetRequest.java#L32-L64
- anchor: src/veupathdb/wdk/_searches.py:get_refreshed_dependent_params
- status: ENFORCED by tests/unit/wdk/test_searches.py::test_wdk_vocab_006_the_changed_value_is_a_string

`ParamValueSetRequest.parse` reads `contextParamValues` with `getJSONObject` and
`changedParam.value` with `getString`, and turns a `JSONException` into a
`RequestMisformatException`; the missing-`changedParam` check lives in
[the service](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/QuestionService.java#L233-L280),
which also raises `DataValidationException` when the changed value does not
survive a build with `FILL_PARAM_IF_MISSING_OR_INVALID`.

Verified live on plasmodb.org on 2026-08-10:

| Request | Status | Body |
|---|---|---|
| no `changedParam` | 400 | `'changedParam' property is required at this endpoint` |
| no `contextParamValues` | 400 | `JSONObject["contextParamValues"] not found.` |
| `changedParam.value` not a string | 400 | `JSONObject["value"] is not a string` |
| value not in the vocabulary | 422 | `The passed changed param value 'Nope' is invalid.` |
| unknown `changedParam.name` | 422 | `Parameter 'nope' is not in container 'GeneId.GenesByGenericPercentile'.` |

Two things are worth carrying away. The 422 for a bad value exists only because
the service checks whether its own fill strategy quietly replaced the value -
without that check the endpoint would have returned a perfectly good vocabulary
for a value you did not send. And the container named in the last message is the
**query** full name, which is neither the search's url segment nor its full
name: a third naming vocabulary, alongside the two in
[WDK-SEARCH-002](searches-and-answers.md).

### WDK-VOCAB-007 - A flat vocabulary's third element is the parent term, and the reference client types it as `null`

- class: CONTRACT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/EnumParamVocabInstance.java#L160-L174
- anchor: src/veupathdb/domain/parameters/wdk_vocab.py:WDKVocabTerm
- status: ENFORCED by tests/unit/domain/parameters/test_wdk_vocab.py::TestTheThirdElementIsTheParentTerm::test_the_live_parameter_parses

`EnumParamVocabInstance.getFullVocab` writes `term`, `_termDisplayMap.get(term)`
and `_termParentMap.get(term)`, and its own javadoc calls the row a
`(term, displayName, parentTerm)` tuple. `EnumParamFormatter.getVocabularyObject`
copies all three columns after asserting the row has exactly three. **The third
element is the parent term.** It is `null` only for an entry at the top of the
vocabulary.

The reference client says otherwise. At the pinned sha `wdk-client` declares
`type VocabParent = string` and then does not use it, typing the row as
[`[VocabTerm, VocabDisplay, null][]`](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkModel.ts#L104-L110).
That is the client being wrong about WDK in a way WDK's own source cannot be, so
the Java wins.

Live on plasmodb.org and toxodb.org on 2026-08-30, `GenesByOrthologPattern`
carries `phyletic_term_map` and `phyletic_indent_map` as 903-row flat
vocabularies whose parents are populated: `["BACT","Bacteria",null]`,
`["FIRM","Firmicutes","BACT"]`, `["bant","Bacillus anthracis","FIRM"]`. Three
rows on each site have a null parent, and on both sites the indent map's depth
equals the parent's depth plus one for all 903 entries, so the parent column and
the site's own indent convention agree exactly.

A client that requires the third element to be null cannot read a nested
vocabulary at all: it fails the whole search document, not the one parameter, so
the search reads as one the site does not have.
