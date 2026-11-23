"""Value objects and walkers for WDK parameter vocabularies: standard enum
lists, tree-box trees, filter ontologies, and dataset parsers."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from types import MappingProxyType
from typing import Literal

from pydantic import Field, RootModel

from veupathdb.model import CamelModel

FAKE_ALL_SENTINEL = "@@fake@@"
"""The term WDK gives the synthetic tree root. It is not a submittable value."""


class WDKVocabNodeData(CamelModel):
    """The data payload of a tree-box vocabulary node."""

    term: str = ""
    display: str = ""


class WDKTreeBoxVocabNode(CamelModel):
    """A node in a tree-box enum vocabulary."""

    data: WDKVocabNodeData = Field(default_factory=WDKVocabNodeData)
    children: list[WDKTreeBoxVocabNode] = Field(default_factory=list)


class WDKVocabTerm(RootModel[tuple[str, str, str | None]]):
    """A standard enum vocabulary entry as a term, display, parent triple.

    The third element is the term of the entry above this one, and is null for
    an entry at the top of the vocabulary.
    """

    @property
    def term(self) -> str:
        return self.root[0]

    @property
    def display(self) -> str:
        return self.root[1]

    @property
    def parent(self) -> str | None:
        return self.root[2]


class WDKFilterOntologyTerm(CamelModel):
    """A node in the ontology tree of a filter parameter."""

    term: str
    parent: str | None = None
    display: str = ""
    description: str | None = None
    type: Literal["date", "string", "number", "multiFilter"] | None = None
    precision: int = 1
    is_range: bool = False
    units: str | None = None


class WDKDatasetParser(CamelModel):
    """An input parser offered by a dataset parameter."""

    name: str
    display_name: str = ""
    description: str = ""


WDKVocabulary = list[WDKVocabTerm] | WDKTreeBoxVocabNode
"""A standard enum vocabulary list, or a tree-box vocabulary tree."""


class VocabOption(CamelModel):
    """A flattened vocabulary entry with the submittable term and its
    label."""

    value: str
    display: str


def dedupe_options(options: Iterable[VocabOption]) -> list[VocabOption]:
    """Keep the first entry for each value, in order. Empty values are dropped."""
    seen: set[str] = set()
    kept: list[VocabOption] = []
    for option in options:
        if not option.value or option.value in seen:
            continue
        seen.add(option.value)
        kept.append(option)
    return kept


def normalize_vocab_key(value: str) -> str:
    """Lowercase the value and collapse its whitespace for matching."""
    return re.sub(r"\s+", " ", value.strip()).lower()


_ACCESSION_MIN_LENGTH = 4


def leading_accession_token(value: str) -> str | None:
    """The accession a vocabulary value starts with, or ``None``.

    A typeahead term reads ``<accession> : <label>``, so the accession is the
    text before the first whitespace. It identifies an entry only when it holds
    a digit and is long enough; a plain word is a label, not an accession.
    """
    head = value.split(maxsplit=1)
    if not head:
        return None
    token = head[0]
    if len(token) < _ACCESSION_MIN_LENGTH or not any(c.isdigit() for c in token):
        return None
    return token


def accession_matches(options: Iterable[VocabOption], value: str) -> list[str]:
    """The value of every entry whose leading accession is this text."""
    key = normalize_vocab_key(value)
    return [
        option.value
        for option in options
        if (token := leading_accession_token(option.value)) is not None
        and normalize_vocab_key(token) == key
    ]


def name_past_accession(option: VocabOption) -> str:
    token = leading_accession_token(option.display)
    if token is None:
        return option.display
    rest = option.display[len(token) :].lstrip()
    return rest.lstrip(" :") if rest.startswith(":") else option.display


type EntryPaths = Mapping[str, tuple[str, ...]]

NO_PATHS: EntryPaths = MappingProxyType({})


def same_named_groups(
    options: Iterable[VocabOption], under: EntryPaths = NO_PATHS
) -> list[list[str]]:
    """The entries that share a name past their accessions and sit under the
    same labels of the tree in ``under``; the tree tells the others apart."""
    by_name: dict[tuple[tuple[str, ...], str], list[str]] = {}
    for option in options:
        path = tuple(normalize_vocab_key(p) for p in under.get(option.value, ()))
        name = normalize_vocab_key(name_past_accession(option))
        held = by_name.setdefault((path, name), [])
        if option.value not in held:
            held.append(option.value)
    return [values for values in by_name.values() if len(values) > 1]


def match_exact_option(options: Iterable[VocabOption], value: str) -> str | None:
    """The option whose term or label is this text, ignoring case and spacing.

    A tree parent term is an option and selects its children. A substring is a
    different entry, so it does not match. A label several entries share names
    none of them. A text that is the leading accession of exactly one entry names
    that entry; two entries make it ambiguous.
    """
    entries = list(options)
    key = normalize_vocab_key(value)
    for option in entries:
        if key == normalize_vocab_key(option.value):
            return option.value
    grouped = {value for group in same_named_groups(entries) for value in group}
    for option in entries:
        if key == normalize_vocab_key(option.display):
            shared = option.value in grouped
            named = key == normalize_vocab_key(name_past_accession(option))
            return None if shared and named else option.value
    by_accession = accession_matches(entries, value)
    return by_accession[0] if len(by_accession) == 1 else None


def _walk_tree(node: WDKTreeBoxVocabNode) -> list[VocabOption]:
    options = [
        VocabOption(value=node.data.term, display=node.data.display or node.data.term)
    ]
    for child in node.children:
        options.extend(_walk_tree(child))
    return options


def flatten_vocab(vocab: WDKVocabulary | None) -> list[VocabOption]:
    """Flatten a vocabulary into options.

    A tree yields every node except the synthetic root. WDK accepts leaf terms
    only, and a parent term expands to its leaves at submission time.
    """
    if vocab is None:
        return []
    if isinstance(vocab, WDKTreeBoxVocabNode):
        return [
            opt
            for opt in _walk_tree(vocab)
            if opt.value and opt.value != FAKE_ALL_SENTINEL
        ]
    return [VocabOption(value=t.term, display=t.display or t.term) for t in vocab]


def _paths(
    node: WDKTreeBoxVocabNode, above: tuple[str, ...]
) -> dict[str, tuple[str, ...]]:
    paths = {node.data.term: above}
    below = (*above, node.data.display or node.data.term)
    for child in node.children:
        paths |= _paths(child, below)
    return paths


def vocab_paths(vocab: WDKVocabulary | None) -> dict[str, tuple[str, ...]]:
    """Each term of a tree and the labels of the nodes above it, the synthetic
    root left out. A list has no paths."""
    if not isinstance(vocab, WDKTreeBoxVocabNode):
        return {}
    return {
        term: path
        for child in vocab.children
        for term, path in _paths(child, ()).items()
    }


def collect_leaf_terms(node: WDKTreeBoxVocabNode) -> list[str]:
    """Collect every leaf term under the node. A leaf node returns its own
    term."""
    if not node.children:
        return [node.data.term] if node.data.term else []
    leaves: list[str] = []
    for child in node.children:
        leaves.extend(collect_leaf_terms(child))
    return leaves


def leaf_terms(
    vocabulary: WDKVocabulary | None, terms: Sequence[str]
) -> list[str] | None:
    """Each term as the leaves under it, in order and each once, the form WDK
    counts under countOnlyLeaves (WDK-VOCAB-002). None when a term names no node
    of the tree; the synthetic root names none."""
    leaves: list[str] = []
    for term in terms:
        node = None if term == FAKE_ALL_SENTINEL else find_vocab_node(vocabulary, term)
        if node is None:
            return None
        leaves.extend(collect_leaf_terms(node))
    return list(dict.fromkeys(leaves))


def find_vocab_node(
    vocab: WDKVocabulary | None,
    match: str,
    *,
    normalize: bool = False,
) -> WDKTreeBoxVocabNode | None:
    """Find the tree node whose term or display equals the match.

    A list vocabulary has no tree, so it always returns ``None``.
    """
    if not isinstance(vocab, WDKTreeBoxVocabNode) or not match:
        return None
    norm_match = normalize_vocab_key(match) if normalize else None

    def walk(node: WDKTreeBoxVocabNode) -> WDKTreeBoxVocabNode | None:
        candidates = [node.data.term, node.data.display]
        if match in candidates:
            return node
        if norm_match is not None and any(
            normalize_vocab_key(c) == norm_match for c in candidates if c
        ):
            return node
        for child in node.children:
            found = walk(child)
            if found is not None:
                return found
        return None

    return walk(vocab)


def vocab_keys(vocab: WDKVocabulary | None) -> set[str]:
    """Return the submittable terms: the leaf terms of a tree, or every term
    of a list."""
    if vocab is None:
        return set()
    if isinstance(vocab, WDKTreeBoxVocabNode):
        return {t for t in collect_leaf_terms(vocab) if t}
    return {t.term for t in vocab}
