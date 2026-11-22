"""The phrasings one vocabulary lookup reads, and the entries each one matches.

Pure module (no I/O). A term matches as a phrase with hyphen and space alike,
then as its words in any order, then by each uncommon word when neither matched.
The kept entries that carry the request's own words rank first.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Self

from pydantic import ConfigDict, Field, model_validator

from veupathdb.domain.parameters.vocab_utils import looks_numeric, numeric_equivalent
from veupathdb.domain.parameters.wdk_vocab import VocabOption, match_exact_option
from veupathdb.errors import ValidationError
from veupathdb.model import CamelModel, computed

Reach = Literal["phrase", "every_word", "word"]
_REACH_ORDER: tuple[Reach, ...] = ("phrase", "every_word", "word")
_WORD = re.compile(r"[^\W_]+")
_FEWEST_WORDS_TO_SPLIT = 2
# A word more than this share of the labels hold names no concept on its own.
_COMMON_WORD_SHARE = 0.1


def _folded(text: str) -> str:
    """The text in lower case, with every run of other characters one space."""
    return " ".join(_WORD.findall(text.casefold()))


class PhrasingMatch(CamelModel):
    """One phrasing a lookup read, and the entries it matched first."""

    model_config = ConfigDict(frozen=True)

    term: str
    phrasing: str
    reach: Reach
    values: list[str] = Field(default_factory=list)


class AccessionNames(CamelModel):
    model_config = ConfigDict(frozen=True)

    entries: int
    one_token: int
    nameless: int


def accession_names(options: Sequence[VocabOption]) -> AccessionNames | None:
    named = [(o.value, o.display) for o in options if o.display != o.value]
    if not named or not all(display.startswith(value) for value, display in named):
        return None
    names = [display[len(value) :].lstrip(" :") for value, display in named]
    return AccessionNames(
        entries=len(names),
        one_token=sum(len(name.split()) <= 1 for name in names),
        nameless=sum(not _WORD.search(name) for name in names),
    )


class VocabLookup(CamelModel):
    """The terms a read narrowed a vocabulary by, and the phrasings that matched.

    Each kept entry is counted under the first phrasing that matched it.
    ``request_matches`` counts each kept entry that carries the request's own
    words under the first phrasing of those words that holds it.
    """

    model_config = ConfigDict(frozen=True)

    terms: list[str]
    matches: list[PhrasingMatch] = Field(default_factory=list)
    request_terms: list[str] = Field(default_factory=list)
    request_matches: list[PhrasingMatch] = Field(default_factory=list)
    accession: AccessionNames | None = None

    def request_values(self) -> list[str]:
        """The kept entries that carry the request's words, in rank order."""
        return [value for match in self.request_matches for value in match.values]


@dataclass(frozen=True, slots=True)
class _Phrasing:
    term: str
    text: str
    reach: Reach

    def holds(self, *labels: str) -> bool:
        if self.reach == "every_word":
            words = self.text.split()
            return any(all(word in label for word in words) for label in labels)
        return any(self.text in label for label in labels)


def _phrasings_of(term: str, reach: Reach) -> list[_Phrasing]:
    text = _folded(term)
    words = text.split()
    if reach == "phrase":
        return [_Phrasing(term, text, "phrase")] if text else []
    if len(words) < _FEWEST_WORDS_TO_SPLIT:
        return []
    if reach == "every_word":
        return [_Phrasing(term, text, "every_word")]
    return [_Phrasing(term, word, "word") for word in dict.fromkeys(words)]


@dataclass(frozen=True, slots=True)
class VocabRead:
    """The entries a lookup kept, ranked, and the phrasings it applied."""

    options: list[VocabOption]
    lookup: VocabLookup | None
    phrasings: tuple[_Phrasing, ...] = ()

    def matches(self, value: str, display: str) -> bool:
        """Whether an entry holds any phrasing the lookup applied."""
        labels = (_folded(value), _folded(display))
        return any(phrasing.holds(*labels) for phrasing in self.phrasings)


_Labels = list[tuple[str, str]]


def _labels(options: list[VocabOption]) -> _Labels:
    return [(_folded(o.value), _folded(o.display)) for o in options]


def _applied(labels: _Labels, term: str) -> list[_Phrasing]:
    """The phrase and its words in any order, and each uncommon word alone when
    neither matches an entry. A word alone matches entries that hold less of the term."""
    whole = _phrasings_of(term, "phrase") + _phrasings_of(term, "every_word")
    if any(p.holds(*label) for p in whole for label in labels):
        return whole
    common = _COMMON_WORD_SHARE * len(labels)
    return whole + [
        word
        for word in _phrasings_of(term, "word")
        if sum(word.holds(*label) for label in labels) <= common
    ]


def _claimed(
    phrasings: Sequence[_Phrasing], options: list[VocabOption], labels: _Labels
) -> dict[_Phrasing, list[VocabOption]]:
    """Each option under the first phrasing that holds it, by reach."""
    ranked = sorted(phrasings, key=lambda p: _REACH_ORDER.index(p.reach))
    claimed: dict[_Phrasing, list[VocabOption]] = {p: [] for p in ranked}
    seen: set[str] = set()
    for phrasing in ranked:
        for option, label in zip(options, labels, strict=True):
            if option.value not in seen and phrasing.holds(*label):
                claimed[phrasing].append(option)
                seen.add(option.value)
    return claimed


def _matched(claimed: dict[_Phrasing, list[VocabOption]]) -> list[PhrasingMatch]:
    return [
        PhrasingMatch(
            term=p.term,
            phrasing=p.text,
            reach=p.reach,
            values=[option.value for option in options],
        )
        for p, options in claimed.items()
        if options
    ]


def read_options(
    options: list[VocabOption],
    terms: Sequence[str],
    *,
    request_terms: Sequence[str],
) -> VocabRead:
    """Keep the entries any phrasing of the terms matches, ranked by reach.

    ``request_terms`` are the concept in the request's own words. They are read
    as a term is, and the kept entries they match rank first. They keep no entry.
    """
    if not terms:
        return VocabRead(options=options, lookup=None)
    labels = _labels(options)
    phrasings = [p for term in terms for p in _applied(labels, term)]
    by_term = _claimed(phrasings, options, labels)
    kept = [option for claimed in by_term.values() for option in claimed]
    asked = [p for term in request_terms for p in _applied(labels, term)]
    by_request = _claimed(asked, kept, _labels(kept))
    first = [option for claimed in by_request.values() for option in claimed]
    carried = {option.value for option in first}
    return VocabRead(
        options=first + [option for option in kept if option.value not in carried],
        lookup=VocabLookup(
            terms=list(terms),
            matches=_matched(by_term),
            request_terms=list(request_terms),
            request_matches=_matched(by_request),
            accession=accession_names(options),
        ),
        phrasings=tuple(phrasings),
    )


SHOWN_CANDIDATES = 5
DECIDED_CANDIDATES = 254

How = Literal["exact", "decided", "unsettled", "none"]


class Resolution(CamelModel):
    model_config = ConfigDict(frozen=True)

    phrase: str
    value: str | None = None
    display: str | None = None
    how: How
    candidates: list[VocabOption]
    confidence: float | None = None

    @computed
    def settled(self) -> bool:
        return self.how in ("exact", "decided")

    @model_validator(mode="after")
    def _a_value_is_what_settles(self) -> Self:
        if (self.value is not None) != self.settled:
            msg = (
                f"a {self.how} resolution of {self.phrase!r} holds value {self.value!r}"
            )
            raise ValueError(msg)
        if (self.how == "none") != (not self.candidates and not self.settled):
            held = len(self.candidates)
            msg = f"a {self.how} resolution of {self.phrase!r} holds {held} candidates"
            raise ValueError(msg)
        return self


def rank_entries(
    options: Sequence[VocabOption], phrase: str, limit: int
) -> list[VocabOption]:
    entries = list(options)
    lexical = read_options(entries, [phrase], request_terms=[phrase]).options
    by_label: dict[str, VocabOption] = {}
    for option in entries:
        by_label.setdefault(option.value, option)
        by_label.setdefault(option.display, option)
    labels = list(by_label)
    spelled = difflib.get_close_matches(phrase, labels, n=len(labels) or 1, cutoff=0.0)
    ranked: dict[str, VocabOption] = {}
    for option in [*lexical, *(by_label[label] for label in spelled)]:
        ranked.setdefault(option.value, option)
    return list(ranked.values())[:limit]


def _exact(options: Sequence[VocabOption], phrase: str) -> VocabOption | None:
    value = match_exact_option(options, phrase)
    if value is None and looks_numeric(phrase.strip()):
        value = next(
            (
                o.value
                for o in options
                if numeric_equivalent(phrase, o.value)
                or numeric_equivalent(phrase, o.display)
            ),
            None,
        )
    return next((o for o in options if o.value == value), None)


def exact_or_candidates(
    options: Sequence[VocabOption], phrase: str, limit: int
) -> Resolution:
    exact = _exact(options, phrase)
    if exact is not None:
        return Resolution(
            phrase=phrase,
            value=exact.value,
            display=exact.display,
            how="exact",
            candidates=[],
        )
    candidates = rank_entries(options, phrase, limit)
    return Resolution(
        phrase=phrase,
        how="unsettled" if candidates else "none",
        candidates=candidates,
    )


def entry_name(option: VocabOption) -> str:
    if option.display == option.value:
        return option.display
    return f"{option.display} ({option.value})"


def _fault_line(param: str, resolution: Resolution) -> str:
    shown = resolution.candidates[:SHOWN_CANDIDATES]
    if not shown:
        return f"{param} has no entry {resolution.phrase!r}, and no entry is near it."
    named = ", ".join(entry_name(c) for c in shown)
    return f"{param} has no entry {resolution.phrase!r}. Candidates: {named}."


class VocabularyEntryError(ValidationError):
    def __init__(self, faults: list[tuple[str, Resolution]]) -> None:
        self.faults = faults
        super().__init__(
            title="Invalid parameter value",
            detail="\n".join(_fault_line(p, r) for p, r in faults),
            errors=[
                {
                    "param": param,
                    "value": resolution.phrase,
                    "candidates": [
                        {"value": c.value, "display": c.display}
                        for c in resolution.candidates
                    ],
                }
                for param, resolution in faults
            ],
        )
