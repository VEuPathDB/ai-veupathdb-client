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
_WIRE_CALLS = frozenset(
    {"to_wire", "wire_map", "dumps", "encode_wdk_params", "model_dump", "str"}
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


def _inner(node: ast.expr) -> list[ast.expr]:
    match node:
        case (
            ast.Call(func=ast.Name(id="len"), args=[inner])
            | ast.Call(func=ast.Attribute(attr="get", value=inner))
            | ast.Subscript(value=inner)
            | ast.SetComp(elt=inner)
            | ast.ListComp(elt=inner)
            | ast.GeneratorExp(elt=inner)
            | ast.DictComp(value=inner)
        ):
            return [inner]
        case ast.Set(elts=elts) | ast.List(elts=elts) | ast.Tuple(elts=elts):
            return list(elts)
        case _:
            return []


def _wire(node: ast.expr, wires: frozenset[str]) -> str | None:
    match node:
        case ast.Name(id=name) if name in wires:
            return f"the wire text held in {name}"
        case ast.Call() if _called(node) in _WIRE_CALLS:
            return f"the text of {_called(node)}()"
        case _:
            return next(
                (
                    reason
                    for inner in _inner(node)
                    if (reason := _wire(inner, wires)) is not None
                ),
                None,
            )


def _wire_names(scope: ast.AST) -> frozenset[str]:
    names: set[str] = set()
    for node in ast.walk(scope):
        match node:
            case (
                ast.Assign(targets=[ast.Name(id=name)], value=value)
                | ast.AnnAssign(target=ast.Name(id=name), value=ast.expr() as value)
            ) if _wire(value, frozenset(names)) is not None:
                names.add(name)
            case _:
                pass
    return frozenset(names)


def _counted(node: ast.expr) -> bool:
    match node:
        case ast.Call(
            func=ast.Name(id="len"),
            args=[ast.SetComp() | ast.ListComp() | ast.Set() | ast.GeneratorExp()],
        ):
            return True
        case _:
            return False


def _reason(compare: ast.Compare, wires: frozenset[str]) -> str | None:
    for op, right in zip(compare.ops, compare.comparators, strict=True):
        match op:
            case ast.Eq() | ast.NotEq():
                sides = [compare.left, right]
            case ast.In() | ast.NotIn():
                sides = [compare.left]
            case _:
                sides = [side for side in (compare.left, right) if _counted(side)]
        for side in sides:
            reason = _wire(side, wires)
            if reason is not None:
                return f"compares {reason}"
    return None


def _scoped(tree: ast.Module) -> Iterator[tuple[str, frozenset[str], ast.Compare]]:
    def walk(
        node: ast.AST, scope: str, wires: frozenset[str]
    ) -> Iterator[tuple[str, frozenset[str], ast.Compare]]:
        for child in ast.iter_child_nodes(node):
            match child:
                case (
                    ast.FunctionDef(name=name)
                    | ast.AsyncFunctionDef(name=name)
                    | ast.ClassDef(name=name)
                ):
                    yield from walk(
                        child,
                        f"{scope}.{name}" if scope else name,
                        _wire_names(child),
                    )
                case ast.Compare():
                    yield scope or "<module>", wires, child
                    yield from walk(child, scope, wires)
                case _:
                    yield from walk(child, scope, wires)

    return walk(tree, "", _wire_names(tree))


def findings_in(path: Path, relative: str) -> list[Finding]:
    tree = ast.parse(path.read_text(), filename=str(path))
    found: list[Finding] = []
    for scope, wires, compare in _scoped(tree):
        reason = _reason(compare, wires)
        if reason is not None:
            found.append(Finding(relative, scope, compare.lineno, reason))
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
            "compare the values with =="
        )
    for key in sorted(stale):
        print(f"{args.allow}: {key} is allowed but compares nothing")
    if unallowed(found, allowed) or stale:
        return 1
    print(f"param-equality: {len(found)} allowed text comparison(s), no other")
    return 0


if __name__ == "__main__":
    sys.exit(main())
