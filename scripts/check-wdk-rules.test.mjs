import { test } from "node:test";
import assert from "node:assert/strict";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { Coverage, collect } from "./check-wdk-rules.mjs";

const FIXTURES = join(dirname(fileURLToPath(import.meta.url)), "__fixtures__/wdk-rules");
const errorsFor = (name) => collect(join(FIXTURES, name));

test("a conformant bundle produces no errors", () => {
  assert.deepEqual(errorsFor("clean"), []);
});

test("a malformed rule id is rejected", () => {
  const errors = errorsFor("bad-id");
  assert.equal(errors.length, 1);
  assert.match(errors[0], /malformed rule id/);
});

test("a duplicate rule id is rejected", () => {
  const errors = errorsFor("duplicate-id");
  assert.equal(errors.length, 1);
  assert.match(errors[0], /duplicate rule id/);
});

test("an unrecognized class is rejected", () => {
  const errors = errorsFor("bad-class");
  assert.equal(errors.length, 1);
  assert.match(errors[0], /class must be one of/);
});

test("an upstream link not pinned to a sha is rejected", () => {
  const errors = errorsFor("unpinned-upstream");
  assert.equal(errors.length, 1);
  assert.match(errors[0], /upstream github link is not pinned/);
});

test("an anchor whose file is missing is rejected", () => {
  const errors = errorsFor("missing-anchor-file");
  assert.equal(errors.length, 1);
  assert.match(errors[0], /anchor file does not exist/);
});

test("an anchor whose symbol is absent is rejected", () => {
  const errors = errorsFor("missing-anchor-symbol");
  assert.equal(errors.length, 1);
  assert.match(errors[0], /anchor symbol not found/);
});

test("an ENFORCED status naming a missing test is rejected", () => {
  const errors = errorsFor("missing-test");
  assert.equal(errors.length, 1);
  assert.match(errors[0], /named test not found/);
});

test("a prose doc citing an undefined rule id is rejected", () => {
  const errors = errorsFor("undefined-reference");
  assert.equal(errors.length, 1);
  assert.match(errors[0], /cites undefined rule/);
});

test("a bundle with no rule files is rejected rather than passing vacuously", () => {
  const errors = errorsFor("does-not-exist");
  assert.equal(errors.length, 1);
  assert.match(errors[0], /no rule files found/);
});

// The fixture plants a decoy prose file at the root citing an undefined rule.
// A prose loop that walked root instead of bundle would surface that citation,
// so the empty result proves both halves of the two-argument split.
test("rules and prose are found under bundle while anchors resolve against root", () => {
  const root = join(FIXTURES, "split-root");
  assert.deepEqual(collect(root, join(root, "bundle")), []);
});

test("bundle defaults to root, so the wrong root finds no rules", () => {
  const errors = collect(join(FIXTURES, "split-root"));
  assert.equal(errors.length, 1);
  assert.match(errors[0], /no rule files found/);
});

test("an unpinned raw.githubusercontent.com link is rejected", () => {
  const errors = errorsFor("unpinned-raw");
  assert.equal(errors.length, 1);
  assert.match(errors[0], /upstream github link is not pinned/);
});

test("an anchor symbol must match on a word boundary, not as a substring", () => {
  const errors = errorsFor("anchor-precision");
  assert.equal(errors.length, 2);
  assert.match(errors[0], /anchor symbol not found in src\/sample\.py -> Step$/);
  assert.match(errors[1], /anchor symbol not found in src\/sample\.py -> Foo::bar$/);
});

test("vitest and bare-path test ids resolve", () => {
  assert.deepEqual(errorsFor("vitest-status"), []);
});

test("a renamed vitest case is rejected", () => {
  const errors = errorsFor("vitest-missing-test");
  assert.equal(errors.length, 1);
  assert.match(errors[0], /named test not found in tests\/sample\.test\.ts -> rejects cycles/);
});

test("undefined citations are caught in rest/ and pathfinder/ too", () => {
  const errors = errorsFor("prose-dirs");
  assert.equal(errors.length, 2);
  assert.match(errors[0], /rest\/a\.md: cites undefined rule WDK-PARAM-404/);
  assert.match(errors[1], /pathfinder\/b\.md: cites undefined rule WDK-VOCAB-500/);
});

test("a withdrawn rule needs no class, upstream or anchor", () => {
  assert.deepEqual(errorsFor("withdrawn-clean"), []);
});

test("a withdrawal with no reason is rejected", () => {
  const errors = errorsFor("withdrawn-bare");
  assert.equal(errors.length, 1);
  assert.match(errors[0], /malformed status/);
});

test("prose citing a withdrawn rule is rejected", () => {
  const errors = errorsFor("withdrawn-cited");
  assert.equal(errors.length, 1);
  assert.match(errors[0], /cites withdrawn rule WDK-STEP-001/);
});

test("only the exact basename index.md is skipped", () => {
  const errors = errorsFor("basename-index");
  assert.equal(errors.length, 1);
  assert.match(errors[0], /malformed rule id "WDK-PARAMS-1"/);
});

test("a rules file whose headings are at the wrong level is rejected", () => {
  const errors = errorsFor("wrong-heading-level");
  assert.equal(errors.length, 1);
  assert.match(errors[0], /contains no rules/);
});

test("a test selector must match on a word boundary, not as a substring", () => {
  const errors = errorsFor("selector-substring");
  assert.equal(errors.length, 1);
  assert.match(errors[0], /named test not found in tests\/test_sample\.py -> test_step$/);
});

test("a directory anchor is rejected with and without a symbol", () => {
  const errors = errorsFor("anchor-directory");
  assert.equal(errors.length, 2);
  assert.match(errors[0], /WDK-STEP-001 anchor is a directory, not a file -> src$/);
  assert.match(errors[1], /WDK-STEP-002 anchor is a directory, not a file -> src$/);
});

test("a directory named as the enforcing test is rejected", () => {
  const errors = errorsFor("test-directory");
  assert.equal(errors.length, 2);
  assert.match(errors[0], /WDK-STEP-001 named test is a directory, not a file -> tests$/);
  assert.match(errors[1], /WDK-STEP-002 named test is a directory, not a file -> tests$/);
});

// The convention promises pinned evidence for every WDK concept, not only for
// the rules. `model/` proves prose is covered and `sources.md` proves the scan
// is not limited to the three prose directories. Both assertions anchor on `$`,
// so a URL carrying its trailing sentence period would fail them.
test("an unpinned github link outside a rule block is rejected", () => {
  const errors = errorsFor("unpinned-prose");
  assert.equal(errors.length, 2);
  assert.ok(
    errors.some((e) =>
      /^model\/doc\.md: unpinned github citation -> https:\/\/github\.com\/VEuPathDB\/WDK\/blob\/main\/Model\/src\/main\/java\/org\/gusdb\/wdk\/model\/user\/Step\.java$/.test(e),
    ),
    `no clean model/ error in ${JSON.stringify(errors)}`,
  );
  assert.ok(
    errors.some((e) =>
      /^sources\.md: unpinned github citation -> https:\/\/raw\.githubusercontent\.com\/VEuPathDB\/web-monorepo\/main\/packages\/libs\/wdk-client\/src\/Utils\/WdkModel\.ts$/.test(e),
    ),
    `no bundle-root error in ${JSON.stringify(errors)}`,
  );
});

// The positive control. Without it a regex that matched nothing would look
// identical to a regex that matched correctly.
test("pinned links in prose, in a reserved index, and non-github urls all pass", () => {
  assert.deepEqual(errorsFor("pinned-prose"), []);
});

// SITE is a namespace of its own because the parameters it governs are declared
// in ApiCommonModel rather than in WDK. The fixture carries both directions in
// one file: WDK-SITE-001 must be admitted, and the near-miss WDK-SITES-001 must
// not be, so widening the list to a prefix match would fail this.
test("the SITE namespace is admitted and a near-miss is still rejected", () => {
  const errors = errorsFor("site-namespace");
  assert.equal(errors.length, 1);
  assert.match(errors[0], /malformed rule id "WDK-SITES-001"$/);
});

// An unenforced rule is admissible only while it says why. Without the reason
// the column fills with silence, which is the state this gate exists to end.
test("an unenforced rule with no reason is rejected", () => {
  const errors = errorsFor("unenforced-without-reason");
  assert.equal(errors.length, 1);
  assert.match(errors[0], /is UNENFORCED and gives no reason/);
});

test("the run reports what the bundle claims about itself", () => {
  const coverage = new Coverage();
  assert.deepEqual(collect(join(FIXTURES, "clean"), join(FIXTURES, "clean"), coverage), []);
  assert.equal(coverage.total, 1);
  assert.equal(coverage.unenforced.length, 1);
  assert.equal(coverage.unenforced[0].id, "WDK-STEP-001");
});

test("an enforced rule is counted as enforced rather than as a gap", () => {
  const coverage = new Coverage();
  collect(join(FIXTURES, "vitest-status"), join(FIXTURES, "vitest-status"), coverage);
  assert.equal(coverage.unenforced.length, 0);
  assert.ok(coverage.enforced > 0);
});
