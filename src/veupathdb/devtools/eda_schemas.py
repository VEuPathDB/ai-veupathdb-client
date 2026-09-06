"""The pinned service-eda RAML types, and the recorded EDA bodies measured against them.

``schema/library.raml`` is the merged RAML 1.0 type library the EDA service
publishes. ``vendor`` copies it and the one file it includes at the commit
``schema-pin.json`` names; ``verify`` converts the types it declares to JSON
Schema draft-07 and validates every recorded fixture, without a network or a
credential.

Usage::

    python -m veupathdb.devtools.eda_schemas types
    python -m veupathdb.devtools.eda_schemas verify
    python -m veupathdb.devtools.eda_schemas vendor

The converter covers the constructs this library uses and refuses anything
else, so a facet the service adds is a failure here rather than a silent gap.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import hashlib
import json
import sys
from collections.abc import Awaitable, Callable, Iterable, Iterator
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any, Literal, Self
from urllib.parse import urljoin

import httpx
import yaml
from jsonschema import Draft7Validator
from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from veupathdb.devtools.pins import VendoredPin, pin_drift
from veupathdb.testing.eda_fixtures import FIXTURE_DIR, SCHEMA_PIN_FILE, UPSTREAM_DIR

LIBRARY_FILE = "library.raml"

_VENDOR_TIMEOUT_SECONDS = 30.0
_INCLUDE_TAG = "!include"
_ANY_PROPERTY_NAME = "//"

_PRIMITIVES: dict[str, dict[str, JsonValue]] = {
    "any": {},
    "array": {"type": "array"},
    "boolean": {"type": "boolean"},
    "date-only": {"type": "string"},
    "datetime": {"type": "string"},
    "datetime-only": {"type": "string"},
    "integer": {"type": "integer"},
    "number": {"type": "number"},
    "object": {"type": "object"},
    "string": {"type": "string"},
}
"""The RAML built-in types this library names, and the draft-07 they become.

``format`` is dropped: draft-07 treats an unknown format as an annotation, and
``int64`` against ``int32`` is not a constraint a recorded body can fail.
"""


class RamlType(BaseModel):
    """One RAML 1.0 type declaration, with every facet this library uses.

    ``extra="forbid"`` is the gate on the converter's scope: a facet this
    library does not use fails the parse instead of being dropped.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    expression: str = Field(alias="type")
    properties: dict[str, RamlType] | None = None
    items: RamlType | None = None
    enum: tuple[JsonValue, ...] | None = None
    required: bool | None = None
    additional_properties: bool | None = Field(
        default=None, alias="additionalProperties"
    )
    discriminator: str | None = None
    discriminator_value: str | None = Field(default=None, alias="discriminatorValue")
    format: str | None = None
    minimum: float | None = None
    min_items: int | None = Field(default=None, alias="minItems")
    max_items: int | None = Field(default=None, alias="maxItems")
    min_length: int | None = Field(default=None, alias="minLength")
    max_length: int | None = Field(default=None, alias="maxLength")
    pattern: str | None = None
    default: JsonValue = None
    description: str | None = None
    display_name: str | None = Field(default=None, alias="displayName")

    @model_validator(mode="before")
    @classmethod
    def _a_declaration_is_a_type_expression_or_a_facet_map(cls, value: Any) -> Any:
        """RAML writes a plain type expression where a facet map would go."""
        match value:
            case str():
                return {"type": value}
            case {"type": _}:
                return value
            case {**facets}:
                shape = "object" if "properties" in facets else "string"
                return {**facets, "type": shape}
            case _:
                return value

    @property
    def optional(self) -> bool:
        """``required: false``, the long form of a ``?`` on the property name."""
        return self.required is False


class RamlLibrary(BaseModel):
    """The ``types:`` map of a RAML library, resolved against itself."""

    model_config = ConfigDict(frozen=True)

    types: dict[str, RamlType]

    def ancestors(self, name: str) -> tuple[str, ...]:
        """The library types *name* inherits from, nearest first."""
        chain: list[str] = []
        current = name
        while (parent := self.types[current].expression) in self.types:
            chain.append(parent)
            current = parent
        return tuple(chain)

    def subtypes(self, name: str) -> tuple[str, ...]:
        """Every transitive subtype of *name*."""
        found: list[str] = []
        pending = [name]
        while pending:
            parent = pending.pop()
            children = [
                child
                for child, declared in self.types.items()
                if declared.expression == parent
            ]
            found.extend(children)
            pending.extend(children)
        return tuple(sorted(found))

    def leaf_subtypes(self, name: str) -> tuple[str, ...]:
        """Every transitive subtype of *name* that names a discriminator value."""
        return tuple(
            child
            for child in self.subtypes(name)
            if self.types[child].discriminator_value is not None
        )

    def document(self) -> dict[str, JsonValue]:
        """The whole library as one draft-07 document of ``definitions``."""
        definitions: dict[str, JsonValue] = {
            name: self._definition(name) for name in sorted(self.types)
        }
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "definitions": definitions,
        }

    def _expression(self, expression: str) -> dict[str, JsonValue]:
        """The schema of a RAML type expression: a name, an array, or a union."""
        text = expression.strip()
        if "|" in text:
            branches: list[JsonValue] = [
                self._expression(part) for part in text.split("|")
            ]
            return {"anyOf": branches}
        if text.endswith("[]"):
            return {"type": "array", "items": self._expression(text[:-2])}
        if text in self.types:
            return {"$ref": f"#/definitions/{text}"}
        if text in _PRIMITIVES:
            return dict(_PRIMITIVES[text])
        msg = f"{expression!r} names no library type and no RAML built-in"
        raise KeyError(msg)

    def _facets(self, declared: RamlType) -> dict[str, JsonValue]:
        """The scalar and array bounds a declaration carries, as draft-07 keys."""
        bounds: dict[str, JsonValue] = {
            "minimum": declared.minimum,
            "minItems": declared.min_items,
            "maxItems": declared.max_items,
            "minLength": declared.min_length,
            "maxLength": declared.max_length,
            "pattern": declared.pattern,
        }
        return {key: value for key, value in bounds.items() if value is not None}

    def _member(self, declared: RamlType) -> dict[str, JsonValue]:
        """The schema of one property or item declaration."""
        if declared.enum is not None:
            return {"enum": list(declared.enum)}
        schema = self._expression(declared.expression)
        if declared.items is not None:
            schema["items"] = self._member(declared.items)
        if declared.properties is not None:
            schema |= self._object(declared)
        return schema | self._facets(declared)

    def _object(self, declared: RamlType) -> dict[str, JsonValue]:
        """The members of one declaration, without inheritance.

        ``//`` is RAML's any-name property, which draft-07 spells as a schema
        under ``additionalProperties``. A narrower pattern is refused rather
        than approximated.
        """
        properties: dict[str, JsonValue] = {}
        required: list[str] = []
        anything: JsonValue | None = None
        for key, member in (declared.properties or {}).items():
            schema = self._member(member)
            if key.startswith("/"):
                if key != _ANY_PROPERTY_NAME:
                    msg = f"{key!r} is a property pattern the converter does not read"
                    raise KeyError(msg)
                anything = schema
                continue
            optional = key.endswith("?") or member.optional
            name = key.removesuffix("?")
            properties[name] = schema
            if not optional:
                required.append(name)
        shape: dict[str, JsonValue] = {"type": "object", "properties": properties}
        if anything is not None:
            shape["additionalProperties"] = anything
        elif declared.additional_properties is False:
            shape["additionalProperties"] = False
        if required:
            shape["required"] = _names(required)
        return shape

    def _merged_object(self, name: str) -> dict[str, JsonValue]:
        """One named type's object schema, with every inherited member folded in."""
        properties: dict[str, JsonValue] = {}
        required: set[str] = set()
        anything: JsonValue | None = None
        for level in reversed((name, *self.ancestors(name))):
            shape = self._object(self.types[level])
            own = _as_map(shape.get("properties"))
            properties |= own
            required = (required - set(own)) | set(_as_list(shape.get("required")))
            if "additionalProperties" in shape:
                anything = shape["additionalProperties"]
        value = self.types[name].discriminator_value
        if value is not None:
            properties[self._discriminator_of(name)] = {"const": value}
        merged: dict[str, JsonValue] = {"type": "object", "properties": properties}
        if required:
            merged["required"] = _names(required)
        if anything is not None:
            merged["additionalProperties"] = anything
        return merged

    def _discriminator_of(self, name: str) -> str:
        """The property the nearest discriminated ancestor keys its subtypes by."""
        for ancestor in self.ancestors(name):
            discriminator = self.types[ancestor].discriminator
            if discriminator is not None:
                return discriminator
        msg = f"{name} names a discriminator value under no discriminated type"
        raise KeyError(msg)

    def _definition(self, name: str) -> dict[str, JsonValue]:
        """One named type as draft-07."""
        declared = self.types[name]
        if declared.enum is not None:
            choices: dict[str, JsonValue] = {"enum": list(declared.enum)}
            return self._expression(declared.expression) | choices
        if declared.discriminator is not None:
            leaves = self.leaf_subtypes(name)
            if leaves:
                branches: list[JsonValue] = [
                    {"$ref": f"#/definitions/{leaf}"} for leaf in leaves
                ]
                return {"anyOf": branches}
        if declared.properties is None and declared.expression not in self.types:
            schema = self._expression(declared.expression)
            if declared.items is not None:
                schema["items"] = self._member(declared.items)
            return schema | self._facets(declared)
        return self._merged_object(name)


def _as_map(node: JsonValue) -> dict[str, JsonValue]:
    """The mapping at *node*, or an empty one when the key was absent."""
    match node:
        case dict():
            return dict(node)
        case _:
            return {}


def _as_list(node: JsonValue) -> list[str]:
    """The list of names at *node*, or an empty one when the key was absent."""
    match node:
        case list():
            return [str(item) for item in node]
        case _:
            return []


def _names(values: Iterable[str]) -> list[JsonValue]:
    """Member names in order, as the JSON values a schema list holds."""
    ordered: list[JsonValue] = []
    ordered.extend(sorted(values))
    return ordered


class VendoredRaml(VendoredPin):
    """The service-eda commit the vendored RAML was copied from.

    ``includes`` maps each absolute ``!include`` URL to the copy that answers
    it, so the library resolves offline.
    """

    includes: dict[str, str] = Field(default_factory=dict)


def load_pin() -> VendoredRaml:
    """The pin the vendored RAML answers to."""
    return VendoredRaml.model_validate_json(SCHEMA_PIN_FILE.read_text())


def raml_pin_drift(pin: VendoredRaml) -> tuple[str, ...]:
    """Every vendored RAML that is missing, edited, absent from the pin, or unresolved."""
    on_disk = (path.name for path in UPSTREAM_DIR.glob("*.raml"))
    problems = pin_drift(pin, UPSTREAM_DIR, on_disk)
    problems.extend(
        f"{url}: included but not vendored"
        for url, relative in sorted(pin.includes.items())
        if relative not in pin.files
    )
    return tuple(problems)


def _parse_raml(relative: str, includes: dict[str, str]) -> Any:
    """Parse one vendored RAML file, with each ``!include`` inlined from the pin.

    An included file is written back as JSON, which is a YAML flow mapping, so
    the whole library parses with ``safe_load`` and no custom tag handling.
    """
    text = (UPSTREAM_DIR / relative).read_text()
    for url in _include_urls(text):
        included = _parse_raml(includes[url], includes)
        text = text.replace(f"{_INCLUDE_TAG} {url}", json.dumps(included))
    return yaml.safe_load(text)


@dataclass(frozen=True)
class PinnedLibrary:
    """The vendored library, as declared and as the wire answers to it."""

    library: RamlLibrary
    declared: dict[str, JsonValue]
    wire: dict[str, JsonValue]


@cache
def pinned() -> PinnedLibrary:
    """The vendored type library, parsed once and resolved against itself."""
    library = RamlLibrary.model_validate(_parse_raml(LIBRARY_FILE, load_pin().includes))
    declared = library.document()
    return PinnedLibrary(library, declared, _wire_document(library, declared))


def reload() -> None:
    """Drop the parsed library, after the vendored bytes change."""
    pinned.cache_clear()


def _errors(
    document: dict[str, JsonValue], type_name: str, body: JsonValue
) -> tuple[str, ...]:
    """Every draft-07 error *document* reports for *body* read as *type_name*."""
    if type_name not in _as_map(document["definitions"]):
        msg = f"{type_name} is not a type the pinned library declares"
        raise KeyError(msg)
    validator = Draft7Validator({"$ref": f"#/definitions/{type_name}", **document})
    return tuple(
        sorted(
            f"{'/'.join(str(part) for part in error.absolute_path) or '<root>'}: "
            f"{error.message}"
            for error in validator.iter_errors(body)
        )
    )


def verify_body(type_name: str, body: JsonValue) -> tuple[str, ...]:
    """Every draft-07 error the pinned RAML type reports for *body*."""
    return _errors(pinned().declared, type_name, body)


type DefectKind = Literal[
    "renamed-on-the-wire", "required-but-absent", "undeclared-on-the-wire"
]


class SpecDefect(BaseModel):
    """One member where the pinned RAML and the measured wire disagree.

    ``renamed`` gives the name the service sends instead, and the declared
    member keeps its type under that name. A ``required-but-absent`` member
    leaves the type's ``required`` list. An ``undeclared-on-the-wire`` member is
    one the service sends and the RAML never declares; nothing is relaxed for
    it, because a RAML type admits unknown members unless it closes itself.
    """

    model_config = ConfigDict(frozen=True)

    raml_type: str
    member: str
    kind: DefectKind
    renamed: str | None = None
    measured: str
    records: str

    @model_validator(mode="after")
    def _only_a_rename_names_a_wire_member(self) -> Self:
        if (self.kind == "renamed-on-the-wire") != (self.renamed is not None):
            msg = f"{self.raml_type}.{self.member}: only a rename names a wire member"
            raise ValueError(msg)
        return self

    def holds(self, definition: dict[str, JsonValue]) -> bool:
        """Whether *definition* still shows the divergence this entry records."""
        properties = _as_map(definition.get("properties"))
        if self.kind == "undeclared-on-the-wire":
            return bool(properties) and self.member not in properties
        return self.member in properties

    def applied(self, definition: dict[str, JsonValue]) -> JsonValue:
        """*definition* bent to what the service sends, or left alone."""
        if not self.holds(definition) or self.kind == "undeclared-on-the-wire":
            return definition
        properties = _as_map(definition.get("properties"))
        required = _as_list(definition.get("required"))
        if self.renamed is not None:
            properties[self.renamed] = properties.pop(self.member)
            required = [
                self.renamed if name == self.member else name for name in required
            ]
        else:
            required = [name for name in required if name != self.member]
        return {**definition, "properties": properties, "required": _names(required)}


SPEC_DEFECTS: tuple[SpecDefect, ...] = (
    SpecDefect(
        raml_type="API_Variable",
        member="isCategory",
        kind="required-but-absent",
        measured="absent on 13 of 13 variables of STUDY_53f554ec6a, 2026-09-04",
        records="docs/knowledge/eda/rest-surface.md",
    ),
    SpecDefect(
        raml_type="API_StudyOverview",
        member="shortDisplayName",
        kind="required-but-absent",
        measured="absent on 14 of 757 studies, 2026-09-04",
        records="docs/knowledge/eda/rest-surface.md",
    ),
    SpecDefect(
        raml_type="API_StudyOverview",
        member="description",
        kind="required-but-absent",
        measured="absent on 2 of the 52 studies the fixture keeps, 2026-08-28",
        records="docs/knowledge/eda/rest-surface.md",
    ),
    SpecDefect(
        raml_type="DatasetPermissionEntry",
        member="shortDisplayName",
        kind="required-but-absent",
        measured="absent on 22 of 878 perDataset entries, 2026-09-04",
        records="docs/knowledge/eda/rest-surface.md",
    ),
    SpecDefect(
        raml_type="DatasetPermissionEntry",
        member="description",
        kind="required-but-absent",
        measured="absent on 2 of the 61 entries the fixture keeps, 2026-08-28",
        records="docs/knowledge/eda/rest-surface.md",
    ),
    SpecDefect(
        raml_type="DifferentialExpressionPoint",
        member="pointId",
        kind="renamed-on-the-wire",
        renamed="pointID",
        measured="pointID on 5511 of 5511 rows, pointId on 0, 2026-09-04",
        records="docs/knowledge/eda/rest-surface.md",
    ),
    SpecDefect(
        raml_type="DifferentialExpressionPoint",
        member="pValue",
        kind="required-but-absent",
        measured="absent on 1 of 5511 rows, 2026-09-04",
        records="docs/knowledge/eda/rest-surface.md",
    ),
    SpecDefect(
        raml_type="DifferentialExpressionPoint",
        member="adjustedPValue",
        kind="required-but-absent",
        measured="absent on the same 1 of 5511 rows, 2026-09-04",
        records="docs/knowledge/eda/rest-surface.md",
    ),
    SpecDefect(
        raml_type="DifferentialExpressionStatsResponse",
        member="pValueFloor",
        kind="undeclared-on-the-wire",
        measured="sent on every response, declared nowhere, 2026-09-04",
        records="docs/knowledge/eda/rest-surface.md",
    ),
    SpecDefect(
        raml_type="DifferentialExpressionStatsResponse",
        member="adjustedPValueFloor",
        kind="undeclared-on-the-wire",
        measured="sent on every response, declared nowhere, 2026-09-04",
        records="docs/knowledge/eda/rest-surface.md",
    ),
)
"""Where the pinned RAML describes a service that does not exist.

Every entry is a defect in the specification: PathFinder's own models already
match the wire at each of these ten members. The gate applies them so that
whatever it still reports is drift.
"""


def _wire_document(
    library: RamlLibrary, document: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    """*document* with every recorded specification defect applied.

    A defect on a discriminated base reaches every subtype, because a subtype's
    own definition is where the inherited member ends up. An entry the pinned
    library no longer contradicts is a failure: the spec was fixed, and the
    entry and its knowledge line must go.
    """
    definitions = _as_map(document["definitions"])
    for defect in SPEC_DEFECTS:
        names = (defect.raml_type, *library.subtypes(defect.raml_type))
        declared = {name: _as_map(definitions[name]) for name in names}
        if not any(defect.holds(shape) for shape in declared.values()):
            msg = (
                f"{defect.raml_type}.{defect.member}: the pinned library no longer "
                f"diverges here; drop the entry and the line in {defect.records}"
            )
            raise KeyError(msg)
        definitions |= {name: defect.applied(shape) for name, shape in declared.items()}
    return {**document, "definitions": definitions}


def verify_wire_body(type_name: str, body: JsonValue) -> tuple[str, ...]:
    """Every draft-07 error left after the recorded specification defects."""
    return _errors(pinned().wire, type_name, body)


class FixtureBinding(BaseModel):
    """The RAML type the endpoint behind one recorded fixture answers with."""

    model_config = ConfigDict(frozen=True)

    fixture: str
    raml_type: str
    endpoint: str

    @property
    def file(self) -> Path:
        return FIXTURE_DIR / f"{self.fixture}.json"


BINDINGS: tuple[FixtureBinding, ...] = (
    FixtureBinding(
        fixture="studies_list",
        raml_type="StudiesGetResponse",
        endpoint="GET /studies",
    ),
    FixtureBinding(
        fixture="study_detail_de",
        raml_type="StudyIdGetResponse",
        endpoint="GET /studies/{study-id}",
    ),
    FixtureBinding(
        fixture="study_detail_phenotype",
        raml_type="StudyIdGetResponse",
        endpoint="GET /studies/{study-id}",
    ),
    FixtureBinding(
        fixture="count_unfiltered",
        raml_type="EntityCountPostResponse",
        endpoint="POST /studies/{study-id}/entities/{entity-id}/count",
    ),
    FixtureBinding(
        fixture="count_filtered",
        raml_type="EntityCountPostResponse",
        endpoint="POST /studies/{study-id}/entities/{entity-id}/count",
    ),
    FixtureBinding(
        fixture="distribution_categorical",
        raml_type="VariableDistributionPostResponse",
        endpoint=(
            "POST /studies/{study-id}/entities/{entity-id}"
            "/variables/{variable-id}/distribution"
        ),
    ),
    FixtureBinding(
        fixture="compute_job_lookup",
        raml_type="JobResponse",
        endpoint="POST /computes/differentialexpression",
    ),
    FixtureBinding(
        fixture="volcano_statistics",
        raml_type="DifferentialExpressionStatsResponse",
        endpoint="POST /computes/differentialexpression/statistics",
    ),
    FixtureBinding(
        fixture="permissions",
        raml_type="PermissionsGetResponse",
        endpoint="GET /permissions",
    ),
)
"""Which RAML type each recorded body answers to, read from ``api.raml``.

The endpoint column is the RAML resource path, so a moved binding is one
lookup in the same file rather than a guess.
"""


class BindingCheck(BaseModel):
    """One recorded body measured against the type its endpoint returns."""

    model_config = ConfigDict(frozen=True)

    fixture: str
    raml_type: str
    errors: tuple[str, ...] = ()


def binding_checks() -> tuple[BindingCheck, ...]:
    """One check per binding, over the wire document."""
    return tuple(
        BindingCheck(
            fixture=binding.fixture,
            raml_type=binding.raml_type,
            errors=verify_wire_body(
                binding.raml_type, json.loads(binding.file.read_text())
            ),
        )
        for binding in BINDINGS
    )


type RamlFetcher = Callable[[str], Awaitable[bytes]]
"""Answers one absolute RAML URL with its bytes, or raises."""


def _include_urls(text: str) -> Iterator[str]:
    """Every absolute URL a ``!include`` in *text* names."""
    for line in text.splitlines():
        _, tag, rest = line.partition(_INCLUDE_TAG)
        if tag and rest.strip():
            yield rest.strip()


async def vendor_raml(fetch: RamlFetcher) -> int:
    """Re-download the library and its includes at the commit the pin names.

    The pin is rewritten only when a byte changed, so ``vendored_at`` dates the
    content and not the run.
    """
    pin = load_pin()
    UPSTREAM_DIR.mkdir(parents=True, exist_ok=True)
    library = await fetch(urljoin(pin.base_url, LIBRARY_FILE))
    (UPSTREAM_DIR / LIBRARY_FILE).write_bytes(library)
    digests = {LIBRARY_FILE: hashlib.sha256(library).hexdigest()}
    includes: dict[str, str] = {}
    for url in _include_urls(library.decode()):
        relative = url.rsplit("/", 1)[-1]
        content = await fetch(url)
        (UPSTREAM_DIR / relative).write_bytes(content)
        digests[relative] = hashlib.sha256(content).hexdigest()
        includes[url] = relative
    for path in sorted(UPSTREAM_DIR.glob("*.raml")):
        if path.name not in digests:
            path.unlink()
    if digests != pin.files or includes != pin.includes:
        refreshed = pin.model_copy(
            update={
                "files": dict(sorted(digests.items())),
                "includes": dict(sorted(includes.items())),
                "vendored_at": datetime.datetime.now(tz=datetime.UTC)
                .date()
                .isoformat(),
            }
        )
        SCHEMA_PIN_FILE.write_text(refreshed.model_dump_json(indent=2) + "\n")
    reload()
    return len(digests)


async def _vendor_from_upstream() -> int:
    """Vendor the library over HTTP from the repository the pin names."""
    async with httpx.AsyncClient(timeout=_VENDOR_TIMEOUT_SECONDS) as client:

        async def fetch(url: str) -> bytes:
            response = await client.get(url)
            response.raise_for_status()
            return response.content

        return await vendor_raml(fetch)


def reached_types(names: tuple[str, ...]) -> frozenset[str]:
    """Every definition the schemas of *names* reach through a ``$ref``."""
    definitions = _as_map(pinned().declared["definitions"])
    found: set[str] = set()
    pending = list(names)
    while pending:
        name = pending.pop()
        if name in found:
            continue
        found.add(name)
        pending.extend(
            ref.removeprefix("#/definitions/") for ref in _refs(definitions.get(name))
        )
    return frozenset(found)


def _refs(node: JsonValue) -> Iterator[str]:
    """Every ``$ref`` value under *node*."""
    match node:
        case dict():
            for key, value in node.items():
                match value:
                    case str(ref) if key == "$ref":
                        yield ref
                    case _:
                        yield from _refs(value)
        case list():
            for item in node:
                yield from _refs(item)
        case _:
            return


def _list_types() -> None:
    library = pinned().library
    for binding in BINDINGS:
        print(f"{binding.fixture:26} {binding.raml_type:36} {binding.endpoint}")
    for defect in SPEC_DEFECTS:
        member = f"{defect.raml_type}.{defect.member}"
        print(f"{member:52} {defect.kind:22} {defect.measured}")
    print(f"{len(library.types)} type(s) in the pinned library")


def _verify() -> int:
    """Print one line per fixture and return the process exit code."""
    pin = load_pin()
    drift = raml_pin_drift(pin)
    for problem in drift:
        print(f"schema pin: {problem}")

    checks = binding_checks()
    failed = [check for check in checks if check.errors]
    for check in checks:
        state = "FAIL" if check.errors else "PASS"
        print(f"{check.fixture:26} {state:5} {check.raml_type}")
        for error in check.errors:
            print(f"    {error}")

    bound = tuple(sorted({check.raml_type for check in checks}))
    print(
        f"{len(checks)} fixture(s), {len(failed)} failed; "
        f"{len(bound)} bound type(s) reaching {len(reached_types(bound))} "
        f"of {len(pinned().library.types)} pinned; "
        f"{len(SPEC_DEFECTS)} recorded spec defect(s); "
        f"{len(pin.files)} file(s) pinned at {pin.repo}@{pin.sha[:12]}"
    )
    return 1 if failed or drift else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eda_schemas", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("types", help="show which RAML type each fixture answers to")
    sub.add_parser("verify", help="check every fixture against the pinned RAML")
    sub.add_parser("vendor", help="re-download the library at the pinned commit")
    args = parser.parse_args(argv)

    if args.command == "types":
        _list_types()
        return 0
    if args.command == "verify":
        return _verify()
    count = asyncio.run(_vendor_from_upstream())
    print(f"vendored {count} file(s) into {UPSTREAM_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "BINDINGS",
    "LIBRARY_FILE",
    "SPEC_DEFECTS",
    "BindingCheck",
    "DefectKind",
    "FixtureBinding",
    "PinnedLibrary",
    "RamlFetcher",
    "RamlLibrary",
    "RamlType",
    "SpecDefect",
    "VendoredRaml",
    "binding_checks",
    "load_pin",
    "main",
    "pinned",
    "raml_pin_drift",
    "reached_types",
    "reload",
    "vendor_raml",
    "verify_body",
    "verify_wire_body",
]
