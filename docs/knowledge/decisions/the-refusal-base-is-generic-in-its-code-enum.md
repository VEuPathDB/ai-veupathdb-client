---
type: Decision
title: The refusal base is generic in its code enum
description: VEuPathDBError takes its code enum as a PEP 695 type parameter bound to StrEnum, so a host puts its own error hierarchy under the same base. Widening the parameter to StrEnum was rejected.
tags: [errors, api-surface, typing]
generated: { by: claude-code/opus-5, at: 2026-09-09T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-09T00:00:00Z }
status: stable
---

# What was decided

`VEuPathDBError[C: StrEnum]` takes the code enum as a type parameter. Every refusal
this client raises is a `VEuPathDBError[VEuPathDBErrorCode]`. A host application that
owns its own `StrEnum` of codes declares its base as `VEuPathDBError[ItsOwnEnum]` and
keeps `code` typed as that enum; a handler that takes any refusal annotates
`VEuPathDBError[StrEnum]`.

`code` is assigned as `Final`. That makes the type parameter covariant under both
mypy and pyright, which is what lets a `VEuPathDBError[VEuPathDBErrorCode]` reach a
parameter annotated `VEuPathDBError[StrEnum]`.

# The alternative that was rejected

Widen the constructor to `code: StrEnum` and keep the class non-generic. It is one
line and it type-checks, but it lets a refusal this client raises carry any foreign
enum, and it erases the code's type for every reader: `except VEuPathDBError as exc`
would give `exc.code` the bound rather than the enum that was passed.

A host enum that extends `VEuPathDBErrorCode` was also considered and is impossible:
a `StrEnum` that has members cannot be subclassed.

# What holds it

`tests/unit/test_errors.py` constructs a subclass parametrized with an enum this
package does not own, reads `.code` back, and asserts the static type with
`assert_type`. That file is named in the mypy gate (`uv run mypy --strict src
tests/unit/test_errors.py`) in `.pre-commit-config.yaml` and in CI, because a runtime
assertion alone cannot see a type parameter.
