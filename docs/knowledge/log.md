# Knowledge log

## 2026-10-23 - The strict type check covers every test file

- The mypy gate in CI and pre-commit is `uv run mypy --strict src tests`, in place of
  `src` and a list of seven test files. `[tool.mypy]` no longer excludes `tests/`, and
  reads `mypy_path = ["src", "."]` with `explicit_package_bases`, the roots pytest
  imports from, so two test files of one name in two directories are two modules. The
  131 errors the wider run found were in the tests: the live lane reads WDK bodies
  through typed models in `tests/live/_bodies.py`, and the unit tests annotate their
  `TypeAdapter`s and narrow the JSON they index. No source changed, and the hermetic
  suite runs the same tests with the same outcomes.

## 2026-10-22 - A bigWig file's total summary is read with its header

- 0.1.0b21: `BigWigReader.summary()` returns the file's total summary as a frozen
  `BigWigSummary` (`bases_covered`, `min_value`, `max_value`, `sum_data`, `sum_squares`,
  and `mean_depth`, `sum_data / bases_covered` or 0.0), or `None` when the header's
  `totalSummaryOffset` is 0. The header read widens from bytes `0-303` to `0-343`, so a
  summary after 10 or fewer zoom headers arrives in that one read; a summary past it takes
  one more 40-byte read. `summary()` and `depth` share the header read. The read counts
  of `depth` are unchanged. A `totalSummaryOffset` above 0 and inside the header and zoom
  headers raises `TrackReadError`. The recorded AGAP003685 header read is now bytes
  `0-343`, read again on QA VectorBase, so its summary decodes from the recording; the
  recorder names read 1 "the header, zoom headers and total summary". See
  [the JBrowse surface](wdk/rest/jbrowse-surface.md).

## 2026-10-22 - A tabix read is counted before it is sent, and an unlisted search has no class

- 0.1.0b20: `TabixReader.chunk_group_count(track, seqid, start, end)` returns the number
  of ranged reads `lines` sends for that region, read from the index alone, so a caller
  bounds its store reads without reading the track's private chunk functions. See
  [the JBrowse surface](wdk/rest/jbrowse-surface.md).
- `record_class_of(step_id, steps)` returns `str | None` and takes no `fallback`. A search
  or a transform whose `record_class` is unset reads `None`, never the class of its input;
  only a combine reads its class off its inputs, a WDK-named combine and a combine left
  with one input included. See [WDK-STRAT-004](wdk/rules/strategies-and-steps.md).

## 2026-10-22 - A bigWig track is read within bounds, and every JBrowse read is observed

- 0.1.0b19: `BigWigReader(client, data_path).depth(seqid, start, end)` reads per-base
  RNA-seq depth over one region of a bigWig through the store: the header and the
  chromosome tree once per reader, the R-tree root once, one read per level below it and
  one per data block. `BIGWIG_MAX_REGION` (200,000 bases), `BIGWIG_MAX_RTREE_DEPTH` (4),
  `BIGWIG_MAX_BLOCKS` (2), `BIGWIG_MAX_CHROM_TREE_BYTES` (1 MiB), `BIGWIG_MAX_BLOCK_BYTES`
  (256 KiB), `BIGWIG_MAX_ZOOM_LEVELS` (10), `BIGWIG_MAX_NODE_ITEMS` (256) and
  `BIGWIG_BYTE_ORDER` (little-endian) refuse a read past them with `TrackReadError`
  before it is sent. `TrackConfig.url_templates` reads a
  `MultiBigWig` track's `urlTemplates` as `SubTrack(url, name)`, `TrackConfig.subtracks()`
  is that list or the one `urlTemplate`, and `JBrowseClient.coverage_tracks(abbrev)` keeps
  the `rnaseq` tracks whose store class ends in `BigWig`. `Observer.on_jbrowse_request`
  receives each JBrowse HTTP request with `site_host`, `kind` (`store`, `track_list`) and
  `status`, `none` for a request that gets no answer; `OpenTelemetryObserver` records it as
  `veupathdb.jbrowse.request_duration`. The mypy gate now covers the six test files that
  install an observer, so a new `Observer` member fails a test observer that lacks it.
  `jbrowse_capture coverage` stops at its budget of 9 requests and records the agamPEST
  `rnaseq` track list and the six ranges one `depth` call over `AGAP003685` reads on QA
  VectorBase. See [the JBrowse surface](wdk/rest/jbrowse-surface.md).

## 2026-10-21 - An OrthoMCL expression is evaluated on one group, as the site reads it

- 0.1.0b18: `PhyleticExpression.site_reading()` is the expression as the site reads it,
  parentheses dropped and AND before OR ([WDK-SITE-010](wdk/rules/site-model-params.md)).
  `PhyleticExpression.holds_for(proteins, tree)` evaluates that reading on one group's
  genome-to-protein counts (`TaxonCounts`): a `T` count counts the genomes that hold a
  protein, a bare count sums their proteins, and every unit is false on a group with no
  protein of its codes except `=0`/`=0T` ([WDK-SITE-009](wdk/rules/site-model-params.md)).
  `PhyleticExpression.parse` reads AND before OR and no longer refuses the two side by
  side. `check_expression` refuses an expression whose site reading differs from its
  written grouping, a unit that names a code or a genome twice (which `holds_for` also
  refuses), `<=0`, `<=0T`, `<1` and `<1T` with `L=0T` as the form of absence, and a unit
  that states nothing beyond presence. The recorded groups are the
  `orthomcl_group_taxon_counts` fixture and four sampled answers, `orthomcl_groups_*` and
  `orthomcl_group_with_equal_proteins_in_two_genomes`.

## 2026-10-21 - A step's column is counted with its word-cloud reporter

- 0.1.0b18: `get_step_word_counts` reads the counts of one column over a step's records
  through the column's `wordCloud` attribute reporter, which answers on any step, a
  transform included. The reporter counts words after three merges (the split into
  pieces, the case fold, the plural fold), so its counts are record counts only on a
  column whose every value is one token that no merge changes; a matching sum is
  necessary, not sufficient. `WDKWordCounts` refuses the reporter's 10,000-word cap
  answer, and `record_counts` refuses a sum that differs from the step's size. See
  [WDK-ANS-011](wdk/rules/searches-and-answers.md).

## 2026-10-21 - A genome is a Taxons row, and an OrthoMCL clade can hold none

- 0.1.0b18: `TaxonEntry` and `PhyleticNode` carry `clade`. `ortho_taxonomy_of` sets it
  from the table a row came from (`RootTaxons` a clade, `Taxons` a genome), and
  `from_vocab` marks a node with children a clade. `PhyleticTree.species_under` is now
  `genomes_under` and counts only genomes, so the empty clade `BACI` counts 0 and `VIRI`,
  `EUKA` and `ALL` read 14, 783 and 857; `leaf_states` pushes a selection to genomes the
  same way. `species_of` reads a genome's species as the first two words of its label,
  after a leading `Candidatus`, and the first three when the second is `sp.`, `cf.` or
  `aff.`; `SpeciesGroup` and `PhyleticTree.species_groups` group genomes by it.
  `PhyleticExpression.describe` says genome and protein, and names how many genomes and
  species a unit spans. The recorded taxonomy is the `orthomcl_taxonomy` fixture. See
  [WDK-SITE-008](wdk/rules/site-model-params.md).

## 2026-10-21 - The JBrowse reader reads a tabix track by range

- 0.1.0b17: `TabixReader` reads the lines of a bgzipped, tabix-indexed track that overlap
  a genome region, through one ranged read of the store, and `parse_gff_line` types each
  line. `JBrowseClient.junction_tracks` lists an organism's RNA-seq junction tracks, and a
  track reads its index path from `tbiUrlTemplate` or beside its data. A block cut short,
  a block that fails its checksum and an index that is not a generic tabix index raise
  `TrackReadError`. A sequence the index does not name raises `SequenceNotIndexedError`
  (HTTP 404, "Sequence not in the track index", since the track itself reads),
  and an indexed sequence with no feature in the window returns no line. A chunk starts
  no earlier than the linear index offset, and chunks more than one read apart take
  separate reads. GFF3 attribute values are tuples split on `,`.
  `jbrowse_capture junctions` records the P. cynomolgi M junction track
  list, its index and the blocks of `PcyM_07:1380000-1384000`. See
  [the JBrowse surface](wdk/rest/jbrowse-surface.md).

## 2026-10-21 - A refused JBrowse answer is closed unread

- 0.1.0b17: `JBrowseClient` sends each read as a stream and checks the status before it
  reads the body. A 401, a status that is not a success, and a 200 to a ranged read are
  closed without reading their body, so the client does not download the whole file
  from a store that ignores the range. See [the JBrowse surface](wdk/rest/jbrowse-surface.md).

## 2026-10-21 - The JBrowse reader reads a genome window

- 0.1.0b16: `veupathdb.jbrowse` reads a site's JBrowse track list and its store, and
  `GenomeReader` reads a window of genome sequence through the FASTA index under the
  track list's data prefix. A ranged read must answer 206, and a refusal is a 502 that
  carries the site's status. See [the JBrowse surface](wdk/rest/jbrowse-surface.md).

## 2026-10-19 - A scope reads each search definition once

- 0.1.0b15: `search_definitions_read_once` keeps the search definitions read inside it,
  keyed by site, login token, record type, search and the expand flag, and drops them when
  it ends. A definition is built for the user who asks and a vocabulary may list that
  user's own data (WDK-VOCAB-008), so nothing is kept across logins or past the scope. A
  step write inside one reads its search once, where it read it twice; the strategy API no
  longer keeps input-param names of its own.

## 2026-10-18 - The site client keeps the user id and the boolean search

- 0.1.0b14: `resolve_wdk_user_id` reads `GET /users/current` once per login token and the
  site client keeps the id (`HTTPClient.remembered_user_id`, keyed by a hash of the token),
  and `SearchEndpoints.boolean_search` reads a record type's boolean search and its operand
  names once per site client. A host that builds a strategy API per call no longer reads
  them again on every step.

## 2026-10-18 - The recorded stores are QA recordings

The WDK, EDA and VDI stores under `veupathdb.testing.fixtures` are recorded from the QA
sites, one request at a time, under a registered account, and the production backup is
deleted. QA matches production on the site-search stream (352 records), the two genome
lists (64 and 16, three GiardiaDB identifiers over 50 characters) and the refused upload.
The service roots drop their sign-in links, which name the shared production sign-in host.
Two states have no recording: a cached AI expression summary, which only the site's own
summary job makes, and a crashed VDI import. QA passes `import_complete_data_absent` in
under a second, so a test takes the `data` axis out of the recorded `data_running` body
instead. `wdk_record` keeps a JSON list answer as JSON. A first EDA capture into an empty
store starts its provenance file instead of failing.

## 2026-10-16 - A search's column is counted by value

`run_search_column_report` counts a search's records by each value of one column with the
site's `byValue` column reporter, and creates no step; the search config's `columnFilters`
apply first. `WDKAttributeField.tools` names the column reporters and filters the site
offers on an attribute.

## 2026-10-16 - A site-search query is six words at most

The site-search service refuses a query of more than six words with a 400
(`SearchRequest.MAX_TERMS_IN_QUERY` in VEuPathDB/SiteSearchService). `SiteSearchClient` sends
at most six: it drops filler words from the end first, then keeps the first six words. Both the
paged and the streamed form send the fitted text.

## 2026-10-15 - A cleaned value keeps its lines and no indent

`strip_html_tags` joins the words of each line with one space and drops blank lines, so
OrthoMCL's clade counts read one clade per line, as `Microsporidia: 49 / 51`, without the
tabs and spaces the site indents them with.

## 2026-10-15 - Hidden text is not read

`strip_html_tags` drops an element a site styles `display:none` together with its text.
A site writes a sort key there before the value it shows: OrthoMCL's BLAST `evalue`
reads `7.0E-161`, not the sort key and the value run together.

## 2026-10-14 - OrthoMCL's phyletic expression has a grammar here

`PhyleticExpression` parses, writes and reads aloud OrthoMCL's `phyletic_expression`, and
`check_expression` refuses, on the parameter it was stated in, a code the taxonomy lacks and
a unit every group meets or none can, counted over `PhyleticTree.species_under`. `ortho_taxonomy_of` builds a `PhyleticTree` from OrthoMCL's taxon tables through the new
`PhyleticTree.from_taxa`, so both phyletic searches share one tree, one code set and one
refusal ([site-model parameters](wdk/model/site-model-parameters.md)).

## 2026-10-12 - Open paths travel as one shared guest

The client sends no request without a token and holds no deployment token:
`veupathdb_auth_token` left the settings and `resolve_veupathdb_auth_token` left
`veupathdb.auth_context`. A request with no researcher token travels as one guest token,
minted once per process by `veupathdb.guest_token.GuestTokens` and sent on every site and
on EDA ([transport-quirks](wdk/rest/transport-quirks.md)). A site that refuses the guest
raises `WDKLoginRequiredError`. The shared WDK cookie jar never stores an `Authorization`
cookie ([WDK-AUTH-002](wdk/rules/auth-and-transport.md)). The recorders act as the
registered test account named by `WDK_TEST_TOKEN` or `WDK_TEST_EMAIL`/`WDK_TEST_PASSWORD`,
and `veupathdb.testing.hermetic_guest_tokens` mints a guest with no network for a hermetic suite.

## 2026-10-10 - A range value reads its JSON text

`param_value_from_raw` reads a `number-range` or `date-range` value given as the JSON text
of its object, the form WDK sends as a range's `initialDisplayValue` and takes on the wire.
Other text for a range kind is refused with `ValueError`.

## 2026-10-09 - A search waits in its turn's line, the host's gate and the site's slots

A request that runs a search takes the line of its turn on its site (`search_turn`), the
gate the host installs (`use_search_gate`, called with a `SearchRequest`), then one of the
site's slots; each waits first come first served and none refuses
([decision](decisions/a-search-waits-in-line-and-the-host-owns-the-gate.md)).
`HIGH_SPEED_SNP_SEARCHES` names the thirteen searches ApiCommonModel runs on the
High Speed SNP Search plugins ([WDK-HTTP-006](wdk/rules/auth-and-transport.md)). A client
learns the search of each step and the tree of each strategy it creates or reads, so a
step or strategy request names its searches. `budget_seconds` on `post` and
`run_search_report` bounds a request from its send. `Observer.on_wdk_search_wait` reports each wait.
`HTTPClient` takes a `site_id`, and the connection pool sizes are constants.

## 2026-10-09 - Tests run against QA, and a deployment names its site list

The package ships no default site list: `load_sites_config` raises
`SitesConfigNotSetError` when `VEUPATHDB_SITES_CONFIG` names no file, and the production
list is `docs/sites/production.yaml`. The wheel carries the QA list at
`veupathdb.testing.QA_SITES_FILE`; every test and every recorder reads it, and no
recorder takes an option that reaches another list. The bodies recorded on production
moved to `fixtures-production-backup-2026-10-09/`; `verify` names each missing body and
every test that reads one is skipped with `NEEDS_QA_RECORDING`.
`scripts/check-test-sites.mjs` fails on a production or beta host outside `docs/`
([decision](decisions/tests-run-against-qa-and-a-deployment-names-its-sites.md)).

## 2026-10-07 - The portal's project id is UniDB

The `veupathdb` site's `project_id` is `UniDB`, the id the portal's WDK `GET /service`,
its page config and VDI's install targets name; `EuPathDB` made EDA answer 404 "Invalid
project ID", site search find no searches, datasets, pathways or compounds, and a VDI
upload name a target VDI does not install to.
`tests/live/test_every_site_names_its_wdk_project.py` checks every site's `project_id`
against its WDK `GET /service`. `veupathdb-py` is 0.1.0b3.

## 2026-10-06 - A search is sent once, a site runs a few at a time, and every request names its sender

A request that makes WDK run a search (`runs_a_search`: a report, a step or strategy read,
an analysis run) waits for one of `veupathdb_concurrent_searches_per_site` slots (default 4)
on its site's client and is not sent again after a 5xx or a timeout, because WDK keeps
running the first search ([WDK-HTTP-005](wdk/rules/auth-and-transport.md)). A connection
that never opened and the delayed-result sentinel are still retried. Every client that
reaches a VEuPathDB service sends `veupathdb_user_agent` (default `veupathdb-py/<version>`;
a host sets its own). The WDK connection pool is 64, from 1000. `veupathdb-py` is 0.1.0b2.

## 2026-10-04 - A report sends tree leaves, and a label comparator needs a categorical shape

`VEuPathDBClient.expand_tree_params_to_leaves` reads the search and sends each parent
term of a `countOnlyLeaves` tree as its leaves through `leaves_of_tree_values`
(`wdk/tree_leaves.py`); `create_step` and `run_search_report` both send their parameters
through it, so a step and a report of one configuration send the same leaves
([WDK-VOCAB-002](wdk/rules/parameters-and-vocabularies.md)). A report with no parameters
reads no search. A transport failure names the exception class when its text is empty:
"Request failed after retries: ReadTimeout". `validate_compute_config` refuses a
comparator group of labels alone on a variable whose `dataShape` is not `categorical`,
`ordinal` or `binary`, and names the variable and its shape; a `continuous` variable is
compared by bins with `min` and `max` ([computes-and-jobs](eda/computes-and-jobs.md)).
`ValueVariableFacts` carries `data_shape` and `LabeledRangeFacts` carries `min`.
A configuration with no term list names no tree parent, so it reads no search
definition (`tree_leaves.holds_a_term_list`). `veupathdb-py` is 0.1.0a22.

## 2026-10-03 - The PCA compute and four statistical plots are read

`EdaClient` runs `dimensionalityreduction` through the existing submit and poll, reads its
computed variables with `compute_meta` (`POST /computes/{name}/meta`, which answers only
`text/plain`), and reads `scatterplot`, `two_by_two`, `contingency_table` and `boxplot`
into typed models that refuse misaligned parallel arrays. Six bodies are recorded on
`STUDY_e973eadd57` and bound in `eda_schemas`, with ten new specification defects and the
`retyped-on-the-wire` kind ([rest-surface](eda/rest-surface.md)). The deployment answers
every twobytwo request with a 400 R evaluation failure, so the 2x2 shape follows the R
producer ([visualizations](eda/visualizations.md)).

## 2026-09-30 - A failed rnaseqrc import is the plugin's fault, not a `label` column

[vdi-surface](wdk/rest/vdi-surface.md) no longer says a sample-details column named `label`
stops an rnaseqrc import. Byte-identical uploads with no such column failed with
`import: failed` and exit 255 twice and installed twice on plasmodb. The wrangler exits
255 only through `stop_unexpected_error`, which the rnaseqrc path reaches when a Claude API
call of its annotation step fails. A `failed` import takes a new upload of the same files;
an `invalid` import names what is wrong with the data.

## 2026-09-28 - A filter parameter's term summary is read

`get_ontology_term_summary` calls
`POST /record-types/{recordType}/searches/{searchName}/{paramName}/ontology-term-summary`
with `ontologyId`, `filters` (each a `FilterTermClause` in its wire form) and
`contextParamValues`, and reads `WDKOntologyTermSummary`: `valueCounts` of
`WDKOntologyTermValueCount` (`value`, `count`, `filteredCount`), `internalsCount` and
`internalsFilteredCount`. [WDK-PARAM-014](wdk/rules/parameters-and-vocabularies.md)
records that the response carries no display name: a value is its own label, and a
term's label is the `display` of its node in the parameter's `ontology`. The fixture
`ontology_term_summary_ngs_snps_sex` holds plasmodb `GenesByNgsSnps.variation_sample_meta`
term `VAR_68bb04bd` (`sex`) under P. falciparum 3D7: `female` 6, `male` 6, 12 samples.
`veupathdb-py` is 0.1.0a20.

## 2026-09-27 - The organism parameter is the one WDK marks

[WDK-PARAM-013](wdk/rules/parameters-and-vocabularies.md) records that WDK publishes a
parameter's `<propertyList>`s under `properties`, and that ApiCommonModel marks an
organism parameter with `organismProperties`. `WDKBaseParameter.is_organism` reads the
mark. `extract_output_organisms` takes a map from a search name to its marked parameter
and no longer recognizes `organism` and `text_search_organism` by name, which missed
`organismSinglePick` and `organism_select_none`. An ortholog step with no target value
now answers unknown instead of its input's organism. Two fixtures are recorded,
plasmodb `GenesByNgsSnps` and vectorbase `GenesByGeneModelChars`; over every transcript
search on both sites, no search carries two marked parameters. `ms_assay` and
`ptm_assay` are marked too, and their values are experiments under organism branches.

## 2026-09-26 - A filter clause's value takes the shape its facet parses

[WDK-PARAM-012](wdk/rules/parameters-and-vocabularies.md) records that
`FilterParamNewStableValue` reads a `date` clause and a `number` clause with
`isRange: true` as an object of `min` and `max`, and a `string` clause and a `number`
clause with `isRange: false` as a list. On plasmodb.org a member list on the range facet
`variants_per_kb` of `GenesByVariantCharacteristics` is refused with
`JSONObject["value"] is not a JSONObject`. The rule is anchored in `veupathdb-mcp`, where
a clause is bound to its facet; this client needs no change, because
`FilterTermClause.value` is `JsonValue`.

## 2026-09-24 - A search report takes view filters, and a gene-id distribution is recorded

`run_search_report` takes `view_filters`, sent as `viewFilters` at the top level of the
search report body beside `searchConfig` and `reportConfig` (WDK-FILTER-003), the way
`get_step_answer` does. With none given the body carries no `viewFilters` key. Live on
plasmodb, `GenesByMolecularWeight` on P. falciparum 3D7 between 50000 and 52000 Da
returned 85 transcript rows for 84 genes, and 84 rows under
`representativeTranscriptOnly`.

`eda_capture` records `/distribution` reads beside the analysis documents:
`DISTRIBUTION_CAPTURES` declares each request, and `record` writes the body with the
first 20 histogram bins and whole statistics, and a provenance entry that states the
cut. The four `gene_id_distribution_*` fixtures hold the `VEUPATHDB_GENE_ID`
distribution of the RNA-Seq and the phenotype study, under one example subset and
under none, bound to `VariableDistributionPostResponse` in `eda_schemas`.
`veupathdb.testing.eda_fixtures.recorded_distribution` reads one as an
`EdaDistributionResponse`. `EdaClient.distribution` builds its body through the new
`distribution_body`, which the capture sends too.

## 2026-09-24 - A user dataset and an EDA analysis never travel as the deployment

Every `VdiClient` call, and every `EdaClient` path under `/users/`, takes its token from
`veupathdb_auth_token_ctx` or the client's own `auth_token=` through the new
`resolve_user_auth_token` in `veupathdb.auth_context`, and raises `WDKLoginRequiredError`
before a request is built when neither carries one. Before this, both fell back to
`VEUPATHDB_AUTH_TOKEN`, so a VDI publish, poll or delete made with no request token ran as
the deployment's service account. EDA study, subsetting and compute paths keep the
settings fallback. The rule is [WDK-AUTH-005](wdk/rules/auth-and-transport.md); the name
is not on the published surface. `veupathdb-py` is 0.1.0a16.

## 2026-09-23 - An analysis document holds every compute the site offers

`EdaComputation.descriptor` is a left-to-right union: `EdaDifferentialExpressionDescriptor`
(the old `EdaComputationDescriptor`, renamed), `EdaPassDescriptor` for the pass-through
compute every plain visualization hangs off, and `EdaOtherComputeDescriptor` for every
other plugin and for a DE compute the EDA app has not finished configuring. The alias is
`EdaComputeDescriptor`. `EdaVisualization.descriptor` is `EdaVolcanoDescriptor` or
`EdaOtherVisualizationDescriptor`, and both keep `thumbnail` and `applicationContext`; the
volcano configuration keeps the plot settings the app stores. A computation's and a
visualization's `display_name` is `None` when the site stores none.
`differential_expression_computations` returns the complete DE computations of a
descriptor in order, each an `EdaDifferentialExpressionComputation` that holds the
`computation` as stored beside its narrowed `descriptor`. Every node of the stored
document keeps the keys it does not model (`extra="allow"` on `EdaStoredModel`; the
other EDA models still drop them, as they are responses or request bodies). A node
read from the site dumps with `exclude_unset=True` exactly as stored; a node built here
dumps with its defaults. `analysis_descriptor_patch` writes a PATCH body that way,
deciding per computation and per visualization by whether the descriptor's `type` is
in `model_fields_set`, and `patch_descriptor` sends it. The anchor is the recorded
`analysis_detail_pass_and_de` fixture, which `python -m veupathdb.devtools.eda_capture
record` writes (create, PATCH, GET, DELETE); `Computation.displayName` joins the RAML
spec defects. See [rest-surface](eda/rest-surface.md). `EdaAnalysesClient.collection_path`
is public. `veupathdb-py` is 0.1.0a15.

## 2026-09-23 - The identity read answers fast or raises

`fetch_current_user` makes one attempt under a 10 s deadline, where every other read keeps
three attempts under the site's timeout. `HTTPClient.get` takes an `attempts` keyword,
three by default. The read returns `None` only when the request carries no token or the
site answers 401 or 403; a site that does not answer raises `WDKError` (502 past the
deadline, on a transport timeout or a refused connection, the site's own status for a
5xx), so a consumer can tell an outage from a signed-out user. An unknown site raises
`SiteNotFoundError` and an unreadable profile raises, where both were `None` before.
See [transport-quirks](wdk/rest/transport-quirks.md).
`veupathdb-py` is 0.1.0a14.

## 2026-09-23 - A search-config update starts from the step's own config

`update_step_search_config` keeps the step's own filters, column filters and weight,
and replaces its `parameters` map whole with the caller's map, every input-step value set
to the value the step holds. The caller's weight replaces the step's only when the caller
sets one. The body always carries `parameters`, empty for a search without any (WDK
resets every key the body omits). On the update path a failed catalog read of the
input-step names raises, and a step that holds no value for an input refuses the write
before it reaches WDK (WDK-STEP-003). Step creation still proceeds on a failed catalog
read, because the create endpoint takes no record type. `update_step_filters` builds its
body the same way.

`get_step_records` and `get_step_answer` take `view_filters`, sent as `viewFilters` at the
top level of the step report body beside `reportConfig` (WDK-FILTER-003). A transcript
step reports one row per transcript while its count is of genes, so a caller that pages
genes sends `representativeTranscriptOnly`. With no view filters the body is unchanged.
The two methods no longer take `user_id`: no consumer passed one, and they read as the
session's user.
`veupathdb-py` is 0.1.0a13.

## 2026-09-22 - One step read serves a search-config update

`update_step_search_config` reads the step once and takes both its filters and its
input-step values from that read. `veupathdb-py` is 0.1.0a12.

## 2026-09-22 - A search-config update carries the step's own inputs

`update_step_search_config` reads the step back and sends every input-step
(AnswerParam) value at the value the step holds, whatever the caller states for it
(WDK-STEP-003: the endpoint refuses a changed input, and the client sent none).
Before this, a change to a transform's own parameter could not be pushed.
`veupathdb-py` is 0.1.0a11.

## 2026-09-11 - The signing-key reset is published

`forget_signing_keys` is on `veupathdb.wdk`. A consumer's test suite that fakes a WDK
login drops the OAuth signing-key cache through the surface, so no consumer reads the
module that holds it. `veupathdb-py` is 0.1.0a10.

## 2026-09-11 - One token resolution, a declared surface, and every rule proven here

WDK, EDA and VDI resolve the request's token through one function,
`veupathdb.auth_context.resolve_veupathdb_auth_token`: the contextvar, then the client's
own `auth_token`, then settings. `EdaClient` and `VdiClient` take an `auth_token`
keyword, so a deployment that exports one environment variable reads an EDA study as it
reads a WDK search list. One WDK rule still stands above the order: a path under
`/users/` is refused unless the contextvar carries the token.

Sixteen surfaces are published, each declaring `__all__`, all of them checked in at
`tests/unit/published_surface.json`. `tests/unit/consumer_imports.json` records the
names the two in-house consumers read under the surface each one reads them from, and
the gate fails when a name stops being published on that surface.
`veupathdb.wdk._failures` stays private and `veupathdb.wdk` publishes the three names
its readers need.

The two schema readers are a `devtools` extra. The wheel already shipped
`veupathdb.devtools`, and now an installed copy can import it.

Installing a settings source drops the router, the cached sites config and every
per-site client cache built from the previous one. `reset_site_router` publishes the
same reset, and this package's own conftest uses it instead of reaching into a private
signing-key cache.

The login refusal states the condition rather than a feature list, and names no entity
this package does not model. Three docstrings state what their symbol is rather than
which layer called it, and `tests/unit/test_package_boundary.py` fails on a caller's
vocabulary in a docstring.

Every rule status names a test this repository runs. The 36 that named another
repository are now 29 hermetic cases under `tests/unit/rules/`, two live cases, and
five `PARTIAL` - four hermetic and one live - where the named case holds the half that
can be held. The run reports
78 rules: 73 enforced, 5 partial, 0 unenforced.

The WDK and EDA trees state WDK and EDA, with the client as the actor. The application's
mapping, its authority ranking and its two verification sites left for
`pathfinder: docs/knowledge/wdk/pathfinder/`; `tests/unit/test_bundle_subject.py` fails on
the application's name anywhere under `wdk/` or `eda/`. One paragraph was deleted rather
than moved: it described `StepValidation` defaults the tree has not had since the field
became `StepValidation | None`.

- The two visible phyletic species lists are `PHYLETIC_LIST_PARAMS` on
  `veupathdb.domain.parameters`. The five names of a phyletic search are the two
  structural maps, these two lists and the derived pattern, and the suite asserts that
  partition. At its next tag `veupathdb-mcp` deletes its own `PHYLETIC_LIST_PARAMS` from
  `catalog/param_formatting.py`, drops it from its published surface and reads this one
  at its three call sites; `pathfinder` moves one import line.

- `build_wdk_step_tree` and `MissingWDKStepIdError` join `walk_wdk_step_tree` in
  `veupathdb.wdk.step_tree`, and `resolve_record_type` is `veupathdb.wdk.record_types`.
  Both are `veupathdb.wdk` and not `veupathdb.domain.strategy`, because each one names a
  WDK wire model and no module of the domain package names a module of `veupathdb.wdk`.
  `veupathdb.wdk` now names four modules of the strategy package, and all four state WDK
  shapes. At its next tag `veupathdb-mcp` deletes `wdk/step_tree.py` and
  `wdk/record_types.py`, imports the three names from here and drops them from its
  surface; `pathfinder` moves one import line in `services/strategies/sync.py`.

- Nine shapes a consumer constructs are published: `InputStepValue`, `PhyleticNode`,
  `WDKVocabNodeData` and `collect_leaf_terms` on `veupathdb.domain.parameters`, and
  `AiExpressionReport`, `SiteSearchResponse`, `SiteSearchStreamRecord`, `WDKFilterParam`
  and `WDKReporter` on `veupathdb.wdk`. Eight of them are the inner shape of a name that
  was already published, and none of them is a test double.
  `tests/unit/consumer_imports.json` measures the tool server's suite beside its `src`,
  so a rename of a shape that suite builds fails here. At its next tag `veupathdb-mcp`
  rewrites fifteen imports onto the package surface.

## 2026-09-10 - The authoring model leaves, and an unbound parameter is a parameter

`session`, `operations/`, `spec_diff`, `combination_check`, `build_outcome`,
`operational_spec`, `constraints`, `SyncStateProtocol` and `PersistedStrategyGraph`
left `domain/strategy/` for the consuming application. What is left states WDK's own
shapes: the step tree, the keyed step map, the traversal over both, the combine
operators, the validation bundle and the organism scope rule.

`StepStatus` and `step_status` left with them. Four states saying whether a step has
reached WDK yet are a build lifecycle over the keyed map, and WDK states no such
enum. `StrategyStep` and `is_computable` stay, so the lifecycle reads them across the
seam and `veupathdb-mcp`, which names neither status symbol, is untouched.

WDK-VALID-004 anchored that lifecycle. It now anchors `StepValidation.rejects` and
the tests beside it: the half of the rule a client owns is the claim it reads back,
and that claim is the validation bundle.

`OpenSlot` split on the line its readers already draw. The parameter name, the
question and the vocabulary are `UnboundParameter` in
`veupathdb.domain.parameters.unbound`, which is what the MCP server's parameter
binding builds and reads. The criterion a slot is attached to is the spec's, so it
left with the spec. There is no forwarding module at the old path: `veupathdb-mcp`
names the new one at its next release.

The `WireParams` alias moved into `veupathdb.wdk.value_decoding`, so `veupathdb.wdk`
names two modules of this package and both are WDK shapes.

WDK-STRAT-006 anchors the step node's `secondary_input` and the tree tests beside it.
The rule is about the shape a client can express, and the shape is what stayed.

The consuming application's card said the cut costs 47 edges out of `veupathdb.wdk`.
That count was measured before the split. Measured here the edge set was four lines
into three modules, all of them WDK shapes.

## 2026-09-09 - The refusal base takes the host's code enum, the strategy prefix leaves, and an absent experiment count reads None

`VEuPathDBError` is generic in its code enum, so a host application puts its own
error hierarchy under this base instead of maintaining a parallel one. The client's
own refusals name `VEuPathDBErrorCode`; a handler that takes any refusal names the
bound.

The reserved prefix that marks a helper strategy is now a settings field with a
neutral default. It named one product and was written into the user's real VEuPathDB
account. A deployment that already wrote helper strategies states its historical
prefix in the same change that takes this release, or those strategies stay in the
account unmatched.

`env_ignore_empty=True` is stated in the settings docstring and asserted in the
suite, because a blank environment variable resolving to the field default is the
behaviour that keeps a validator unnecessary.

An `aiExpression` entry that answers `present` carries the summary and
`basedOnIncompleteData` and no experiment counts; the site writes `numExperiments`,
`numExperimentsComplete` and the `experimentStatus` map only on the branches that answer
no summary. The two counts are `int | None` now, so a reader tells an absent count from a
count of zero. A consumer that compares them handles `None` as "the site stated nothing".
`basedOnIncompleteData` is modelled beside them as `bool | None`, so a consumer can caveat
a summary the site generated over part of the experiment set. WDK-ANS-009 states the
measured `present` shape. The recorded aiExpression bodies now hold a `present` entry and
an `experiments_incomplete` one, and their fixture names say which is which.

Each experiment line of that summary also names its experiment and its assay, so
`AiExperimentSummary` reads `experiment_name` and `assay_type` beside the six keys it
already read. Those keys are snake_case on the wire, so the model states them as they
arrive. A tool that quotes a summary line can now say which experiment it came from
instead of quoting a dataset id.

## 2026-09-08 - The small client moves arrive, and the app prose leaves

`GET /users/current` and its typed profile, the two EDA validation predicates, the
OpenTelemetry observer adapter, the WDK capture transport and the orphaned-step delete
moved in from the consuming application. `veupathdb_oauth_url` moved in from the MCP
server's settings, because the function that reads it is this client's.

Four sections that spoke about the consuming application left: the three EDA
"what this means" sections and the step-analysis usage note. What names a module in
another repository is now written as a citation - `pathfinder:` or `veupathdb-mcp:` -
and every path that still spelled the pre-split `integrations/veupathdb/` tree names
this package instead. WDK-AUTH-004 is enforced here now that `password_logout` has a
test in this suite.

## 2026-09-08 - ruff format owns the bundle's Python blocks

`ruff format` formats Python code blocks inside markdown from ruff 0.16, so
`uv run ruff format --check .` now covers every file in this bundle as well as
`src` and `tests`. A Python block here is formatted code, not free text.

## 2026-09-05 - The bundle arrives with the client

The WDK model, REST and rule bundles and the whole EDA bundle moved here from
PathFinder's `docs/knowledge/`, with every anchor and every named test repointed at
this tree. A rule whose enforcement lives in the consuming application is `UNENFORCED`
here, with a `reason` naming the consumer's test: 37 of the 78 rules are in that state,
and the count is the honest measure of what this repository's own suite holds.

PathFinder keeps the eight `WDK-MAP` rules, because a mapping rule is an invariant of
the application rather than a fact about WDK.
