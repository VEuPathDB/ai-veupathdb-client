---
okf_version: "0.2"
---

# veupathdb-py Knowledge Bundle

What VEuPathDB's WDK and EDA services do, in [Open Knowledge Format](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md) v0.2. Plain markdown with YAML frontmatter, no tooling required.

Every claim here is pinned to the upstream that can prove it wrong, and `scripts/check-wdk-rules.mjs` fails the build when a citation is unpinned, an anchor has moved, or a named test is gone.

## WDK

- [WDK](wdk/) - how WDK works and the rules that must hold

## EDA

- [EDA](eda/) - VEuPathDB's Exploratory Data Analysis platform and how it reaches WDK steps

## Decisions

- [Decisions](decisions/) - choices with a real alternative

## Conventions

- [Conventions](conventions/) - how this bundle is kept honest

## History

- [log.md](log.md) - dated record of significant changes to this bundle
