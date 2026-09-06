import pytest

from veupathdb.domain.parameters.canonicalize import ParameterCanonicalizer
from veupathdb.domain.parameters.specs import ParamSpecNormalized
from veupathdb.domain.parameters.value_utils import decode_single_value
from veupathdb.domain.parameters.values import MultiPickValue, SinglePickValue
from veupathdb.domain.parameters.wdk_vocab import WDKVocabTerm
from veupathdb.errors import ValidationError


def test_comma_containing_value_is_one_value() -> None:
    value = "P. falciparum 3D7 asexual stages, salivary gland sporozoite"
    assert decode_single_value(value, "profileset_generic") == [value]


def test_explicit_json_array_string_is_multiple() -> None:
    assert decode_single_value('["A", "B"]', "x") == ["A", "B"]


def test_list_input_is_multiple() -> None:
    assert decode_single_value(["A", "B"], "x") == ["A", "B"]


def test_plain_value_is_one() -> None:
    assert decode_single_value("Gametocyte V", "x") == ["Gametocyte V"]


def test_empty_is_no_values() -> None:
    assert decode_single_value("", "x") == []


def _canonicalizer(*terms: str) -> ParameterCanonicalizer:
    spec = ParamSpecNormalized(
        name="profileset_generic",
        param_type="single-pick-vocabulary",
        vocabulary=[WDKVocabTerm((term, term, None)) for term in terms],
    )
    return ParameterCanonicalizer({"profileset_generic": spec})


def test_a_comma_containing_vocab_value_stays_one_value() -> None:
    value = "P. falciparum 3D7 asexual stages, salivary gland sporozoite"

    canonical = _canonicalizer(value).canonicalize(
        {"profileset_generic": SinglePickValue(value=value)}
    )

    assert canonical["profileset_generic"] == SinglePickValue(value=value)


def test_a_genuine_multiple_is_refused_for_a_single_pick() -> None:
    with pytest.raises(ValidationError, match="only one value"):
        _canonicalizer("A", "B").canonicalize(
            {"profileset_generic": MultiPickValue(values=["A", "B"])}
        )
