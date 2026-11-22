"""Vocabulary entries: exact matching and the parent term the third element
carries."""

from __future__ import annotations

from pydantic import TypeAdapter

from veupathdb.domain.parameters.wdk_vocab import (
    VocabOption,
    WDKVocabTerm,
    match_exact_option,
)
from veupathdb.wdk.wdk_parameters import WDKEnumParam

_PFAM = [
    VocabOption(value="PF00069 : Pkinase", display="PF00069 : Pkinase"),
    VocabOption(value="PF00569 : ZZ", display="PF00569 : ZZ"),
    VocabOption(value="PF00169 : PH", display="PF00169 : PH"),
]

_EC = [
    VocabOption(value="2.7.1.1", display="2.7.1.1"),
    VocabOption(value="2.7.11.1", display="2.7.11.1"),
]

# The head of ``GenesByOrthologPattern``'s phyletic term vocabulary.
_TERM_MAP: list[list[str | None]] = [
    ["BACT", "Bacteria", None],
    ["FIRM", "Firmicutes", "BACT"],
    ["bant", "Bacillus anthracis", "FIRM"],
    ["bsub", "Bacillus subtilis subsp. subtilis str. 168", "FIRM"],
    ["EUKA", "Eukaryota", None],
    ["MAMM", "Mammalia", "EUKA"],
    ["hsap", "Homo sapiens REF", "MAMM"],
]


def _matched(options: list[VocabOption], value: str) -> str:
    """The term the value names, empty when it names none."""
    return match_exact_option(options, value) or ""


class TestMatchExactOption:
    """A value is matched by term, by label, or by its leading accession."""

    def test_a_term_matches_itself(self) -> None:
        assert _matched(_PFAM, "PF00069 : Pkinase") == "PF00069 : Pkinase"

    def test_an_accession_names_the_one_entry_that_carries_it(self) -> None:
        assert _matched(_PFAM, "PF00069") == "PF00069 : Pkinase"

    def test_an_accession_is_matched_ignoring_case(self) -> None:
        assert _matched(_PFAM, "pf00069") == "PF00069 : Pkinase"

    def test_a_prefix_of_an_accession_matches_nothing(self) -> None:
        assert _matched(_EC, "2.7") == ""

    def test_a_value_holding_a_colon_is_not_split(self) -> None:
        options = [VocabOption(value="GO:0016301", display="kinase activity")]

        assert _matched(options, "GO:0016301") == "GO:0016301"

    def test_an_accession_two_entries_share_matches_nothing(self) -> None:
        options = [
            VocabOption(value="PF00069 : Pkinase", display="PF00069 : Pkinase"),
            VocabOption(value="PF00069 : Pkinase_2", display="PF00069 : Pkinase_2"),
        ]

        assert _matched(options, "PF00069") == ""

    def test_an_exact_label_wins_over_another_entrys_accession(self) -> None:
        options = [
            VocabOption(value="PF00069 : Pkinase", display="PF00069 : Pkinase"),
            VocabOption(value="IPR000719", display="PF00069"),
        ]

        assert _matched(options, "PF00069") == "IPR000719"

    def test_a_leading_word_that_is_not_an_accession_matches_nothing(self) -> None:
        options = [
            VocabOption(value="Plasmodium falciparum 3D7", display="P. falciparum")
        ]

        assert _matched(options, "Plasmodium") == ""


class TestTheThirdElementIsTheParentTerm:
    def test_a_nested_entry_parses_and_states_its_parent(self) -> None:
        entry = WDKVocabTerm(("FIRM", "Firmicutes", "BACT"))

        assert (entry.term, entry.display, entry.parent) == (
            "FIRM",
            "Firmicutes",
            "BACT",
        )

    def test_a_root_entry_has_no_parent(self) -> None:
        entry = WDKVocabTerm(("BACT", "Bacteria", None))

        assert (entry.term, entry.display, entry.parent) == ("BACT", "Bacteria", None)

    def test_the_live_parameter_parses(self) -> None:
        param = WDKEnumParam.model_validate(
            {
                "name": "phyletic_term_map",
                "type": "multi-pick-vocabulary",
                "displayType": "checkBox",
                "vocabulary": _TERM_MAP,
            }
        )

        terms = TypeAdapter(list[WDKVocabTerm]).validate_python(param.vocabulary)

        assert [t.parent for t in terms] == [
            None,
            "BACT",
            "FIRM",
            "FIRM",
            None,
            "EUKA",
            "MAMM",
        ]
