#!/usr/bin/env node
/**
 * Conformance check for the WDK rule bundle.
 *
 * A WDK rule is admissible only because upstream can falsify it. This script
 * is what makes that true in practice: it fails the build when a citation is
 * unpinned, an anchor has moved, or a test named as enforcing a rule no longer
 * exists. Without it the rules are a wiki, and a wiki gets believed after it
 * stops being true.
 *
 * Rule blocks are parsed only under `rules/`, but the pinning requirement runs
 * over every markdown file in the bundle, because the convention admits WDK
 * material on the promise that all of it is pinned, not just the rules.
 *
 * Every check here is written to fail loudly rather than pass vacuously: an
 * empty rules directory, a heading at the wrong level, and a citation of a
 * withdrawn rule are all errors, because each of them is a way for the bundle
 * to look green while asserting nothing.
 */
import { readFileSync, readdirSync, statSync, existsSync } from "node:fs";
import { join, resolve, relative, basename } from "node:path";

const CLASSES = new Set(["HARD", "SILENT", "CONTRACT"]);
const NAMESPACES = "STRAT|STEP|SEARCH|PARAM|VOCAB|FILTER|ANS|VALID|AUTH|HTTP|MAP|SITE";
const ID_RE = new RegExp(`^WDK-(?:${NAMESPACES})-\\d{3}$`);
const CITE_RE = new RegExp(`WDK-(?:${NAMESPACES})-\\d{3}`, "g");
const GITHUB_HOST_RE = /^https:\/\/(?:github\.com|raw\.githubusercontent\.com)\//;
const PINNED_BLOB_RE =
  /^https:\/\/github\.com\/[^\s/]+\/[^\s/]+\/(?:blob|tree|raw|blame)\/[0-9a-f]{40}\//;
const PINNED_RAW_RE =
  /^https:\/\/raw\.githubusercontent\.com\/[^\s/]+\/[^\s/]+\/[0-9a-f]{40}\//;
const STATUS_RE = /^(UNENFORCED|WITHDRAWN - .+|(?:ENFORCED|PARTIAL) by (.+))$/;
const PROSE_DIRS = ["model", "rest", "pathfinder"];
const GITHUB_URL_RE =
  /https:\/\/(?:github\.com|raw\.githubusercontent\.com)\/[^\s)<>"'`\]]+/g;

function markdownIn(dir) {
  if (!existsSync(dir)) return [];
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) return markdownIn(full);
    return name.endsWith(".md") ? [full] : [];
  });
}

/** Split a rule file into `### ` blocks, dropping any preamble. */
function ruleBlocks(text) {
  return text
    .split(/^### /m)
    .slice(1)
    .map((chunk) => {
      const [heading, ...rest] = chunk.split("\n");
      const fields = {};
      for (const line of rest) {
        const match = /^- ([a-z]+): (.+)$/.exec(line.trim());
        if (match) fields[match[1]] = match[2].trim();
      }
      return { heading: heading.trim(), fields };
    });
}

/** `path::Class::name` (pytest) or `path > describe > name` (vitest). */
function splitTestId(testId) {
  const separator = testId.includes("::") ? "::" : testId.includes(" > ") ? " > " : null;
  if (separator === null) return { path: testId.trim(), selector: null };
  const parts = testId.split(separator).map((part) => part.trim());
  return { path: parts[0], selector: parts[parts.length - 1] };
}

/** Only the first colon separates path from symbol, so `Foo::bar` survives. */
function splitAnchor(anchor) {
  const colon = anchor.indexOf(":");
  if (colon === -1) return { path: anchor.trim(), symbol: null };
  return { path: anchor.slice(0, colon).trim(), symbol: anchor.slice(colon + 1).trim() };
}

/** Word-bounded, so renaming `Step` to `WdkStep` does not keep the anchor green. */
function mentions(text, symbol) {
  const escaped = symbol.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`(?<![\\w$])${escaped}(?![\\w$])`).test(text);
}

function isPinned(url) {
  return PINNED_BLOB_RE.test(url) || PINNED_RAW_RE.test(url);
}

/** Sentence punctuation abutting a bare URL is not part of it. */
function trimUrl(url) {
  return url.replace(/[.,;:]+$/, "");
}

export function collect(root, bundle = root, tally = null) {
  const errors = [];
  const defined = new Set();
  const withdrawn = new Map();
  const seenAt = new Map();
  const reportedUnpinned = new Set();
  const rulesDir = join(bundle, "rules");
  const ruleFiles = markdownIn(rulesDir);

  if (ruleFiles.length === 0) {
    errors.push(`no rule files found under ${rulesDir}`);
    return errors;
  }

  for (const file of ruleFiles) {
    const rel = relative(root, file);
    if (basename(file) === "index.md") continue;

    const blocks = ruleBlocks(readFileSync(file, "utf8"));
    if (blocks.length === 0) {
      errors.push(`${rel}: contains no rules (a rule is a "### " heading)`);
      continue;
    }

    for (const { heading, fields } of blocks) {
      const [id, ...titleParts] = heading.split(" - ");
      const title = titleParts.join(" - ");

      if (!ID_RE.test(id)) {
        errors.push(`${rel}: malformed rule id "${id}"`);
        continue;
      }
      if (seenAt.has(id)) {
        errors.push(`${rel}: duplicate rule id ${id}, already defined in ${seenAt.get(id)}`);
        continue;
      }
      seenAt.set(id, rel);

      if (title.trim() === "") errors.push(`${rel}: ${id} has no statement after the id`);

      const status = fields.status ?? "";
      const statusMatch = STATUS_RE.exec(status);
      if (statusMatch === null) {
        errors.push(`${rel}: ${id} has a malformed status -> "${status}"`);
      }

      // An unenforced rule is admissible, and only while it says why no test
      // can hold it. Without that, the column fills with silence.
      if (status === "UNENFORCED" && (fields.reason ?? "") === "") {
        errors.push(
          `${rel}: ${id} is UNENFORCED and gives no reason; add "- reason: ..."`,
        );
      }
      tally?.count(id, rel, fields.class ?? "", status, fields.reason ?? "");

      // A withdrawn rule is exempt from class, upstream and anchor: the code it
      // cited is gone, which is why it was withdrawn. It is not added to
      // `defined`, so prose still citing it is reported rather than tolerated.
      if (status.startsWith("WITHDRAWN")) {
        if (statusMatch !== null) withdrawn.set(id, rel);
        continue;
      }
      defined.add(id);

      if (!CLASSES.has(fields.class ?? "")) {
        errors.push(`${rel}: ${id} class must be one of HARD, SILENT, CONTRACT (got "${fields.class ?? ""}")`);
      }

      const upstream = fields.upstream ?? "";
      if (upstream === "") {
        errors.push(`${rel}: ${id} has no upstream evidence`);
      } else if (GITHUB_HOST_RE.test(upstream) && !isPinned(upstream)) {
        errors.push(`${rel}: ${id} upstream github link is not pinned to a 40-character sha`);
        reportedUnpinned.add(`${rel}\t${trimUrl(upstream)}`);
      }

      const anchor = fields.anchor ?? "";
      if (anchor === "") {
        errors.push(`${rel}: ${id} has no anchor`);
      } else {
        const { path: anchorPath, symbol } = splitAnchor(anchor);
        const anchorFull = join(root, anchorPath);
        if (!existsSync(anchorFull)) {
          errors.push(`${rel}: ${id} anchor file does not exist -> ${anchorPath}`);
        } else if (!statSync(anchorFull).isFile()) {
          errors.push(`${rel}: ${id} anchor is a directory, not a file -> ${anchorPath}`);
        } else if (symbol && !mentions(readFileSync(anchorFull, "utf8"), symbol)) {
          errors.push(`${rel}: ${id} anchor symbol not found in ${anchorPath} -> ${symbol}`);
        }
      }

      if (statusMatch?.[2]) {
        const { path, selector } = splitTestId(statusMatch[2]);
        const testFull = join(root, path);
        if (!existsSync(testFull)) {
          errors.push(`${rel}: ${id} named test not found -> ${path}`);
        } else if (!statSync(testFull).isFile()) {
          errors.push(`${rel}: ${id} named test is a directory, not a file -> ${path}`);
        } else if (selector && !mentions(readFileSync(testFull, "utf8"), selector)) {
          errors.push(`${rel}: ${id} named test not found in ${path} -> ${selector}`);
        }
      }
    }
  }

  for (const dir of PROSE_DIRS) {
    for (const file of markdownIn(join(bundle, dir))) {
      const rel = relative(root, file);
      const text = readFileSync(file, "utf8");
      for (const cited of new Set(text.match(CITE_RE) ?? [])) {
        if (withdrawn.has(cited)) {
          errors.push(`${rel}: cites withdrawn rule ${cited}, withdrawn in ${withdrawn.get(cited)}`);
        } else if (!defined.has(cited)) {
          errors.push(`${rel}: cites undefined rule ${cited}`);
        }
      }
    }
  }

  // The convention admits WDK material because upstream can falsify it, and it
  // demands pinned evidence of every WDK concept, not only of the rules. A
  // `blob/main` link in an explainer drifts exactly as silently as one in a
  // rule block, so the pinning requirement covers the whole bundle. Anything
  // already reported against a rule's `upstream` field is skipped, so a single
  // bad citation is a single error.
  for (const file of markdownIn(bundle)) {
    const rel = relative(root, file);
    const urls = new Set(
      (readFileSync(file, "utf8").match(GITHUB_URL_RE) ?? []).map(trimUrl),
    );
    for (const url of urls) {
      if (isPinned(url)) continue;
      if (reportedUnpinned.has(`${rel}\t${url}`)) continue;
      errors.push(`${rel}: unpinned github citation -> ${url}`);
    }
  }

  return errors;
}

/** Counts what the bundle claims about itself, so a run reports its coverage. */
export class Coverage {
  constructor() {
    this.enforced = 0;
    this.partial = 0;
    this.withdrawn = 0;
    this.unenforced = [];
  }

  count(id, file, ruleClass, status, reason) {
    if (status.startsWith("WITHDRAWN")) this.withdrawn += 1;
    else if (status.startsWith("ENFORCED")) this.enforced += 1;
    else if (status.startsWith("PARTIAL")) this.partial += 1;
    else this.unenforced.push({ id, file, ruleClass, reason });
  }

  get total() {
    return this.enforced + this.partial + this.withdrawn + this.unenforced.length;
  }
}

const invokedDirectly = process.argv[1]?.endsWith("check-wdk-rules.mjs");
if (invokedDirectly) {
  const repoRoot = resolve(process.argv[2] ?? ".");
  const coverage = new Coverage();
  const errors = collect(repoRoot, join(repoRoot, "docs/knowledge/wdk"), coverage);
  if (errors.length > 0) {
    console.error("check-wdk-rules: FAILED");
    for (const error of errors) console.error(`  ${error}`);
    process.exit(1);
  }
  console.log("check-wdk-rules: all rules conform (0 violations)");
  console.log(
    `  ${coverage.total} rules: ${coverage.enforced} enforced, ` +
      `${coverage.partial} partial, ${coverage.unenforced.length} unenforced, ` +
      `${coverage.withdrawn} withdrawn`,
  );
  for (const rule of coverage.unenforced) {
    console.log(`  UNENFORCED ${rule.id} (${rule.ruleClass}): ${rule.reason}`);
  }
}
