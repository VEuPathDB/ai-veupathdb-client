# Decisions

Choices with a real alternative, each naming what was rejected and why.

- [An unbound parameter is a parameter, and the criterion that holds it is not](an-unbound-parameter-is-a-parameter.md) - what left `domain/strategy/`, what stayed, and where `OpenSlot` split
- [Only a WDK shape enters the strategy package](only-a-wdk-shape-enters-the-strategy-package.md) - the question a module proposed for `domain/strategy/` answers
- [The refusal base is generic in its code enum](the-refusal-base-is-generic-in-its-code-enum.md) - why `VEuPathDBError` takes its code enum as a type parameter, and why widening to `StrEnum` was rejected
- [The prefix that tags a helper strategy belongs to the deployment](the-internal-strategy-prefix-is-the-deployments.md) - why the reserved strategy-name prefix is a settings field with a neutral default
