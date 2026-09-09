---
type: Rules
title: Site-model parameter rules
description: The parameters WDK executes but ApiCommonModel defines - the phyletic profile pattern's LIKE grammar, why a wrong pattern is never refused and returns whatever the ortholog-less branch yields, why this parameter's own published default is an expression from another site, and why a search that offers the same criterion twice unions the two halves.
tags: [wdk-alignment, rules, parameters, site-model, apicommonmodel, phyletic-profile, radio-params]
generated: { by: claude-code/opus-5, at: 2026-08-14T00:00:00Z }
verified: { by: claude-code/fable-5, at: 2026-08-17T00:00:00Z }
status: stable
---

# WDK-SITE - parameters WDK runs and does not define

A parameter declared in
[ApiCommonModel](https://github.com/VEuPathDB/ApiCommonModel/tree/301b2be012af713411e9b0e216ed93c51d04c239/)
has a grammar WDK cannot see. WDK validates it as a string, of a length, against a regex if
one is declared, and stops
([WDK-PARAM-010](parameters-and-vocabularies.md)). Everything about what the string *means*
lives in the site model, and every rule in this file is sourced there rather than in the
WDK repository. That is why this is a namespace of its own and not more `WDK-PARAM`
entries: the falsifier is a different repository.

The explainer these rules come from is
[site-model-parameters](../model/site-model-parameters.md).

### WDK-SITE-001 - `profile_pattern` is a SQL `LIKE` pattern over a colon-joined species census, not a delimited list

- class: CONTRACT
- upstream: https://github.com/VEuPathDB/ApiCommonModel/blob/301b2be012af713411e9b0e216ed93c51d04c239/Model/lib/wdk/model/questions/queries/geneQueries.xml#L2239-L2266
- anchor: src/veupathdb/wdk/strategy_api/base.py:_expand_profile_pattern_groups
- status: UNENFORCED
- reason: enforced in the consuming application, at apps/web/src/features/strategy/editor/widgets/PhyleticProfileParam.test.tsx::encodeProfilePattern::wraps and separates the tokens with the LIKE wildcard

`GenesByOrthologPattern`'s query uses the parameter twice, and the second use is the
search:

```sql
                AND $$profile_pattern$$ not like '%:Y%'
...
              WHERE gpp.profile_string LIKE $$profile_pattern$$
```

`apidb.PhylogeneticProfile.profile_string` is a census over every species in the OrthoMCL
clade tree. **The `%` characters are the `LIKE` wildcard, not a separator**, and the tokens
between them are `code:Y` for present and `code:N` for absent. There is no token for the
third state of the user model - "no constraints" is a species left out of the pattern, and
the wildcards step over it.

The reference client builds exactly that string, and it is the only place in
web-monorepo that writes this parameter
([GenesByOrthologPattern.tsx#L154-L178](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/sites/genomics-site/webapp/wdkCustomization/js/client/components/questions/GenesByOrthologPattern.tsx#L154-L178)):
`` `%${profilePatternLeaves.join('%')}%` ``, with the empty selection written as the single
character `%` rather than as the empty string.

Measured live on plasmodb.org on 2026-08-14, holding `organism` at *P. falciparum* 3D7,
the census structure is directly visible. `auva` is the immediate successor of `atum` in
code order among the vocabulary's 818 species codes, and `_` is the single-character `LIKE`
wildcard, so:

| Probe | `totalCount` | Reads as |
|---|---|---|
| `%atum:Y_auva%` | 474 | exactly one character between the two |
| `%atum:Y__auva%`, `%atum:Y___auva%` | 0 | not two, not three |
| `%atum:Y:auva%` | 474 | that character is `:` |
| `%atum:Y.auva%`, `%atum:Y*auva%`, `%atum:Y+auva%`, and the same with a tab and a newline | 0 | none of those |
| `%atum:Y %`, `%atum:Y,%`, `%atum:Y|%`, `%atum:Y;%`, `%atum:Y-%` | 0 | nor space, comma, pipe, semicolon or hyphen anywhere after a token |

The census is therefore a single colon-joined run of alternating codes and states.

A client never needs the separator, because `%` covers it. It is recorded because knowing
the value is a substring match over a census is what makes every other rule here follow,
and a reader who thinks `%` is a delimiter will reinvent all of them.

**I could not find any upstream document that states this grammar in prose, and this rule
is therefore a reconstruction** - from the SQL, from the client's template, and from live
measurement, in that order. What was searched: the parameter's `<help>`, the search's
`<description>`
([geneQuestions.xml#L2574-L2588](https://github.com/VEuPathDB/ApiCommonModel/blob/301b2be012af713411e9b0e216ed93c51d04c239/Model/lib/wdk/model/questions/geneQuestions.xml#L2574-L2588),
which describes the three states and the radio buttons and says nothing about the string),
every comment in the surrounding XML, and the three markdown files ApiCommonModel carries
at this sha, none of which is about this search. The genomics-site component contains no
comments at all. A prose statement may exist somewhere outside the four pinned
repositories; none was found in them.

### WDK-SITE-002 - A wrong `profile_pattern` is never refused; it silently returns whatever the ortholog-less branch yields for that organism

- class: SILENT
- upstream: https://github.com/VEuPathDB/ApiCommonModel/blob/301b2be012af713411e9b0e216ed93c51d04c239/Model/lib/wdk/model/questions/queries/geneQueries.xml#L2239-L2266
- anchor: src/veupathdb/domain/parameters/phyletic.py:encode_profile_pattern
- status: UNENFORCED
- reason: enforced in the consuming application, at apps/web/src/features/strategy/editor/widgets/PhyleticProfileParam.test.tsx::an included species always reaches the matching branch::writes a :Y token for an inclusion
There is nothing to parse. The parameter is a `stringParam` with `number="false"`, no
`regex`, and `length="4000"`, so
[`StringParam.validateValue`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/param/StringParam.java#L171-L202)
has exactly one check to apply to it - the length cap - and any string under 4000
characters passes. The value then goes to `LIKE`, which does not fail on a pattern that
matches nothing.

PathFinder refuses three shapes before the value leaves the client, all of them read in
`domain/parameters/phyletic.py`. `read_census` reads the value as a run of
`code:Y` / `code:N` tokens and returns no states for any other shape, and
`census_states` answers that with a 422 - which is what prose, OrthoMCL
syntax and the published default get. A code that states two states is a 422 of its own,
naming the repeated code, because one species has one state in the census; both paths to
the wire raise it, the expansion in `base.py:_expand_profile_pattern_groups` and
`sort_profile_pattern` under `_normalize_parameters`. A code the phyletic tree does not
carry is a second 422, raised by `validate_phyletic_codes`. All three run at
`set_criterion` time as well, from
`veupathdb-mcp: src/veupathdb_mcp/catalog/param_validation.py`, because the
pattern the model states is otherwise accepted by the pre-flight and refused one tool call
later. Guarded by
`tests/unit/wdk/test_strategy_api_base.py`,
`veupathdb-mcp/tests/unit/catalog/test_param_validation_phyletic.py`
and `apps/api/src/pathfinder/tests/unit/test_phyletic_conformance.py`.

That narrows the ways in rather than closing them. A pattern built from real codes in the
right order and the wrong states is well formed, reaches WDK, and comes back as a count;
the bare `%` is legal and matches every census. What changed the odds is upstream of the
wire rather than at it: the pattern is no longer written by hand but derived from the two
species lists
([WDK-SITE-006](#wdk-site-006---included_species-and-excluded_species-never-reach-the-query-and-are-the-only-state-the-reference-client-reads-back)).

**But the answer is not therefore empty, and this is the part that makes the rule
`SILENT` rather than merely annoying.** The query is a `UNION` of two branches, and the
first one does not use `LIKE` at all - it inspects the pattern *string* and, if the string
contains no `:Y`, returns every ortholog-less protein-coding gene for the selected
organism:

```sql
-- branch 1, lines 2243-2251
              WHERE group_id IS NULL
                AND (gene_type = 'protein coding' OR gene_type = 'protein coding gene')
                AND $$profile_pattern$$ not like '%:Y%'
             UNION
-- branch 2, lines 2253-2261
              WHERE gpp.profile_string LIKE $$profile_pattern$$
```

That guard is correct for its intended purpose: a pattern of pure exclusions means "absent
from these species, *or* not in any ortholog group". It is also indiscriminate. It cannot
distinguish a deliberate all-`:N` pattern from a typo, from OrthoMCL syntax, from prose.

So the failure mode is not "returns zero". It is:

**A wrong pattern containing no `:Y` returns exactly the ortholog-less protein-coding gene
set for the chosen organism, under a name that claims to be a phyletic profile result.**

Live on plasmodb.org and toxodb.org on 2026-08-14, with `organism` fixed at *P.
falciparum* 3D7 and *T. gondii* ME49. The `:Y` column is what decides which branches run:

| `profile_pattern` | has `:Y` | branches | plasmodb.org | toxodb.org |
|---|---|---|---|---|
| `%hsap:Y%` | yes | 2 only | 200, **2042** | 200, **2595** |
| `%zzzz:Y%` - unknown code | yes | 2 only | 200, **0** | 200, **0** |
| `%MAMM:Y%` - clade code | yes | 2 only | 200, **0** | 200, **0** |
| `hsap=1T` | **no** | **1 only** | 200, **0** | 200, **0** |
| `hsap>=1T` | **no** | **1 only** | 200, **0** | 200, **0** |
| `hsap=0T` | **no** | **1 only** | 200, **0** | 200, **0** |
| `not a pattern at all` | **no** | **1 only** | 200, **0** | 200, **0** |
| `""` | - | none | **422** `Cannot be empty.` | not re-run |

The only refusal is the empty string, and it is refused for a reason that has nothing to do
with the grammar: `allowEmptyValue` is false, so WDK's own emptiness check fires before the
value reaches the query.

**The zeros in the four `:Y`-free rows are a property of these organisms, not of the
pattern.** Each of those four ran branch 1 and branch 1 came back empty, which means these
organisms have no ortholog-less protein-coding genes - not that the pattern was rejected.
The two `:Y`-bearing zeros are different and are intrinsic: branch 1 was excluded, branch 2
genuinely matched nothing.

**I could not produce a non-zero branch 1, and that is a limit of the measurement rather
than a refutation.** `hsap=1T` isolates branch 1 exactly - no `:Y`, and no census can equal
those seven characters - and it returned 0 on **eleven organisms across both sites**: *P.
falciparum* 3D7, *P. vivax* P01, *P. berghei* ANKA, *P. adleri* G01, *Haemoproteus
tartakovskyi* SISKIN1, *Hepatocystis* sp. ex *Piliocolobus tephrosceles* 2019, *T. gondii*
ME49, *T. gondii* ARI, *Cyclospora cayetanensis* NF1_C8, *Eimeria acervulina* Houghton,
*Besnoitia besnoiti* Bb-Ger1. Eleven organisms on two of the twelve sites is not evidence
that the set is empty everywhere, and the SQL is explicit that it need not be.

**Read the rule as a ceiling, not as an observation.** A converter that reasons "wrong
syntax gives zero, and zero is visible" is relying on a data coincidence that the model
does not promise. A plausible non-zero count from a meaningless pattern is the worst answer
this search can give, and nothing in the query prevents it.

The compare against OrthoMCL is worth carrying, because it shows this is a choice rather
than a platform limit. `GroupsByPhyleticPattern.phyletic_expression` on orthomcl.org
*parses* its input, and on 2026-08-14 it answered **HTTP 500 `Internal Error`** to both
`%hsap:Y%` and `not a pattern at all`. A parsed grammar fails loudly. A `LIKE` grammar
cannot.

### WDK-SITE-003 - `profile_pattern`'s published `initialDisplayValue` is an expression from another site's grammar, and it returns zero

- class: SILENT
- upstream: https://github.com/VEuPathDB/ApiCommonModel/blob/301b2be012af713411e9b0e216ed93c51d04c239/Model/lib/wdk/model/questions/params/geneParams.xml#L4873-L4879
- anchor: src/veupathdb/domain/parameters/specs.py:fill_hidden_required_defaults
- status: ENFORCED by tests/unit/domain/parameters/test_specs.py::TestTheFillIsNamed::test_a_hidden_default_is_reported
The declaration is six lines and it contains the same string twice:

```xml
    <stringParam name="profile_pattern"
                 visible="false" length="4000"
                 prompt="Profile Pattern" number="false">
      <help>Example: 'hsap=1T'</help>
      <suggest default="hsap=1T"/>
    </stringParam>
```

WDK republishes the `suggest default` as `initialDisplayValue`, so on both sites
`GET /record-types/transcript/searches/GenesByOrthologPattern` reports
`initialDisplayValue: "hsap=1T"` with `isVisible: false` and `allowEmptyValue: false` -
a hidden, required parameter whose only published value returns nothing
([WDK-SITE-002](#wdk-site-002---an-unparseable-profile_pattern-is-a-200-with-zero-rows-not-an-error)).

**`hsap=1T` is not a broken pattern and not an older syntax. It is a correct expression in
a different parameter's grammar.** OrthoMCL's
`GroupsByPhyleticPattern.phyletic_expression` uses `code`/operator/count with an optional
`T`, joined by ` AND `. The ortho-site client builds exactly those shapes
([phyleticPattern.ts#L186-L193](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/sites/ortho-site/webapp/wdkCustomization/js/client/utils/phyleticPattern.ts#L186-L193)):
`${node.abbrev}=${node.speciesCount}T`, `${node.abbrev}>=1T`, `${node.abbrev}=0T`.
ApiCommonModel's own tooling calls that OrthoMCL endpoint and url-escapes `=`, `>`, `<` and
`:` on the way
([phyleticPatternWebService.pl#L82-L84](https://github.com/VEuPathDB/ApiCommonModel/blob/301b2be012af713411e9b0e216ed93c51d04c239/Model/bin/phyleticPatternWebService.pl#L82-L84),
[#L97-L111](https://github.com/VEuPathDB/ApiCommonModel/blob/301b2be012af713411e9b0e216ed93c51d04c239/Model/bin/phyleticPatternWebService.pl#L97-L111)).

Live on orthomcl.org on 2026-08-14, `phyletic_expression` publishes
`initialDisplayValue: "EUKA>=5T AND hsap>=10"`, and the same search answers **200 with
9691 groups** for `hsap=1T`. The string is valid there and worthless here.

Nothing in the pinned repositories explains how it arrived in this parameter. That is a
statement about where it was looked for - `geneParams.xml`, `geneQueries.xml`,
`geneQuestions.xml`, `Model/bin` in ApiCommonModel, and both site clients in web-monorepo -
and not a claim that no explanation exists.

The general lesson is
[WDK-PARAM-010](parameters-and-vocabularies.md): `initialDisplayValue` is what the spec
holds, the spec was filled from an unvalidated model default, and nothing anywhere promises
a default returns rows. The anchor is PathFinder's `fill_hidden_required_defaults`, which
does the reasonable thing for a hidden required parameter and, on this one parameter,
chooses the science.

### WDK-SITE-004 - The tokens of a `profile_pattern` must be in ascending code order or the pattern matches nothing

- class: SILENT
- upstream: https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/sites/genomics-site/webapp/wdkCustomization/js/client/components/questions/GenesByOrthologPattern.tsx#L154-L178
- anchor: src/veupathdb/domain/parameters/phyletic.py:sort_profile_pattern
- status: UNENFORCED
- reason: enforced in the consuming application, at apps/web/src/features/strategy/editor/widgets/PhyleticProfileParam.test.tsx::encodeProfilePattern::sorts the tokens into ascending code order

`%A%B%` under `LIKE` means "A, then later B". The stored census lists codes in ascending
order of the code, so two correct tokens in the wrong relative order describe a census that
cannot exist.

Measured on plasmodb.org on 2026-08-14, three pairs, each sent both ways:

| Pattern | `totalCount` |
|---|---|
| `%atum:Y%bant:Y%` | 387 |
| `%bant:Y%atum:Y%` | **0** |
| `%atum:Y%hsap:Y%` | 399 |
| `%hsap:Y%atum:Y%` | **0** |
| `%wsuc:Y%yepe:Y%` | 310 |
| `%yepe:Y%wsuc:Y%` | **0** |

The first pair repeats on toxodb.org: 473 and 0.

**All three pairs were chosen because tree order and code order disagree on them.**
`phyletic_term_map` is emitted as a depth-first walk of the clade tree, in which `bant`
precedes `atum` and `yepe` precedes `wsuc`. Sorting by that order produces a pattern that
matches nothing. The census is in code order, not in vocabulary order, and a converter that
preserves the order the vocabulary handed it is wrong on every pair like these.

The reference client gets this right by construction: `.sort()` with no comparator, applied
to the bare codes before the `:Y`/`:N` suffix is appended, in the cited block.

**This rule has no upstream that can refute it, and that has to be said in the rule rather
than only in the explainer.** `apidb.PhylogeneticProfile.profile_string` is loaded by code
outside the four pinned repositories; nothing in ApiCommonModel, WDK, web-monorepo or
ApiCommonWebsite states what order its codes are in. The pinned citation above is the
client's `.sort()`, which is evidence of intent and not of the stored data. The ordering
requirement itself rests entirely on the six measurements in the table, and it is
falsifiable only by re-running them. If the table is ever rebuilt in a different order this
rule becomes false and no gate can notice. Re-run: the six patterns above against
`GenesByOrthologPattern` with `organism` at *P. falciparum* 3D7, expecting non-zero for the
ascending form of each pair and 0 for the reverse.

PathFinder sorts in one place. `domain/parameters/phyletic.py:encode_profile_pattern` emits
the tokens sorted, so every pattern the authoring path produces is in census order by
construction, and `sort_profile_pattern` beside it re-orders only a pattern that reaches
the wire when the clade tree cannot be read. Re-measured on plasmodb.org on 2026-09-04:
`%hsap:Y%atum:Y%` pushed through `create_step` reads back off the stored step as
`%atum:Y%hsap:Y%`. Both name the stored census as the reason, which is
worth keeping in the code, because the plausible wrong reason - that OrthoMCL requires
alphabetical entries - points a reader at a different site running a different grammar that
requires no such thing
([WDK-SITE-003](#wdk-site-003---profile_patterns-published-initialdisplayvalue-is-an-expression-from-another-sites-grammar-and-it-returns-zero)).

### WDK-SITE-005 - Only lowercase leaf species codes appear in the census; a clade code is case-sensitively absent

- class: SILENT
- upstream: https://github.com/VEuPathDB/ApiCommonModel/blob/301b2be012af713411e9b0e216ed93c51d04c239/Model/lib/wdk/model/questions/params/geneParams.xml#L8247-L8281
- anchor: src/veupathdb/domain/parameters/phyletic.py:leaf_states
- status: ENFORCED by tests/unit/domain/parameters/test_phyletic.py::TestLeafStates::test_a_clade_becomes_its_leaves

The vocabulary is `phyletic_term_map`, whose backing query walks `apidb.orthomclclade` and
returns `three_letter_abbrev` as the term. It contains both kinds of node. Counted with
`jq` over the live response on both sites on 2026-08-14: **865** entries, no duplicates,
**818** whose term is all-lowercase and **47** all-uppercase, none mixed. Every term is
four characters except the uppercase root `ALL`, which is three - so the column name
`three_letter_abbrev` is wrong about its own contents for 864 of 865 rows. The companion
`phyletic_indent_map` holds 864 on both sites, one fewer.

Only the species codes appear in the census. `%MAMM:Y%` returns **0** on plasmodb.org and
on toxodb.org, while `%hsap:Y%` returns 2042 and 2595. `MAMM` is a genuine term of the
parameter's own vocabulary and it matches nothing, because the match is a substring test
rather than a lookup.

The same reason makes it case-sensitive: `%HSAP:Y%` returns 0 where `%hsap:Y%` returns
2042.

The expansion has one implementation, and both paths call it. `PhyleticTree.leaf_states`
pushes each selection down to the species the census holds: the authoring path reaches it
through `derive_binding`, and the wire guard through `_expand_profile_pattern_groups`. The
code check is `validate_phyletic_codes`, called before the expansion and again from the
pre-flight, so a code the tree does not carry is a 422 rather than a token that matches
nothing (`tests/unit/wdk/test_strategy_api_base.py`,
`veupathdb-mcp/tests/unit/catalog/test_param_validation_phyletic.py`). The editor widget
keeps its own copy of the same rule, tested at
`apps/web/src/features/strategy/editor/widgets/PhyleticProfileParam.test.tsx`.

The other half - that the codes written are the ones the vocabulary carries, whatever case
the proposal used - is asserted rather than left to construction:
`tests/unit/domain/parameters/test_phyletic.py::TestResolvingTerms::test_labels_are_case_insensitive_and_lists_are_read`
pins `resolve_terms(["mammalia", "PFAL"]).codes` to `["MAMM", "pfal"]`, so a lowercase clade
name comes back uppercase and an uppercase species name comes back lowercase, each in the
case the census requires.

So a term being in `phyletic_term_map` is not evidence that it can be used, and this is the
one rule here that a naive "validate against the vocabulary" step gets exactly backwards -
it would accept `MAMM` and produce a silent zero. Expand a clade to its leaves first. The
reference client does it structurally, filtering on
`nodeMap[term].children.length === 0`; leaf-versus-clade is not a field on the vocabulary
and has to be read off `phyletic_indent_map` by comparing a code's depth with the next
code's.

An unknown code behaves identically to a clade code: `%zzzz:Y%` is 200 with 0 on both
sites. Nothing distinguishes "you used a group name", "you used a code that does not
exist", and "no gene matches". Both of those zeros are intrinsic rather than
organism-dependent - each pattern carries a `:Y`, so the ortholog-less branch of
[WDK-SITE-002](#wdk-site-002---a-wrong-profile_pattern-is-never-refused-it-silently-returns-whatever-the-ortholog-less-branch-yields-for-that-organism)
is excluded and only the `LIKE` branch can contribute.

**Like [WDK-SITE-004](#wdk-site-004---the-tokens-of-a-profile_pattern-must-be-in-ascending-code-order-or-the-pattern-matches-nothing), the census half of this rule rests on measurement alone.** The pinned
citation above is the vocabulary query, which proves what terms exist and says nothing
about which of them the stored string contains. That a clade code is absent from the census
is a live finding on two sites and nothing in the four pinned repositories can confirm or
refute it. Re-run: `%MAMM:Y%` against `GenesByOrthologPattern`, expecting 0 where
`%hsap:Y%` is non-zero.

### WDK-SITE-006 - `included_species` and `excluded_species` never reach the query, and are the only state the reference client reads back

- class: CONTRACT
- upstream: https://github.com/VEuPathDB/ApiCommonModel/blob/301b2be012af713411e9b0e216ed93c51d04c239/Model/lib/wdk/model/questions/params/geneParams.xml#L4884-L4894
- anchor: src/veupathdb/domain/parameters/phyletic.py:species_lists
- status: ENFORCED by tests/unit/domain/parameters/test_phyletic.py::TestTheLists::test_highest_nodes_comma_joined

Both parameters declare their own irrelevance - "List of included species (for
documentation only)" - and the SQL bears it out: the query's only parameter substitutions
are `$$profile_pattern$$` and `$$organism$$`.

That reading is correct and incomplete. In the reference client these two are the
**primary** state and `profile_pattern` is derived from them. The genomics-site form seeds
its tri-state map from `included_species` and `excluded_species`
([GenesByOrthologPattern.tsx#L132-L142](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/sites/genomics-site/webapp/wdkCustomization/js/client/components/questions/GenesByOrthologPattern.tsx#L132-L142)),
decoding each with `getSpeciesTerms`
([#L90-L101](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/sites/genomics-site/webapp/wdkCustomization/js/client/components/questions/GenesByOrthologPattern.tsx#L90-L101)):
the literal `n/a` is the empty set, the literal `All Organisms` is the root term `ALL`, and
anything else splits on commas and trims. The encoder is symmetric and joins with `", "`
([#L478-L484](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/sites/genomics-site/webapp/wdkCustomization/js/client/components/questions/GenesByOrthologPattern.tsx#L478-L484)),
and stores the **highest** node in each state rather than the leaves
([#L510-L533](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/sites/genomics-site/webapp/wdkCustomization/js/client/components/questions/GenesByOrthologPattern.tsx#L510-L533)),
so an included clade is one term here and many tokens in the pattern.

**The client never reads `profile_pattern` back.** In that file the constant
`PROFILE_PATTERN_PARAM_NAME` appears exactly twice: at its declaration and inside the
write. There is no parser, and on form load the effect at `#L154-L178` overwrites the
parameter with a value regenerated from the two lists.

So the consequence for a client is the opposite of what "for documentation only" suggests.
Write the pattern and not the lists, and the step runs correctly and reopens empty. Write
the lists and not the pattern, and the step reopens correctly and runs on whatever pattern
was there before. Both must be written together, and they are at different granularities on
purpose.

PathFinder writes all three together, and the two lists are the input rather than a
by-product. The parameter sheet gives `included_species` and `excluded_species` the clade
tree as their vocabulary, so the model proposes species and clades by code or by label;
`veupathdb-mcp: src/veupathdb_mcp/catalog/param_phyletic.py:derive_phyletic_overrides`
resolves both proposals
against the tree and returns the two canonical lists beside the pattern derived from them,
and `set_criterion` binds all three. `species_lists` keeps the granularity the reference
client stores - a clade stays one term in the list while its leaves are the tokens in the
pattern - and writes `n/a` for an empty list. Measured on plasmodb.org on 2026-08-17 with
`organism` at *P. falciparum* 3D7, the binding `%hsap:N%pfal:Y%` / `pfal` / `hsap` returns
**3,347** genes, where the published default returns 0. Recorded as
the two lists are the proposal (`pathfinder: docs/knowledge/decisions/phyletic-lists-are-the-proposal.md`).

The editor reads them back the same way. `phyleticProfileLogic.ts:seedTriStates` seeds the
widget's tri-state map from the two lists, resolved against the same clade tree by
`resolveTerms`, and reads `profile_pattern` only when neither list states anything. Seeding
from the pattern instead reopens a step at leaf granularity, so the first click rewrites a
stored clade as its species and the record of the request degrades while the pattern stays
correct. A code both lists claim, or a term the tree does not carry (the reference client's
literal `All Organisms` is one), reopens unconstrained and is named in a notice above the
tree: the widget holds one state per code and has no way to refuse a step that already
exists, and reading the pattern in its place would substitute leaf granularity for the
stated term.

The root is the one selection this path refuses. The reference client decodes `ALL` and the
literal `All Organisms` as the root term, and a pattern over all 818 species exceeds the
parameter's 4000-character cap, so `PhyleticTree` drops the root and a proposal naming it
comes back as an unknown term rather than as a binding.

One further trap sits underneath this, in generic WDK plumbing rather than in the site
model:
[`initialParamDataFromStep`](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/StoreModules/QuestionStoreModule.ts#L1094-L1105)
drops from the seed any parameter named in `validation.errors.byKey`. A step whose
`included_species` is invalid therefore reopens with that parameter's default rather than
its stored value, and the pattern is then regenerated from the reduced set.

### WDK-SITE-007 - A `radio-params` pair is two required parameters ORed by one query, so filling both widens the search

- class: SILENT
- upstream: https://github.com/VEuPathDB/ApiCommonModel/blob/53de242dfce4e2be81ad28ad8a608c87af3e0b7c/Model/lib/wdk/model/questions/queries/geneQueries.xml#L1807-L1814
- anchor: src/veupathdb/wdk/wdk_models.py:properties
- status: UNENFORCED
- reason: enforced in the consuming application, at apps/api/src/pathfinder/tests/unit/ai/tools/test_frame_proposals.py::test_a_refused_proposal_names_what_is_wrong

Some searches offer the same criterion twice: once as a vocabulary the user picks
from, once as free text with wildcards. ApiCommonModel declares the pair in a
`radio-params` property list, always with
[the same comment and the typeahead first](https://github.com/VEuPathDB/ApiCommonModel/blob/28af02f5d613ab150f39350e25f462f39d75650c/Model/lib/wdk/model/questions/geneQuestions.xml#L2303-L2307),
and the property is published on the wire: live on plasmodb.org on 2026-08-17,
`GET /record-types/transcript/searches/GenesByGoTerm` carries
`properties["radio-params"] = ["go_typeahead", "go_term"]`. Four transcript
searches declare one at this sha - `GenesByGoTerm`, `GenesByInterproDomain`,
`GenesByEcNumber` and `GenesByMetabolicPathway` - and other record types declare
more. The citations in this rule are pinned to the current head of each file
rather than to the sha the rules above use, because the line ranges moved
between the two.

**The two halves are `OR`, not `AND`.** The `GenesByGoTerm` SQL matches
`go_id IN ($$go_typeahead$$)` **or** the `go_term` wildcard, and
[`GenesByInterproDomain`](https://github.com/VEuPathDB/ApiCommonModel/blob/53de242dfce4e2be81ad28ad8a608c87af3e0b7c/Model/lib/wdk/model/questions/queries/geneQueries.xml#L3049-L3054)
and
[`GenesByEcNumber`](https://github.com/VEuPathDB/ApiCommonModel/blob/53de242dfce4e2be81ad28ad8a608c87af3e0b7c/Model/lib/wdk/model/questions/queries/geneQueries.xml#L879-L885)
are built the same way. So filling both does not narrow the search, which is the
intuition a form suggests. It returns the union, and the extra records are
whatever the free-text half happened to match.

**There is no off position.** Both halves are `allowEmptyValue: false` on all
three searches, live on plasmodb.org on 2026-08-17, and two of the published
defaults are refused by the search that published them: `go_typeahead: "[]"` and
`domain_typeahead: "[]"` both come back `Cannot be empty.`, and so does
`domain_accession`, whose declared default is
[the empty string](https://github.com/VEuPathDB/ApiCommonModel/blob/28af02f5d613ab150f39350e25f462f39d75650c/Model/lib/wdk/model/questions/params/geneParams.xml#L5593-L5595).
The only way to switch a half off is a value that matches nothing.
[`go_term`](https://github.com/VEuPathDB/ApiCommonModel/blob/28af02f5d613ab150f39350e25f462f39d75650c/Model/lib/wdk/model/questions/params/geneParams.xml#L2085-L2089)
and
[`ec_wildcard`](https://github.com/VEuPathDB/ApiCommonModel/blob/28af02f5d613ab150f39350e25f462f39d75650c/Model/lib/wdk/model/questions/params/geneParams.xml#L966-L969)
declare `N/A` for that purpose and the GO query tests for it explicitly; nothing
declares one for `domain_accession`, where `N/A` works only because it matches no
accession, family or description.

Measured on plasmodb.org on 2026-08-17, organism `Plasmodium falciparum 3D7`,
counts as `totalCount / displayTotalCount`:

| search | values | result |
|---|---|---|
| `GenesByGoTerm` | `go_typeahead: ["GO:0004672"]`, `go_term: N/A` | 106 / 105 |
| `GenesByGoTerm` | the same plus `go_term: *kinase*` | **193 / 192** |
| `GenesByInterproDomain` | `domain_typeahead: ["PF00069 : Pkinase"]`, `domain_accession: N/A` | 82 / 81 |
| `GenesByInterproDomain` | the same plus `domain_accession: *kinase*` | **145 / 144** |
| `GenesByEcNumber` | `ec_number_pattern: 2.7.11.1` (its published default), `ec_wildcard: N/A` | 136 / 133 |
| `GenesByEcNumber` | the same plus `ec_wildcard: *protease*` | **145 / 141** |

The last pair is the sharpest form of the hazard. `ec_number_pattern` cannot be
empty and its `initialDisplayValue` is a real EC number, so a search that asks
only for proteases still carries 133 protein kinases, and no field of the
response says so.

**The vocabulary half is the authoritative one.** It is the half listed first in
`radio-params`, the half whose values are checked against a vocabulary, and on
`GenesByEcNumber` the half that cannot be silenced at all, because its own
default is a real EC number. So the vocabulary half carries the criterion and
the free text is switched off, never the other way round.

This is `SILENT` because every combination above returns 200 with a plausible
count. `set_criterion` reads `radio-params` off the search definition and binds
`N/A` into the free-text half of every declared pair, so a half nobody wrote
into states nothing rather than opening a slot; a proposal that writes the
criterion into the free text comes back as a retry naming the vocabulary entries
nearest to it, and a wildcard is answered by a vocabulary read rather than by a
typed value.

One capability is given up with it, knowingly: `domain_accession` matches an
InterPro family name or a description as well as an accession, so a wildcard over
descriptions - every domain whose description mentions a word - has no equivalent
in the typeahead vocabulary and is no longer expressible in FRAME. That is the
accepted cost of a criterion that cannot silently gain 63 records from a half
nobody read.
