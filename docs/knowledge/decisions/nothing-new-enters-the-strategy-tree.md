---
type: Decision
title: Nothing new enters the strategy authoring tree
description: src/veupathdb/domain/strategy/ is being emptied, so a module that would fit there stays with its caller until that work lands, even when it imports nothing else.
tags: [architecture, strategy, placement]
generated: { by: claude-code/opus-5, at: 2026-09-08T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-08T00:00:00Z }
status: stable
---

# What was decided

`src/veupathdb/domain/strategy/` takes no new module. Code in the consuming
application that imports only `veupathdb.domain.strategy.{ast, strategy_ast, tree}`
stays where it is, however pure it is.

# Why

That directory is 2894 lines of an authoring model this client should not own, and
an open card in the consuming application exists to move it out
(`pathfinder: docs/knowledge/backlog/re-cut-the-authoring-model-out-of-veupathdb-py.md`,
47 measured edges). Adding to it makes that work larger and later.

# What was rejected

Moving the application's step-push planner (154 lines, pure, no other import) here.
It reads as a clean placement move on its own and is refused for the reason above.
Re-propose it only after the authoring model leaves.
