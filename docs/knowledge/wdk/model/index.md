# WDK model

What WDK is. These explain; they do not assert. Assertions live in [the rules](../rules/).

- [Users, auth, and sessions](users-auth-and-sessions.md) - guests against registered users, and which identity a request runs as
- [Strategies and step trees](strategies-and-step-trees.md) - structure against data, what the root step decides, and why the only structural edit is replacing the whole tree
- [Steps and search configuration](steps-and-search-config.md) - the three kinds of step, what is inside `searchConfig`, the boolean triple, and the four states a step can be in
- [Searches and record classes](searches-and-record-classes.md) - the one record class a search is bound to, its two names, why groups are layout, and why the search list belongs to the deployment
- [Answers, reports, and attribute values](answers-reports-and-attributes.md) - the two report endpoints, what `standard` puts in `meta` and `records`, the three shapes an attribute value takes, and where an enrichment result comes from
- [Parameters and their wire forms](parameters.md) - the eleven types, why `displayType` is not one of them, and the exact string each type takes in `searchConfig.parameters`
- [Dependent parameters and vocabularies](dependent-params-and-vocabularies.md) - flat and tree vocabularies, the fake root, `countOnlyLeaves`, and why a dependent value means nothing without the parent it was read under
- [Site-model parameters, and the phyletic profile pattern](site-model-parameters.md) - the parameters ApiCommonModel declares and WDK only executes, `profile_pattern` as a SQL `LIKE` pattern over a species census, and why its own published default returns nothing
- [The three filter mechanisms](filters.md) - `filter` parameters against `filters` against `columnFilters`, where `viewFilters` actually goes, and which of the four counts a report returns honours it
- [Validation, and the four different things a missing number means](validation.md) - the bundle and its levels, why validity is a claim about a level, how invalidity reaches a consumer, and the difference between a result of zero, an unrun step, an invalid step and a lost identity
- [Step analyses](step-analyses.md) - analysis types and their forms, why the defaults are advisory, the create-run-poll-fetch protocol whose successes are 202 and 204, and what PathFinder runs today
