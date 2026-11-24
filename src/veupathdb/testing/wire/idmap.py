from __future__ import annotations

import contextlib
import json
import re

from pydantic import BaseModel, ConfigDict, ValidationError

from veupathdb.json_types import JSONValue
from veupathdb.testing.wire.models import Exchange

_ID_KEYS = frozenset({"stepId", "rootStepId", "strategyId"})
_PARAMETERS = "parameters"
_OWNED = re.compile(r"/users/[^/]+/(steps|strategies|datasets)/(\d+)")
_DUPLICATED = "duplicated-step-tree"


class UnmappedIdError(ValueError):
    pass


class _Minted(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int | str | None = None
    analysisId: str | None = None
    datasetId: str | None = None
    stepTree: JSONValue = None

    def minted(self) -> str | None:
        for value in (self.id, self.analysisId, self.datasetId):
            if value is not None:
                return str(value)
        return None


def _parsed(body: bytes) -> _Minted | None:
    try:
        return _Minted.model_validate_json(body)
    except ValidationError:
        return None


def _step_ids(tree: JSONValue) -> list[str]:
    match tree:
        case dict() if "stepId" in tree:
            return [
                str(tree["stepId"]),
                *_step_ids(tree.get("primaryInput")),
                *_step_ids(tree.get("secondaryInput")),
            ]
        case _:
            return []


class IdMap:
    def __init__(self) -> None:
        self._map: dict[str, str] = {}
        self._minted: list[tuple[str, str, str]] = []
        self._deleted: set[str] = set()

    def learn(self, exchange: Exchange, old: bytes, new: bytes) -> None:
        if exchange.method != "POST" or not exchange.is_write():
            return
        recorded, answered = _parsed(old), _parsed(new)
        if recorded is None or answered is None:
            return
        collection, _, kind = exchange.path.rpartition("/")
        if kind == _DUPLICATED:
            users = collection.rsplit("/strategies/", 1)[0]
            pairs = zip(
                _step_ids(recorded.stepTree), _step_ids(answered.stepTree), strict=False
            )
            for old_step, new_step in pairs:
                self._mint(
                    old_step, new_step, "steps", f"https://{exchange.host}{users}/steps"
                )
            return
        before, after = recorded.minted(), answered.minted()
        if before is not None and after is not None:
            self._mint(before, after, kind, f"https://{exchange.host}{exchange.path}")

    def _mint(self, before: str, after: str, kind: str, collection: str) -> None:
        self._map[before] = after
        self._minted.append((kind, after, collection))

    def rewrite_path(self, path: str) -> str:
        return "/".join(self._map.get(segment, segment) for segment in path.split("/"))

    def _id(self, value: JSONValue) -> JSONValue:
        match value:
            case bool():
                return value
            case int() if str(value) in self._map:
                return int(self._map[str(value)])
            case str() if value in self._map:
                return self._map[value]
            case _:
                return value

    def _rewrite(self, value: JSONValue) -> JSONValue:
        match value:
            case dict():
                return {key: self._entry(key, item) for key, item in value.items()}
            case list():
                return [self._rewrite(item) for item in value]
            case _:
                return value

    def _entry(self, key: str, item: JSONValue) -> JSONValue:
        if key in _ID_KEYS:
            return self._id(item)
        match item:
            case dict() if key == _PARAMETERS:
                return {name: self._id(given) for name, given in item.items()}
            case _:
                return self._rewrite(item)

    def rewrite_body(self, body: str) -> str:
        try:
            parsed: JSONValue = json.loads(body)
        except ValueError:
            return body
        return json.dumps(self._rewrite(parsed), separators=(",", ":"))

    def _known(self) -> set[str]:
        return {after for _, after, _ in self._minted}

    def _named_in(self, value: JSONValue) -> list[str]:
        match value:
            case dict():
                return [
                    found
                    for key, item in value.items()
                    for found in self._named_by(key, item)
                ]
            case list():
                return [found for item in value for found in self._named_in(item)]
            case _:
                return []

    def _named_by(self, key: str, item: JSONValue) -> list[str]:
        match item:
            case bool() | None:
                return []
            case int() | str() if key in _ID_KEYS:
                return [str(item)]
            case _:
                return self._named_in(item)

    def check(self, path: str, body: str | None) -> None:
        named = [match.group(2) for match in _OWNED.finditer(path)]
        if body:
            with contextlib.suppress(ValueError):
                named.extend(self._named_in(json.loads(body)))
        unknown = [found for found in named if found not in self._known()]
        if unknown:
            msg = f"ids {', '.join(unknown)} were minted by no write this refresh sent"
            raise UnmappedIdError(msg)

    def forget(self, path: str) -> None:
        self._deleted.add(path.rstrip("/").rsplit("/", 1)[-1])

    def live(self) -> list[tuple[str, str]]:
        return [(k, a) for k, a, _ in self._minted if a not in self._deleted]

    def sweep_urls(self) -> list[str]:
        return [f"{c}/{a}" for _, a, c in self._minted if a not in self._deleted]
