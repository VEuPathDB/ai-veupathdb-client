from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, Field

from veupathdb.json_types import JSONValue

Compared = tuple[str, int, int, bytes, bytes]
_COUNTS = (
    ("estimatedSize",),
    ("meta", "totalCount"),
    ("meta", "displayTotalCount"),
    ("displayTotalCount",),
)


class DriftRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    cassette: str
    statuses: list[str] = Field(default_factory=list)
    shapes: list[str] = Field(default_factory=list)
    counts: list[str] = Field(default_factory=list)

    def changed(self) -> bool:
        return bool(self.statuses or self.shapes or self.counts)

    def reshaped(self) -> bool:
        return bool(self.statuses or self.shapes)


def _json(body: bytes) -> JSONValue:
    try:
        parsed: JSONValue = json.loads(body) if body else None
    except ValueError:
        return None
    return parsed


def _shape(value: JSONValue, at: str = "$") -> dict[str, str]:
    match value:
        case dict():
            shape = {at: "object"}
            for key, item in value.items():
                shape.update(_shape(item, f"{at}.{key}"))
            return shape
        case list():
            shape = {at: "array"}
            for item in value:
                shape.update(_shape(item, f"{at}[]"))
            return shape
        case None:
            return {at: "null"}
        case _:
            return {at: type(value).__name__}


def _count(value: JSONValue, path: tuple[str, ...]) -> JSONValue:
    for name in path:
        match value:
            case dict():
                value = value.get(name)
            case _:
                return None
    return value


def _counts(value: JSONValue) -> dict[str, JSONValue]:
    counts = {".".join(path): _count(value, path) for path in _COUNTS}
    match value:
        case {"records": list() as records}:
            counts["records"] = len(records)
        case _:
            pass
    return {name: count for name, count in counts.items() if count is not None}


def compare(cassette: str, compared: list[Compared]) -> DriftRow:
    statuses: list[str] = []
    shapes: list[str] = []
    counts: list[str] = []
    for label, old_status, new_status, old_body, new_body in compared:
        if old_status != new_status:
            statuses.append(f"{label} {old_status} -> {new_status}")
        old, new = _json(old_body), _json(new_body)
        before, after = _shape(old), _shape(new)
        shapes.extend(f"{label} removed {p}" for p in before if p not in after)
        shapes.extend(f"{label} added {p}" for p in after if p not in before)
        shapes.extend(
            f"{label} changed {p} {before[p]} -> {after[p]}"
            for p in before
            if p in after and before[p] != after[p]
        )
        old_counts, new_counts = _counts(old), _counts(new)
        counts.extend(
            f"{label} {name} {old_counts[name]} -> {new_counts[name]}"
            for name in old_counts
            if name in new_counts and old_counts[name] != new_counts[name]
        )
    return DriftRow(cassette=cassette, statuses=statuses, shapes=shapes, counts=counts)


def render_report(
    rows: list[DriftRow],
    builds: dict[str, tuple[int | None, int | None]],
    errors: list[str],
) -> str:
    reshaped = [row for row in rows if row.reshaped()]
    counted = [row for row in rows if row.counts and not row.reshaped()]
    unchanged = len(rows) - len(reshaped) - len(counted)
    lines = [
        "# WDK refresh",
        "",
        (
            f"{len(rows)} tests: {unchanged} unchanged, {len(counted)} with count"
            f" changes only, {len(reshaped)} with shape or status changes."
        ),
        "",
        "## Builds",
        *(
            f"- {host}: build {old} -> {new}"
            for host, (old, new) in sorted(builds.items())
        ),
    ]
    if errors:
        lines += ["", "## Refresh errors", *(f"- {error}" for error in errors)]
    if reshaped:
        lines += ["", "## Shape or status changes"]
        for row in reshaped:
            lines += ["", f"### {row.cassette}"]
            lines += [
                f"- {change}" for change in [*row.statuses, *row.shapes, *row.counts]
            ]
    if counted:
        lines += ["", "## Count changes only", "", "| test | change |", "|---|---|"]
        lines += [
            f"| {row.cassette} | {change} |" for row in counted for change in row.counts
        ]
    return "\n".join(lines) + "\n"
