# Decisions

Choices with a real alternative, each naming what was rejected and why.

- [Nothing new enters the strategy authoring tree](nothing-new-enters-the-strategy-tree.md) - why a pure planner that fits `domain/strategy/` stays in the consuming application
- [The refusal base is generic in its code enum](the-refusal-base-is-generic-in-its-code-enum.md) - why `VEuPathDBError` takes its code enum as a type parameter, and why widening to `StrEnum` was rejected
- [The prefix that tags a helper strategy belongs to the deployment](the-internal-strategy-prefix-is-the-deployments.md) - why the reserved strategy-name prefix is a settings field with a neutral default
