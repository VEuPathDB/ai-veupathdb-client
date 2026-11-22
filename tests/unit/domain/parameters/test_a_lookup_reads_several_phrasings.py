"""A vocabulary lookup for a concept reads several phrasings of it, merges the
entries they match, ranks them, and names each phrasing that matched."""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter

from veupathdb.domain.parameters import (
    VocabOption,
    VocabRead,
    flatten_vocab,
    read_options,
)
from veupathdb.testing import NEEDS_QA_RECORDING, needs_qa_recording
from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk.wdk_parameters import WDKParameter

pytestmark = pytest.mark.skipif(
    needs_qa_recording("wdk/refresh_interpro_domain_pfam_on_dal972.json"),
    reason=NEEDS_QA_RECORDING,
)

# Labels that hold "RNA-binding" with a hyphen, which one substring missed.
_HYPHENATED = ("PF14608", "PF12171")
_RRM = ("PF00076", "PF13893")
_KH = "PF00013"


def _dal972() -> list[VocabOption]:
    params = TypeAdapter(list[WDKParameter]).validate_python(
        load_recorded("refresh_interpro_domain_pfam_on_dal972").json_body()
    )
    [domains] = [p for p in params if p.name == "domain_typeahead"]
    return flatten_vocab(domains.vocabulary)


def _read(*terms: str) -> VocabRead:
    return read_options(_dal972(), terms, request_terms=[])


def _values(options: list[VocabOption]) -> list[str]:
    return [option.value for option in options]


def test_hyphen_and_space_read_alike() -> None:
    spaced = _read("RNA binding")
    hyphenated = _read("RNA-binding")

    assert set(_HYPHENATED) <= set(_values(spaced.options))
    assert _values(spaced.options) == _values(hyphenated.options)


def test_the_words_in_another_order_rank_after_the_phrase() -> None:
    read = _read("RNA binding")

    lookup = read.lookup
    assert lookup is not None
    assert [(m.phrasing, m.reach) for m in lookup.matches] == [
        ("rna binding", "phrase"),
        ("rna binding", "every_word"),
    ]
    phrase, every_word = lookup.matches
    assert len(phrase.values) == 24
    assert len(every_word.values) == 6
    assert _values(read.options) == phrase.values + every_word.values


def test_several_phrasings_of_one_concept_merge() -> None:
    read = _read("RNA binding", "RNA recognition", "KH")

    shown = _values(read.options)
    assert {*_HYPHENATED, *_RRM, _KH} <= set(shown)
    assert len(shown) == len(set(shown))
    lookup = read.lookup
    assert lookup is not None
    assert lookup.terms == ["RNA binding", "RNA recognition", "KH"]
    assert {m.term for m in lookup.matches} == set(lookup.terms)
    assert sum(len(m.values) for m in lookup.matches) == len(shown)


def test_the_words_alone_are_read_when_nothing_else_matches() -> None:
    read = _read("recognition helicase")

    lookup = read.lookup
    assert lookup is not None
    assert [(m.phrasing, m.reach, len(m.values)) for m in lookup.matches] == [
        ("recognition", "word", 7),
        ("helicase", "word", 20),
    ]
    assert set(_RRM) <= set(_values(read.options))


def test_a_word_most_labels_hold_is_not_read_alone() -> None:
    """451 of the 2441 labels hold "protein", so it names no concept alone."""
    read = _read("RNA recognition protein")

    lookup = read.lookup
    assert lookup is not None
    assert [m.phrasing for m in lookup.matches] == ["rna", "recognition"]


def test_a_phrase_that_matches_keeps_its_words_out() -> None:
    """A word alone would pull in every entry that holds "rna"."""
    read = _read("RNA binding")

    assert not set(_RRM) & set(_values(read.options))
