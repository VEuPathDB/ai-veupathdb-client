---
type: Decision
title: Only a WDK shape enters the strategy package
description: domain/strategy holds the shapes WDK states, so a module proposed for it is admitted on whether WDK states that shape; the blanket refusal that rejected the consumer's step-push planner is withdrawn with the authoring model it protected.
tags: [architecture, strategy, placement]
generated: { by: claude-code/opus-5, at: 2026-09-08T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-10T00:00:00Z }
status: stable
---

# What was decided

A module joins `src/veupathdb/domain/strategy/` when WDK itself states the shape it
holds: the step tree, the keyed step map, the traversal over both, the combine
operators, the validation bundle, the organism scope rule. A module that states a
goal, a criterion, a session, an edit history or a user requirement belongs to the
application that authors strategies; see
[an unbound parameter is a parameter](an-unbound-parameter-is-a-parameter.md).

The test beside the package asserts the module set, so a module that joins it names
itself in the same change.

# Why

A client of WDK is believed about WDK. Every distribution that installs
`veupathdb-py` reads what is in this package as the VEuPathDB contract, so a module
admitted wrongly is copied into a second client as a fact about WDK, and correcting
it then costs a coordinated release of every distribution that pinned it. Every
module here that stated something else had to be measured, argued and moved once its
consumer needed to change it alone. The admission question is the cheap one: point at
what WDK states.

# What was rejected

**Refusing every module that fits `domain/strategy/`.** That was the rule while the
whole package was leaving, and it refused the application's step-push planner, 154
lines, pure, importing only `ast`, `strategy_ast` and `tree`. Those three state WDK
shapes and stay, so the refusal no longer follows and the planner is judged on
whether a step push is a WDK fact. `strategy_ast` is the one hybrid left: it carries
the persisted graph beside the wire tree because `veupathdb-mcp` types a payload
`StrategyAst` on it, and it is the last module of that kind.

**Admitting on "does a WDK client need it" instead of "does WDK state it".** Every
module that just left passes that test: a client that authors strategies needs a
session, an edit algebra and a build lifecycle. The test admits anything a caller
finds convenient, and each admission is then read by the next client as WDK's own
word. `StepStatus` and `step_status` are the measured case: four states saying
whether a step reached WDK yet, derived from `StrategyStep` and a validation bundle,
useful to a client and stated by no WDK endpoint. They left, and `veupathdb-mcp`
named neither.
