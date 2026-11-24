from __future__ import annotations

import contextlib
import json
from urllib.parse import unquote

from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from veupathdb.json_types import JSONValue
from veupathdb.testing.wire.models import Exchange
from veupathdb.wdk._http import changes_user_state

Minted = tuple[str, str]

_STEPS = "steps"
_STRATEGIES = "strategies"
_DATASETS = "datasets"
_ANALYSES = "analyses"
_VDI_DATASETS = "vdi-datasets"
_ID_KINDS = {"stepId": _STEPS, "rootStepId": _STEPS, "strategyId": _STRATEGIES}
_USER_KINDS = frozenset({_STEPS, _STRATEGIES, _DATASETS})
_PARAMETERS = "parameters"
_DUPLICATED = "duplicated-step-tree"
_CURRENT = "current"
_WINDOW = 6


class UnmappedIdError(ValueError):
    pass


_ID_TEXT: TypeAdapter[str] = TypeAdapter(
    str, config=ConfigDict(coerce_numbers_to_str=True)
)


class _Minted(BaseModel):
    model_config = ConfigDict(extra="ignore", coerce_numbers_to_str=True)

    id: str | None = None
    analysisId: str | None = None
    datasetId: str | None = None
    stepTree: JSONValue = None

    def minted(self) -> str | None:
        for value in (self.id, self.analysisId, self.datasetId):
            if value is not None:
                return value
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
                _ID_TEXT.validate_python(tree["stepId"]),
                *_step_ids(tree.get("primaryInput")),
                *_step_ids(tree.get("secondaryInput")),
            ]
        case _:
            return []


def segments(path: str) -> list[str]:
    return [unquote(segment).strip() for segment in path.split("/")]


def _owned(parts: list[str]) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for at in range(len(parts)):
        window = parts[at : at + _WINDOW]
        match window:
            case ["eda", "users", _, "analyses", _, _]:
                found.append((at + 5, _ANALYSES))
            case ["vdi", "datasets", _, *_]:
                found.append((at + 2, _VDI_DATASETS))
            case ["users", _, kind, _, *_] if kind in _USER_KINDS:
                found.append((at + 3, kind))
            case _:
                pass
    return found


def _users(parts: list[str]) -> list[str]:
    return [parts[at + 1] for at in range(len(parts) - 1) if parts[at] == "users"]


def _created_kind(parts: list[str]) -> str | None:
    match parts:
        case [*_, "eda", "users", _, "analyses", _]:
            return _ANALYSES
        case [*_, "vdi", "datasets"]:
            return _VDI_DATASETS
        case [*_, "users", _, "strategies", _, "duplicated-step-tree"]:
            return _STEPS
        case [*_, "users", _, "steps", _, "analyses"]:
            return _ANALYSES
        case [*_, "users", _, kind] if kind in _USER_KINDS:
            return kind
        case _:
            return None


class IdMap:
    def __init__(self, user_id: int) -> None:
        self._user = _ID_TEXT.validate_python(user_id)
        self._map: dict[Minted, str] = {}
        self._minted: list[tuple[str, str, str, str]] = []
        self._deleted: set[Minted] = set()

    def learn(self, exchange: Exchange, old: bytes, new: bytes) -> None:
        if exchange.method != "POST" or not exchange.is_write():
            return
        recorded, answered = _parsed(old), _parsed(new)
        parts = segments(exchange.path)
        kind = _created_kind(parts)
        if recorded is None or answered is None or kind is None:
            return
        if parts[-1] == _DUPLICATED:
            collection = "/".join([*parts[:-4], _STEPS])
            pairs = zip(
                _step_ids(recorded.stepTree), _step_ids(answered.stepTree), strict=False
            )
            for old_step, new_step in pairs:
                self._mint(_STEPS, old_step, new_step, exchange.host, collection)
            return
        before, after = recorded.minted(), answered.minted()
        if before is not None and after is not None:
            self._mint(kind, before, after, exchange.host, "/".join(parts))

    def _mint(self, kind: str, before: str, after: str, host: str, at: str) -> None:
        self._map[kind, before] = after
        self._minted.append((kind, after, host, at))

    def _minted_ids(self) -> set[Minted]:
        return {(kind, after) for kind, after, _, _ in self._minted}

    def rewrite_path(self, path: str) -> str:
        parts = segments(path)
        for at, kind in _owned(parts):
            parts[at] = self._map.get((kind, parts[at]), parts[at])
        return "/".join(parts)

    def rewrite_query(self, query: list[tuple[str, str]]) -> list[tuple[str, str]]:
        return [
            (name, self._map.get((_ID_KINDS[name], value), value))
            if name in _ID_KINDS
            else (name, value)
            for name, value in query
        ]

    def _id(self, kind: str, value: JSONValue) -> JSONValue:
        match value:
            case bool():
                return value
            case int() if (kind, _ID_TEXT.validate_python(value)) in self._map:
                return int(self._map[kind, _ID_TEXT.validate_python(value)])
            case str() if (kind, value) in self._map:
                return self._map[kind, value]
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
        if key in _ID_KINDS:
            return self._id(_ID_KINDS[key], item)
        match item:
            case dict() if key == _PARAMETERS:
                return {
                    name: self._id(_DATASETS, given) for name, given in item.items()
                }
            case _:
                return self._rewrite(item)

    def rewrite_body(self, body: str) -> str:
        try:
            parsed: JSONValue = json.loads(body)
        except ValueError:
            return body
        return json.dumps(self._rewrite(parsed), separators=(",", ":"))

    def _named_in(self, value: JSONValue) -> list[Minted]:
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

    def _named_by(self, key: str, item: JSONValue) -> list[Minted]:
        match item:
            case bool() | None:
                return []
            case int() | str() if key in _ID_KINDS:
                return [(_ID_KINDS[key], _ID_TEXT.validate_python(item))]
            case _:
                return self._named_in(item)

    def check(
        self, method: str, path: str, query: list[tuple[str, str]], body: str | None
    ) -> None:
        parts = segments(path)
        others = [u for u in _users(parts) if u not in {self._user, _CURRENT}]
        if others:
            msg = f"{method} {path} acts for user {others[0]}, not the test account"
            raise UnmappedIdError(msg)
        owned = [(kind, parts[at]) for at, kind in _owned(parts)]
        named = owned + [(_ID_KINDS[n], v) for n, v in query if n in _ID_KINDS]
        if body:
            with contextlib.suppress(ValueError):
                named.extend(self._named_in(json.loads(body)))
        minted = self._minted_ids()
        unknown = [
            f"{kind} {found}" for kind, found in named if (kind, found) not in minted
        ]
        if unknown:
            msg = f"{', '.join(unknown)} were minted by no write this refresh sent"
            raise UnmappedIdError(msg)
        creates = method == "POST" and _created_kind(parts) is not None
        if changes_user_state(method, "/".join(parts)) and not creates and not owned:
            msg = (
                f"{method} {path} changes {parts[-1]}, which this refresh never minted"
            )
            raise UnmappedIdError(msg)

    def forget(self, path: str) -> None:
        parts = segments(path)
        self._deleted.update((kind, parts[at]) for at, kind in _owned(parts))

    def live(self) -> list[Minted]:
        return [(k, a) for k, a, _, _ in self._minted if (k, a) not in self._deleted]

    def sweep_paths(self) -> list[tuple[str, str]]:
        return [
            (host, f"{at}/{after}")
            for kind, after, host, at in self._minted
            if (kind, after) not in self._deleted
        ]
