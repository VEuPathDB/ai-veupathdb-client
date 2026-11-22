from __future__ import annotations

import argparse
import ast
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

EQUALITY_MODULES = frozenset(
    {
        "veupathdb/domain/parameters/value_equality.py",
        "veupathdb/domain/parameters/values.py",
    }
)
_WIRE_CALLS = frozenset({"to_wire", "wire_map", "dumps", "encode_wdk_params"})
_PARAM_MAPS = frozenset({"parameters", "params", "param_values", "resolved_params"})
_VALUE_KINDS = frozenset(
    {
        "StringValue",
        "NumberValue",
        "NumberRangeValue",
        "DateValue",
        "DateRangeValue",
        "TimestampValue",
        "SinglePickValue",
        "MultiPickValue",
        "FilterValue",
        "HeldValue",
        "InputDatasetValue",
        "InputStepValue",
    }
)


@dataclass(frozen=True)
class Finding:
    path: str
    scope: str
    line: int
    reason: str

    @property
    def key(self) -> str:
        return f"{self.path}:{self.scope}"


def _called(node: ast.expr) -> str | None:
    match node:
        case ast.Call(func=ast.Attribute(attr=name)) | ast.Call(func=ast.Name(id=name)):
            return name
        case _:
            return None


def _param_map(node: ast.expr) -> bool:
    match node:
        case ast.Attribute(attr=name):
            return name in _PARAM_MAPS
        case ast.Subscript(value=inner):
            return _param_map(inner)
        case ast.Call(func=ast.Name(id="dict"), args=[inner]):
            return _param_map(inner)
        case _:
            return False


def _reason(node: ast.expr) -> str | None:
    called = _called(node)
    if called in _WIRE_CALLS:
        return f"compares the text of {called}()"
    if called in _VALUE_KINDS:
        return f"compares a {called} with =="
    if _param_map(node):
        return "compares a parameter map or value with =="
    return None


def _scoped(tree: ast.Module) -> Iterator[tuple[str, ast.Compare]]:
    def walk(node: ast.AST, scope: str) -> Iterator[tuple[str, ast.Compare]]:
        for child in ast.iter_child_nodes(node):
            match child:
                case (
                    ast.FunctionDef(name=name)
                    | ast.AsyncFunctionDef(name=name)
                    | (ast.ClassDef(name=name))
                ):
                    yield from walk(child, f"{scope}.{name}" if scope else name)
                case ast.Compare():
                    yield scope or "<module>", child
                    yield from walk(child, scope)
                case _:
                    yield from walk(child, scope)

    return walk(tree, "")


def findings_in(path: Path, relative: str) -> list[Finding]:
    tree = ast.parse(path.read_text(), filename=str(path))
    found: list[Finding] = []
    for scope, compare in _scoped(tree):
        if not any(isinstance(op, ast.Eq | ast.NotEq) for op in compare.ops):
            continue
        for operand in [compare.left, *compare.comparators]:
            reason = _reason(operand)
            if reason is not None:
                found.append(Finding(relative, scope, compare.lineno, reason))
                break
    return found


def scan(roots: Sequence[Path], base: Path) -> list[Finding]:
    found: list[Finding] = []
    for root in roots:
        for path in sorted(root.rglob("*.py")):
            relative = path.relative_to(base).as_posix()
            if any(relative.endswith(module) for module in EQUALITY_MODULES):
                continue
            if "/tests/" in f"/{relative}" or "/.venv/" in f"/{relative}":
                continue
            found.extend(findings_in(path, relative))
    return found


def unallowed(found: Sequence[Finding], allowed: frozenset[str]) -> list[Finding]:
    return [finding for finding in found if finding.key not in allowed]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m veupathdb.devtools.param_equality")
    parser.add_argument("roots", nargs="+", type=Path)
    parser.add_argument("--allow", type=Path, required=True)
    parser.add_argument("--base", type=Path, default=Path())
    args = parser.parse_args(argv)
    allowed = frozenset(
        line.strip() for line in args.allow.read_text().splitlines() if line.strip()
    )
    found = scan(args.roots, args.base)
    stale = allowed - {finding.key for finding in found}
    for finding in unallowed(found, allowed):
        print(
            f"{finding.path}:{finding.line} {finding.scope}: {finding.reason}; "
            "compare through veupathdb.domain.parameters.same_param_value"
        )
    for key in sorted(stale):
        print(f"{args.allow}: {key} is allowed but compares nothing")
    if unallowed(found, allowed) or stale:
        return 1
    print(f"param-equality: {len(found)} allowed text comparison(s), no other")
    return 0


if __name__ == "__main__":
    sys.exit(main())
