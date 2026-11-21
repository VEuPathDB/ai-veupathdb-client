from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol


class DeclaredParam(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def dependent_params(self) -> Sequence[str]: ...

    @property
    def site_set(self) -> bool: ...


def _inverted(
    names: Sequence[str], parents: Mapping[str, tuple[str, ...]]
) -> dict[str, tuple[str, ...]]:
    children: dict[str, list[str]] = {}
    for child in names:
        for parent in parents.get(child, ()):
            children.setdefault(parent, []).append(child)
    return {parent: tuple(listed) for parent, listed in children.items()}


def _wire_parents(params: Sequence[DeclaredParam]) -> dict[str, tuple[str, ...]]:
    declared = {param.name for param in params}
    parents: dict[str, list[str]] = {}
    for param in params:
        for child in dict.fromkeys(param.dependent_params):
            if child in declared:
                parents.setdefault(child, []).append(param.name)
    return {
        param.name: tuple(parents[param.name])
        for param in params
        if param.name in parents
    }


def _stated_parents_of(
    name: str,
    wire_parents: Mapping[str, tuple[str, ...]],
    site_set: Mapping[str, bool],
) -> tuple[str, ...]:
    stated: list[str] = []
    seen = {name}
    pending = list(reversed(wire_parents.get(name, ())))
    while pending:
        parent = pending.pop()
        if parent in seen:
            continue
        seen.add(parent)
        if site_set[parent]:
            pending.extend(reversed(wire_parents.get(parent, ())))
        else:
            stated.append(parent)
    return tuple(stated)


def _kahn_order(
    names: Sequence[str],
    wire_parents: Mapping[str, tuple[str, ...]],
    wire_children: Mapping[str, tuple[str, ...]],
) -> tuple[str, ...]:
    in_degree = {name: len(wire_parents.get(name, ())) for name in names}
    queue = [name for name in names if in_degree[name] == 0]
    order: list[str] = []
    while queue:
        node = queue.pop(0)
        order.append(node)
        for child in wire_children.get(node, ()):
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)
    placed = set(order)
    return (*order, *(name for name in names if name not in placed))


@dataclass(frozen=True)
class ParamGraph:
    wire_parents: Mapping[str, tuple[str, ...]]
    wire_children: Mapping[str, tuple[str, ...]]
    stated_parents: Mapping[str, tuple[str, ...]]
    stated_children: Mapping[str, tuple[str, ...]]
    fill_order: tuple[str, ...]

    @classmethod
    def of(cls, params: Sequence[DeclaredParam]) -> ParamGraph:
        names = [param.name for param in params]
        site_set = {param.name: param.site_set for param in params}
        wire_parents = _wire_parents(params)
        wire_children = _inverted(names, wire_parents)
        stated_parents = {
            name: stated
            for name in names
            if not site_set[name]
            and (stated := _stated_parents_of(name, wire_parents, site_set))
        }
        return cls(
            wire_parents=wire_parents,
            wire_children=wire_children,
            stated_parents=stated_parents,
            stated_children=_inverted(names, stated_parents),
            fill_order=_kahn_order(names, wire_parents, wire_children),
        )
