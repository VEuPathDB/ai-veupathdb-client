---
type: Reference
title: Site-model parameters, and the phyletic profile pattern
description: What a site-model parameter is, why ApiCommonModel rather than WDK is its authority, the full grammar of profile_pattern as a SQL LIKE pattern, and what the reference client actually reads back from a saved step.
tags: [wdk-alignment, parameters, site-model, apicommonmodel, phyletic-profile, model]
generated: { by: claude-code/opus-5, at: 2026-08-14T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-17T00:00:00Z }
status: stable
---

Every permalink below is pinned to the sha recorded in [sources.md](../sources.md).

# A parameter WDK executes but does not define

WDK ships the parameter *system*: eleven types, the validation levels, the stable-value
encodings, the fill strategy. It ships almost no parameters. A named parameter such as
`organism` or `profile_pattern` is declared in XML in
[ApiCommonModel](https://github.com/VEuPathDB/ApiCommonModel/tree/301b2be012af713411e9b0e216ed93c51d04c239/),
consumed by a SQL query declared in the same repository, and executed by WDK without WDK
knowing anything about what the value means.

That split decides where to look when a value is accepted and produces the wrong answer.
WDK can tell you that a `string` parameter is a string, is required, and is under 4000
characters. It cannot tell you that the string is a SQL `LIKE` pattern, that the tokens
inside it must be in a particular order, or that one particular string returns nothing.
None of that is knowable from the WDK repository, and reading WDK harder will not produce
it. It is the same blind spot that forced [ApiCommonWebsite](https://github.com/VEuPathDB/ApiCommonWebsite/tree/830bb57fe07fc2e4dd37b6ea2e3baae0eaee5bee/)
into [sources.md](../sources.md) for the enrichment column names: a plugin's output shape
and a parameter's grammar are both site model, and WDK is the wrong oracle for both.

**So a site-model parameter has three authorities, in this order.** ApiCommonModel says
what the value is fed to. The reference client in
[web-monorepo](https://github.com/VEuPathDB/web-monorepo/tree/63d1705463d553c0ac19ee577c1b09666597b903/)
says what a working client actually sends. The deployment says what happens, and it is the
only one that can tell you a well-formed value returns zero rows.

The rules drawn from this document are [WDK-SITE-001..006](../rules/site-model-params.md).

# `GenesByOrthologPattern` and its six parameters

The search is declared at
[geneQuestions.xml#L2549-L2596](https://github.com/VEuPathDB/ApiCommonModel/blob/301b2be012af713411e9b0e216ed93c51d04c239/Model/lib/wdk/model/questions/geneQuestions.xml#L2549-L2596),
displayed as "Orthology Phylogenetic Profile", and bound to the query
`GeneId.GenesByOrthologPattern`. Its own description states the user model in one
sentence: the pattern is "a specification, for each species, of 'include', 'exclude', or
'no constraints'"
([geneQuestions.xml#L2574-L2588](https://github.com/VEuPathDB/ApiCommonModel/blob/301b2be012af713411e9b0e216ed93c51d04c239/Model/lib/wdk/model/questions/geneQuestions.xml#L2574-L2588)).
Three states, per species. Nothing there says how those three states become a string.

Live on plasmodb.org and toxodb.org on 2026-08-14, `GET
/record-types/transcript/searches/GenesByOrthologPattern` reports six parameters, and
their visibility is the whole story:

| Parameter | `type` | `isVisible` | `allowEmptyValue` | `initialDisplayValue` |
|---|---|---|---|---|
| `profile_pattern` | `string` | **false** | **false** | `hsap=1T` |
| `included_species` | `string` | true | true | `""` |
| `excluded_species` | `string` | true | true | `""` |
| `phyletic_indent_map` | `multi-pick-vocabulary`, `checkBox` | false | true | `[]` |
| `phyletic_term_map` | `multi-pick-vocabulary`, `checkBox` | false | true | `[]` |
| `organism` | `multi-pick-vocabulary`, `treeBox` | true | false | `[]` |

The parameter that carries the entire scientific meaning of the search is the one the
user cannot see and cannot leave empty. Both sites agree on every column.

`phyletic_indent_map` and `phyletic_term_map` are not query inputs at all. The model says
so in its own words, in a comment immediately after the query
([geneQueries.xml#L2268-L2276](https://github.com/VEuPathDB/ApiCommonModel/blob/301b2be012af713411e9b0e216ed93c51d04c239/Model/lib/wdk/model/questions/queries/geneQueries.xml#L2268-L2276)):
they "are not used by the query. They are for display purposes only." They exist so the
client can draw the species tree - `phyletic_term_map` maps a code to a species or clade
name, `phyletic_indent_map` maps the same code to a depth.

# "Display purposes only" does not mean the metadata read may omit them

The contextual read `POST /record-types/transcript/searches/GenesByOrthologPattern`
answers `500 Internal Error` when the context carries a non-empty `organism` together
with `profile_pattern` and does **not** carry both maps. Measured on plasmodb.org on
2026-08-17, one organism (`Plasmodium falciparum 3D7`) throughout:

| `contextParamValues` | status |
|---|---|
| `organism` | 200 |
| `profile_pattern` | 200 |
| `organism` + `profile_pattern` | **500** |
| `organism` + `profile_pattern` + `phyletic_indent_map: "[]"` | **500** |
| `organism` + `profile_pattern` + `phyletic_term_map: "[]"` | **500** |
| `organism` + `profile_pattern` + both maps | 200, `validation: {level: SEMANTIC, isValid: true}` |
| `organism` + `included_species` + `excluded_species` | 200 |
| `organism: "[]"` + `profile_pattern` | 200 |

The default pattern `hsap=1T` fails the same way, so this is not about the pattern's
content. Both maps are needed; either alone still fails.

A client that omits them loses WDK's verdict on every phyletic binding: the read falls
back to the static `GET`, whose echoed values are the published defaults
([WDK-PARAM-008](../rules/parameters-and-vocabularies.md)). PathFinder therefore adds the
published `initialDisplayValue` of **every** hidden parameter that allows empty to the
context of a metadata read, by shape rather than by name
(`apps/api/src/pathfinder/services/catalog/search_context.py:context_for_metadata_read`).
A hidden parameter that forbids empty is a different case and is decided by
`fill_hidden_required_defaults`, because its value reaches the step's `searchConfig` and
chooses the science.

# The grammar: `profile_pattern` is a SQL `LIKE` pattern

This is the fact that makes every other behaviour follow, and it is visible in exactly one
place. The query is
[geneQueries.xml#L2239-L2266](https://github.com/VEuPathDB/ApiCommonModel/blob/301b2be012af713411e9b0e216ed93c51d04c239/Model/lib/wdk/model/questions/queries/geneQueries.xml#L2239-L2266),
and it uses the parameter twice:

```sql
                AND $$profile_pattern$$ not like '%:Y%'
...
              WHERE gpp.profile_string LIKE $$profile_pattern$$
```

The second line is the search. `apidb.PhylogeneticProfile.profile_string` is a stored
census over every species in the OrthoMCL clade tree, and the parameter is matched against
it with `LIKE`. So:

- **`%` is the SQL `LIKE` wildcard, not a separator.** `%pfal:Y%` means "the census
  contains the substring `pfal:Y` somewhere". A pattern with no `%` at all anchors both
  ends and matches only a census equal to the pattern.
- **A token is `code:Y` (present) or `code:N` (absent).** Measured on plasmodb.org on
  2026-08-14 with the `LIKE` single-character wildcard `_`: `%atum:Y_auva%` returns 474
  while `%atum:Y__auva%` and `%atum:Y___auva%` return 0, so exactly one character separates
  one token from the next, and `%atum:Y:auva%` returns 474 while every other separator
  probed returns 0. The census is a single colon-joined run of alternating codes and
  states. The full probe table is in
  [WDK-SITE-001](../rules/site-model-params.md).
- **There is no "no constraints" token.** The third state of the user model is expressed
  by leaving the species out of the pattern, which the wildcards then step over.
- **The empty selection is the single character `%`**, which matches every census. Live on
  plasmodb.org that is 5389 transcripts for *P. falciparum* 3D7.

The first line is not a detail. It is the whole reason a wrong pattern is dangerous rather
than merely useless, and it is what
[WDK-SITE-002](../rules/site-model-params.md) is about.

Branch 1 never touches `LIKE`. It inspects the pattern **string** with
`$$profile_pattern$$ not like '%:Y%'`, and when the string contains no `:Y` it adds every
protein-coding gene of the selected organism that is in **no** ortholog group. The intent
is sound - a pattern of pure exclusions should mean "absent from these species, *or* not in
any ortholog group" - but the test is on the pattern's spelling, so it cannot tell a
deliberate all-`:N` pattern from a typo, from OrthoMCL syntax, or from prose.

The consequence is that a meaningless pattern does not reliably produce an empty answer. It
produces branch 1's answer for that organism, which is empty on every organism measured
here and is not guaranteed empty anywhere. The rule states the measurement and its limit.

## Ordering is load-bearing

Because the match is `LIKE`, `%A%B%` means "A, then later B". Two tokens in the wrong
relative order can never match, however correct each token is on its own. Measured on
plasmodb.org on 2026-08-14, holding `organism` at *P. falciparum* 3D7:

| Pattern | `totalCount` |
|---|---|
| `%atum:Y%bant:Y%` | 387 |
| `%bant:Y%atum:Y%` | **0** |
| `%atum:Y%hsap:Y%` | 399 |
| `%hsap:Y%atum:Y%` | **0** |
| `%wsuc:Y%yepe:Y%` | 310 |
| `%yepe:Y%wsuc:Y%` | **0** |

Each pair is ordered one way and then the other, and only the ascending-code form matches
anything. `%atum:Y%bant:Y%` returns 473 on toxodb.org and `%bant:Y%atum:Y%` returns 0
there too.

All three pairs were chosen because tree order and code order **disagree** on them: in
`phyletic_term_map`'s own order `bant` precedes `atum` and `yepe` precedes `wsuc`, since
the vocabulary is a depth-first walk of the clade tree. The census is not in that order.
The stored string lists codes in ascending order of the code itself.

The reference client produces that order by construction. The genomics-site question form
sorts the leaf codes before joining
([GenesByOrthologPattern.tsx#L154-L178](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/sites/genomics-site/webapp/wdkCustomization/js/client/components/questions/GenesByOrthologPattern.tsx#L154-L178)):

```tsx
    const profilePatternLeaves = Object.keys(constraints)
      .filter(
        (term) =>
          nodeMap[term].children.length === 0 &&
          (constraints[term] === 'include' || constraints[term] === 'exclude')
      )
      .sort()
      .map((term) =>
        constraints[term] === 'include' ? `${term}:Y` : `${term}:N`
      );

    const newProfilePatternValue =
      profilePatternLeaves.length === 0
        ? '%'
        : `%${profilePatternLeaves.join('%')}%`;
```

`.sort()` with no comparator, on the bare codes, before the `:Y`/`:N` suffix is appended.
It is worth being precise about what that proves and what it does not. It proves the
client emits ascending code order. It does not prove that ascending order is *required* -
the measurements above prove that, and they are the reason the sort matters.

## Only leaf codes, and they are case-sensitive

The client's filter is `nodeMap[term].children.length === 0`: an interior clade node never
contributes a token. Selecting a clade propagates the state down to its leaves and the
leaves are what get written. Live confirmation that this is not merely a client
convention: `%MAMM:Y%` returns **0** on both plasmodb.org and toxodb.org, while
`%hsap:Y%` returns 2042 and 2595. A clade abbreviation is a real term of
`phyletic_term_map` and it appears nowhere in the census.

Case matters for the same reason - the comparison is `LIKE`, not a lookup. `%HSAP:Y%`
returns 0 on plasmodb.org where `%hsap:Y%` returns 2042.

The vocabulary itself is `phyletic_term_map`, whose backing query is
[PhyleticTermMap](https://github.com/VEuPathDB/ApiCommonModel/blob/301b2be012af713411e9b0e216ed93c51d04c239/Model/lib/wdk/model/questions/params/geneParams.xml#L8247-L8281):
a recursive walk of `apidb.orthomclclade`, term = `three_letter_abbrev`, display = the
clade or species name, excluding `BACI`. On both sites on 2026-08-14 it holds **865**
entries, of which **818** are lowercase four-character species codes and 47 are uppercase
clade abbreviations. Leaf-versus-clade is not a field on the vocabulary; it is read off
`phyletic_indent_map`, by comparing a code's depth with the next code's depth.

# `included_species` and `excluded_species` are not what they look like

Both are declared with the help text "List of included species (for documentation only)"
([geneParams.xml#L4884-L4894](https://github.com/VEuPathDB/ApiCommonModel/blob/301b2be012af713411e9b0e216ed93c51d04c239/Model/lib/wdk/model/questions/params/geneParams.xml#L4884-L4894)),
and the SQL genuinely never reads them - the query's only uses of a parameter are
`$$profile_pattern$$` and `$$organism$$`.

That makes them sound inert. In the reference client they are the opposite of inert: they
are the **only** state that survives a round trip.

The genomics-site form replaces the whole question form, registered by search name rather
than by parameter name
([pluginConfig.tsx#L233-L237](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/sites/genomics-site/webapp/wdkCustomization/js/client/pluginConfig.tsx#L233-L237)),
and it renders exactly one stock parameter element, `organism`
([GenesByOrthologPattern.tsx#L57](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/sites/genomics-site/webapp/wdkCustomization/js/client/components/questions/GenesByOrthologPattern.tsx#L57)).
When the form opens on an existing step it seeds its tri-state map from
`included_species` and `excluded_species`
([#L132-L142](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/sites/genomics-site/webapp/wdkCustomization/js/client/components/questions/GenesByOrthologPattern.tsx#L132-L142)),
decoding each with `getSpeciesTerms`
([#L90-L101](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/sites/genomics-site/webapp/wdkCustomization/js/client/components/questions/GenesByOrthologPattern.tsx#L90-L101)):
the literal `n/a` is the empty set, the literal `All Organisms` is the root term `ALL`,
and anything else is split on commas and trimmed. The encoder is symmetric and joins with
`", "`
([#L478-L484](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/sites/genomics-site/webapp/wdkCustomization/js/client/components/questions/GenesByOrthologPattern.tsx#L478-L484)).
The terms stored are the **highest** node in each state rather than the leaves
([#L510-L533](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/sites/genomics-site/webapp/wdkCustomization/js/client/components/questions/GenesByOrthologPattern.tsx#L510-L533)),
so an included clade is one term here and many tokens in `profile_pattern`. The two
parameters are at different granularities on purpose.

**The client never reads `profile_pattern` back.** In that file the constant
`PROFILE_PATTERN_PARAM_NAME` appears twice: at its declaration and inside the write. There
is no parser. On form load the effect at `#L154-L178` fires and overwrites
`profile_pattern` with a value regenerated from the tri-state map, which itself came from
the two species lists.

So "for documentation only" is true of the SQL and false of the workflow. The pattern is
the value that runs; the species lists are the value that is remembered. A client that
writes one without the other produces a step that either runs correctly and cannot be
edited, or edits cleanly and runs on a stale pattern.

# `hsap=1T` belongs to a different search on a different site

`profile_pattern` declares its own default, and the default is also its only documentation
([geneParams.xml#L4873-L4879](https://github.com/VEuPathDB/ApiCommonModel/blob/301b2be012af713411e9b0e216ed93c51d04c239/Model/lib/wdk/model/questions/params/geneParams.xml#L4873-L4879)):

```xml
    <stringParam name="profile_pattern"
                 visible="false" length="4000"
                 prompt="Profile Pattern" number="false">
      <help>Example: 'hsap=1T'</help>
      <suggest default="hsap=1T"/>
    </stringParam>
```

The help text and the `suggest default` are the same string, and WDK republishes that
string as `initialDisplayValue`. Measured on both sites on 2026-08-14, it returns **0**.

It is not nonsense, and it is not an older `profile_pattern` syntax either. It is a
well-formed expression in a **different** grammar belonging to a **different** parameter on
a **different** site: OrthoMCL's `GroupsByPhyleticPattern.phyletic_expression`.

Two independent pieces of evidence. ApiCommonModel's own tooling calls that endpoint
directly and passes the pattern as `phyletic_expression`
([phyleticPatternWebService.pl#L82-L84](https://github.com/VEuPathDB/ApiCommonModel/blob/301b2be012af713411e9b0e216ed93c51d04c239/Model/bin/phyleticPatternWebService.pl#L82-L84)),
url-escaping `=`, `>`, `<`, `:`, `,` and parentheses on the way
([#L97-L111](https://github.com/VEuPathDB/ApiCommonModel/blob/301b2be012af713411e9b0e216ed93c51d04c239/Model/bin/phyleticPatternWebService.pl#L97-L111))
- an escape set that describes the `=`/`>=`/`AND` grammar rather than the `LIKE` one. And
the ortho-site client builds exactly the `=1T` shapes
([phyleticPattern.ts#L186-L193](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/sites/ortho-site/webapp/wdkCustomization/js/client/utils/phyleticPattern.ts#L186-L193)):

```ts
    if (nextConstraintType === 'include-all') {
      nonSpeciesExpressionTerms.push(`${node.abbrev}=${node.speciesCount}T`);
    } else if (nextConstraintType === 'include-at-least-one') {
      nonSpeciesExpressionTerms.push(`${node.abbrev}>=1T`);
    } else if (nextConstraintType === 'exclude') {
      nonSpeciesExpressionTerms.push(`${node.abbrev}=0T`);
```

joining subexpressions with `" AND "`
([#L161-L182](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/sites/ortho-site/webapp/wdkCustomization/js/client/utils/phyleticPattern.ts#L161-L182)).
That is a four-state model - free, include-all, include-at-least-one, exclude - against the
genomics-site's three, because a count-bearing grammar can express "at least one" and a
substring match cannot.

The live confirmation closes it. On orthomcl.org on 2026-08-14, `phyletic_expression`
publishes `initialDisplayValue: "EUKA>=5T AND hsap>=10"`, and running the search there:

| `phyletic_expression` on orthomcl.org | Result |
|---|---|
| `hsap=1T` | 200, `totalCount` **9691** |
| `EUKA>=5T AND hsap>=10` | 200, `totalCount` 291 |
| `%hsap:Y%` | **HTTP 500**, `Internal Error` |
| `not a pattern at all` | **HTTP 500**, `Internal Error` |

The two grammars are mutually unintelligible, and they fail in opposite directions.
OrthoMCL parses its expression and throws a 500 on anything it cannot parse. The
genomics-site search does not parse at all - it hands the string to `LIKE` - so a wrong
value is a 200 with zero rows. `hsap=1T` is a valid OrthoMCL expression that has been
sitting in a VEuPathDB site parameter as its default and its only example, and on that
site it means "a census literally equal to the seven characters `hsap=1T`", which no
census is.

Nothing in the pinned repositories explains how it got there. That is a statement about
what was searched - `geneParams.xml`, `geneQueries.xml`, `geneQuestions.xml` and the
`Model/bin` tooling in ApiCommonModel, and the two site clients in web-monorepo - and not
a claim that no explanation exists.

# What a converter has to get right

Five things, in the order they bite:

1. Emit `%`-wrapped, `%`-separated `code:Y` / `code:N` tokens. Nothing else is a
   `profile_pattern`.
2. Sort the codes ascending before joining, or the pattern silently matches nothing.
3. Use leaf species codes only; expand a clade to its leaves first.
4. Write `included_species` and `excluded_species` alongside, or the step cannot be edited
   without losing its meaning.
5. Never treat `initialDisplayValue` as a usable value on this parameter. It is an
   example, from another grammar, and it returns nothing.

The general form of the fifth point is not specific to this search and is recorded as
[WDK-PARAM-010](../rules/parameters-and-vocabularies.md).
