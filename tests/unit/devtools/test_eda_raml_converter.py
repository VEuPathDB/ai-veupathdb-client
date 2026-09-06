"""What the RAML 1.0 type library becomes as JSON Schema draft-07."""

from __future__ import annotations

import pytest
from jsonschema import Draft7Validator
from pydantic import JsonValue, ValidationError

from veupathdb.devtools.eda_schemas import RamlLibrary, RamlType


def _library(types: dict[str, JsonValue]) -> RamlLibrary:
    return RamlLibrary.model_validate({"types": types})


def _definition(types: dict[str, JsonValue], name: str) -> dict[str, JsonValue]:
    document = _library(types).document()
    definitions = document["definitions"]
    assert isinstance(definitions, dict)
    shape = definitions[name]
    assert isinstance(shape, dict)
    return shape


def test_a_bare_string_declaration_is_a_type_expression() -> None:
    declared = RamlType.model_validate("string")
    assert declared.expression == "string"
    assert declared.properties is None


def test_a_declaration_with_properties_and_no_type_is_an_object() -> None:
    declared = RamlType.model_validate({"properties": {"id": "string"}})
    assert declared.expression == "object"


def test_a_facet_the_library_never_uses_is_refused() -> None:
    with pytest.raises(ValidationError, match="uniqueItems"):
        RamlType.model_validate({"type": "string[]", "uniqueItems": True})


def test_a_type_expression_naming_nothing_is_refused() -> None:
    with pytest.raises(KeyError, match="names no library type"):
        _library(
            {"Thing": {"type": "object", "properties": {"x": "Missing"}}}
        ).document()


def test_a_question_mark_on_the_name_makes_a_member_optional() -> None:
    shape = _definition(
        {
            "Thing": {
                "type": "object",
                "properties": {"id": "string", "note?": "string"},
            }
        },
        "Thing",
    )
    assert shape["properties"] == {"id": {"type": "string"}, "note": {"type": "string"}}
    assert shape["required"] == ["id"]


def test_required_false_makes_a_member_optional_too() -> None:
    shape = _definition(
        {
            "Thing": {
                "type": "object",
                "properties": {
                    "id": "string",
                    "note": {"type": "string", "required": False},
                },
            }
        },
        "Thing",
    )
    assert shape["required"] == ["id"]


def test_a_bracket_suffix_is_an_array_of_the_named_type() -> None:
    shape = _definition(
        {
            "Leaf": {"type": "object", "properties": {"id": "string"}},
            "Thing": {"type": "object", "properties": {"leaves": "Leaf[]"}},
        },
        "Thing",
    )
    assert shape["properties"] == {
        "leaves": {"type": "array", "items": {"$ref": "#/definitions/Leaf"}}
    }


def test_a_pipe_is_a_union_of_both_branches() -> None:
    shape = _definition(
        {
            "A": {"type": "object", "properties": {"a": "string"}},
            "B": {"type": "object", "properties": {"b": "string"}},
            "Thing": {"type": "object", "properties": {"either": "A | B"}},
        },
        "Thing",
    )
    assert shape["properties"] == {
        "either": {"anyOf": [{"$ref": "#/definitions/A"}, {"$ref": "#/definitions/B"}]}
    }


def test_an_enum_type_keeps_its_base_type_and_its_values() -> None:
    shape = _definition({"Mode": {"type": "string", "enum": ["a", "b"]}}, "Mode")
    assert shape == {"type": "string", "enum": ["a", "b"]}


def test_inheritance_folds_the_parent_members_into_the_child() -> None:
    shape = _definition(
        {
            "Base": {
                "type": "object",
                "properties": {"id": "string", "note?": "string"},
            },
            "Child": {"type": "Base", "properties": {"extra": "boolean"}},
        },
        "Child",
    )
    assert shape["properties"] == {
        "id": {"type": "string"},
        "note": {"type": "string"},
        "extra": {"type": "boolean"},
    }
    assert shape["required"] == ["extra", "id"]


def test_a_child_that_makes_an_inherited_member_optional_drops_it_from_required() -> (
    None
):
    shape = _definition(
        {
            "Base": {"type": "object", "properties": {"id": "string"}},
            "Child": {"type": "Base", "properties": {"id?": "string"}},
        },
        "Child",
    )
    assert "required" not in shape


def test_a_discriminated_base_is_the_union_of_its_leaves() -> None:
    types: dict[str, JsonValue] = {
        "Shape": {
            "type": "object",
            "discriminator": "kind",
            "properties": {"kind": "string", "id": "string"},
        },
        "Middle": {"type": "Shape", "properties": {"size": "integer"}},
        "Square": {"type": "Middle", "discriminatorValue": "square"},
        "Round": {"type": "Shape", "discriminatorValue": "round"},
    }
    assert _definition(types, "Shape") == {
        "anyOf": [{"$ref": "#/definitions/Round"}, {"$ref": "#/definitions/Square"}]
    }
    square = _definition(types, "Square")
    assert square["properties"] == {
        "kind": {"const": "square"},
        "id": {"type": "string"},
        "size": {"type": "integer"},
    }
    assert square["required"] == ["id", "kind", "size"]


def test_a_wrong_discriminator_value_fails_the_union() -> None:
    types: dict[str, JsonValue] = {
        "Shape": {
            "type": "object",
            "discriminator": "kind",
            "properties": {"kind": "string"},
        },
        "Square": {"type": "Shape", "discriminatorValue": "square"},
        "Round": {"type": "Shape", "discriminatorValue": "round"},
    }
    validator = Draft7Validator(
        {"$ref": "#/definitions/Shape", **_library(types).document()}
    )
    assert validator.is_valid({"kind": "round"})
    assert not validator.is_valid({"kind": "oval"})


def test_additional_properties_false_closes_the_type() -> None:
    types: dict[str, JsonValue] = {
        "Thing": {
            "type": "object",
            "additionalProperties": False,
            "properties": {"id": "string"},
        }
    }
    assert _definition(types, "Thing")["additionalProperties"] is False
    validator = Draft7Validator(
        {"$ref": "#/definitions/Thing", **_library(types).document()}
    )
    assert not validator.is_valid({"id": "x", "extra": 1})


def test_a_type_without_additional_properties_admits_an_unknown_member() -> None:
    types: dict[str, JsonValue] = {
        "Thing": {"type": "object", "properties": {"id": "string"}}
    }
    validator = Draft7Validator(
        {"$ref": "#/definitions/Thing", **_library(types).document()}
    )
    assert validator.is_valid({"id": "x", "extra": 1})


def test_the_any_name_property_types_every_key_of_the_map() -> None:
    types: dict[str, JsonValue] = {
        "Entry": {"type": "object", "properties": {"n": "integer"}},
        "Map": {
            "type": "object",
            "additionalProperties": False,
            "properties": {"//": "Entry"},
        },
    }
    assert _definition(types, "Map")["additionalProperties"] == {
        "$ref": "#/definitions/Entry"
    }
    validator = Draft7Validator(
        {"$ref": "#/definitions/Map", **_library(types).document()}
    )
    assert validator.is_valid({"DS_1": {"n": 1}, "DS_2": {"n": 2}})
    assert not validator.is_valid({"DS_1": {"n": "one"}})


def test_a_narrower_property_pattern_is_refused_rather_than_approximated() -> None:
    types: dict[str, JsonValue] = {
        "Entry": {"type": "object", "properties": {"n": "integer"}},
        "Map": {"type": "object", "properties": {"/^DS_/": "Entry"}},
    }
    with pytest.raises(KeyError, match="the converter does not read"):
        _library(types).document()


def test_string_bounds_survive_the_conversion() -> None:
    types: dict[str, JsonValue] = {
        "HashId": {
            "type": "string",
            "minLength": 4,
            "maxLength": 4,
            "pattern": "^[a-f]{4}$",
        }
    }
    assert _definition(types, "HashId") == {
        "type": "string",
        "minLength": 4,
        "maxLength": 4,
        "pattern": "^[a-f]{4}$",
    }


def test_a_top_level_array_type_carries_its_item_type() -> None:
    types: dict[str, JsonValue] = {
        "Leaf": {"type": "object", "properties": {"id": "string"}},
        "Leaves": {"type": "array", "items": "Leaf"},
    }
    assert _definition(types, "Leaves") == {
        "type": "array",
        "items": {"$ref": "#/definitions/Leaf"},
    }


def test_a_recursive_type_resolves_through_a_reference() -> None:
    types: dict[str, JsonValue] = {
        "Node": {
            "type": "object",
            "properties": {"id": "string", "children": "Node[]"},
        }
    }
    validator = Draft7Validator(
        {"$ref": "#/definitions/Node", **_library(types).document()}
    )
    assert validator.is_valid({"id": "a", "children": [{"id": "b", "children": []}]})
    assert not validator.is_valid({"id": "a", "children": [{"children": []}]})


def test_ancestors_and_subtypes_are_the_two_directions_of_one_chain() -> None:
    library = _library(
        {
            "Base": {"type": "object", "properties": {"id": "string"}},
            "Middle": {"type": "Base"},
            "Leaf": {"type": "Middle", "discriminatorValue": "leaf"},
        }
    )
    assert library.ancestors("Leaf") == ("Middle", "Base")
    assert library.subtypes("Base") == ("Leaf", "Middle")
    assert library.leaf_subtypes("Base") == ("Leaf",)
