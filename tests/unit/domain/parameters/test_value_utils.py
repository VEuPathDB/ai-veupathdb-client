import pytest

from veupathdb.domain.parameters.canonicalize import ParameterCanonicalizer
from veupathdb.domain.parameters.specs import ParamSpecNormalized
from veupathdb.domain.parameters.values import MultiPickValue, SinglePickValue
from veupathdb.domain.parameters.wdk_vocab import WDKVocabTerm
from veupathdb.errors import ValidationError


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
    with pytest.raises(ValidationError, match="takes a single-pick-vocabulary value"):
        _canonicalizer("A", "B").canonicalize(
            {"profileset_generic": MultiPickValue(values=["A", "B"])}
        )
