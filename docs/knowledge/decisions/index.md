# Decisions

Choices with a real alternative, each naming what was rejected and why.

- [An unbound parameter is a parameter, and the criterion that holds it is not](an-unbound-parameter-is-a-parameter.md) - what left `domain/strategy/`, what stayed, and where `OpenSlot` split
- [Only a WDK shape enters the strategy package](only-a-wdk-shape-enters-the-strategy-package.md) - the question a module proposed for `domain/strategy/` answers
- [The refusal base is generic in its code enum](the-refusal-base-is-generic-in-its-code-enum.md) - why `VEuPathDBError` takes its code enum as a type parameter, and why widening to `StrEnum` was rejected
- [The prefix that tags a helper strategy belongs to the deployment](the-internal-strategy-prefix-is-the-deployments.md) - why the reserved strategy-name prefix is a settings field with a neutral default
- [The published surface is a list of packages, checked in name by name](the-published-surface-is-a-list-of-packages.md) - the sixteen surfaces, why eight of them stay modules, and the consumer import lines that change
- [Installing a settings source drops what the old one built](installing-a-settings-source-drops-what-the-old-one-built.md) - why a source may be installed at any point, and why an ordering note was not enough
- [The schema readers are an extra, not a dependency group](the-schema-readers-are-an-extra-not-a-group.md) - why `veupathdb.devtools` ships with a `devtools` extra rather than leaving the wheel
- [A rule is proven in this checkout, or it says so](a-rule-is-proven-in-this-checkout.md) - why no rule status names another repository's test
