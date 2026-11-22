import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import {
  ALLOWED,
  SITE_DOMAINS,
  ignoredNames,
  isAllowed,
  offencesIn,
  productionHosts,
  scannedPaths,
} from "./check-test-sites.mjs";

const host = (...labels) => [...labels, "org"].join(".");

test("every site domain is production when it carries no prefix", () => {
  for (const domain of SITE_DOMAINS) {
    assert.deepEqual(productionHosts(`https://${host(domain)}/x/service`), [
      { line: 1, host: host(domain) },
    ]);
  }
});

test("www, beta, a numbered server and any other label are production", () => {
  for (const prefix of ["www", "beta", "w1", "auth", "wdk-mcp"]) {
    assert.equal(productionHosts(`https://${host(prefix, "plasmodb")}/`).length, 1, prefix);
  }
});

test("an address on the production domain is production", () => {
  assert.deepEqual(productionHosts(`help@${host("veupathdb")}`), [
    { line: 1, host: host("veupathdb") },
  ]);
});

test("the qa and q2 hosts pass, under any further label", () => {
  const text = [
    `https://${host("qa", "plasmodb")}/plasmo.qa/service`,
    `https://${host("q2", "toxodb")}/toxo.q2/service`,
    host("www", "qa", "toxodb"),
  ].join("\n");
  assert.deepEqual(productionHosts(text), []);
});

test("a site name that is not a host passes", () => {
  assert.deepEqual(productionHosts("plasmodb toxodb.json qa.plasmodb.organism"), []);
});

test("each offence names the file, the line and the host", () => {
  assert.deepEqual(
    offencesIn([["tests/conftest.py", `ok\nBASE = "https://${host("plasmodb")}/eda"\n`]]),
    [
      `tests/conftest.py:2: names the production host ${host("plasmodb")}; a test, a recorder and a default reach the QA sites only`,
    ],
  );
});

test("only the allowlisted paths are exempt", () => {
  assert.ok(isAllowed("docs/sites/production.yaml"));
  assert.equal(isAllowed("src/veupathdb/testing/qa_sites.yaml"), false);
  assert.equal(isAllowed("src/veupathdb/testing/fixtures/wdk/record_types.json"), false);
  assert.equal(isAllowed("tests/conftest.py"), false);
  assert.equal(isAllowed(".github/workflows/ci.yml"), false);
  assert.equal(ALLOWED.some((entry) => entry.startsWith("tests") || entry.startsWith(".github")), false);
});

test("the walk skips caches, ignored names and the allowlist, and reads everything else", () => {
  const root = mkdtempSync(join(tmpdir(), "check-test-sites-"));
  for (const directory of [".venv/lib", "docs", "tests/unit", ".github/workflows", "src/veupathdb/testing/fixtures/wdk"]) {
    mkdirSync(join(root, directory), { recursive: true });
  }
  for (const path of [
    ".venv/lib/site.py",
    "docs/page.md",
    "tests/unit/test_a.py",
    ".github/workflows/ci.yml",
    "src/veupathdb/testing/fixtures/wdk/body.json",
    "summary.json",
  ]) {
    writeFileSync(join(root, path), "");
  }
  assert.deepEqual(scannedPaths(root, ignoredNames("# output\nsummary.json\n.venv/\n")), [
    ".github/workflows/ci.yml",
    "src/veupathdb/testing/fixtures/wdk/body.json",
    "tests/unit/test_a.py",
  ]);
});

const recording = (url, text) =>
  JSON.stringify({ provenance: { site: "plasmodb", url }, body: { description: text } }, null, 2);

test("a recording is read by the address it called", () => {
  const path = "src/veupathdb/testing/fixtures/wdk/search.json";
  assert.deepEqual(
    offencesIn([[path, recording(`https://${host("plasmodb")}/plasmo/service`, "")]]),
    [
      `${path}:4: names the production host ${host("plasmodb")}; a test, a recorder and a default reach the QA sites only`,
    ],
  );
});

test("a production link inside a recorded body passes", () => {
  const text = recording(
    `https://${host("qa", "plasmodb")}/plasmo.qa/service`,
    `<a href="https://${host("orthomcl")}/">OrthoMCL</a>`,
  );
  assert.deepEqual(offencesIn([["src/veupathdb/testing/fixtures/wdk/search.json", text]]), []);
});

test("a body outside the fixture store is read whole", () => {
  const text = recording(
    `https://${host("qa", "plasmodb")}/plasmo.qa/service`,
    `https://${host("plasmodb")}/`,
  );
  assert.equal(offencesIn([["tests/unit/recording.json", text]]).length, 1);
});

test("a fixture that is not a recording is read whole", () => {
  const path = "src/veupathdb/testing/fixtures/wdk/schema-pin.json";
  assert.equal(offencesIn([[path, `{"url": "https://${host("plasmodb")}/"}`]]).length, 1);
});

test("an offence in a recording names the file's own line", () => {
  const path = "src/veupathdb/testing/fixtures/wdk/search.json";
  const text = [
    "{",
    `  "body": {"description": "https://${host("orthomcl")}/ and \\"}\\" text"},`,
    `  "provenance": {`,
    `    "site": "plasmodb",`,
    "",
    `    "url": "https://${host("plasmodb")}/plasmo/service"`,
    "  }",
    "}",
  ].join("\n");
  assert.deepEqual(offencesIn([[path, text]]), [
    `${path}:6: names the production host ${host("plasmodb")}; a test, a recorder and a default reach the QA sites only`,
  ]);
});
