"""The clade tree of ``GenesByOrthologPattern``, the census pattern derived from
a selection, and the two documentation lists the reference client reads back."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from typing import Literal, NoReturn

from pydantic import BaseModel, ConfigDict, Field

from veupathdb.domain.parameters.wdk_vocab import VocabOption, WDKVocabTerm
from veupathdb.errors import ValidationError, param_message_rows

PHYLETIC_PARAM_NAMES = frozenset(
    {
        "profile_pattern",
        "included_species",
        "excluded_species",
        "phyletic_indent_map",
        "phyletic_term_map",
    }
)
"""A search is phyletic when it carries all five of these parameters."""

PHYLETIC_MAP_PARAMS = frozenset({"phyletic_term_map", "phyletic_indent_map"})
"""The two structural parameters that carry the tree. They state no criterion."""

PHYLETIC_LIST_PARAMS = frozenset({"included_species", "excluded_species"})
"""The two visible parameters a caller writes. ``profile_pattern`` is derived
from them, and the two maps carry the tree they are chosen from."""

TriState = Literal["include", "exclude"]
"""A species left out of both lists has no third state: the pattern omits it."""

NO_SPECIES = "n/a"
"""The literal the reference client decodes as the empty set."""

NO_CONSTRAINT_PATTERN = "%"
"""The pattern of an empty selection: every census matches it."""

_ROOT_CODE = "ALL"
"""The tree root, which the reference client also writes as ``All Organisms``.
Authoring resolves neither form: a pattern over every species exceeds the
parameter's 4000 character cap and states more than the request means."""

_DEFAULT_DEPTH = 1


class PhyleticNode(BaseModel):
    """One clade or species of the tree, with its children below it."""

    code: str
    label: str
    depth: int
    children: list[PhyleticNode] = Field(default_factory=list)


class ResolvedTerms(BaseModel):
    """The vocabulary codes a proposal named, and the words that named nothing."""

    codes: list[str] = Field(default_factory=list)
    unknown: list[str] = Field(default_factory=list)


class PhyleticBinding(BaseModel):
    """The three parameter values a selection produces.

    The field names are the WDK parameter names, so this model stays snake_case.
    """

    profile_pattern: str
    included_species: str
    excluded_species: str


class PhyleticUnresolved(BaseModel):
    """Why a pair of proposals binds nothing, named per parameter.

    A conflict is a code both proposals claim: the two states contradict, and
    the census has one state per species.
    """

    included_unknown: list[str] = Field(default_factory=list)
    excluded_unknown: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)


def _depth_of(display: str) -> int:
    """The depth the indent map carries in its display field."""
    text = display.strip()
    return int(text) if text.isdigit() else _DEFAULT_DEPTH


class PhyleticTree(BaseModel):
    """The clade tree built from ``phyletic_term_map`` and ``phyletic_indent_map``."""

    roots: list[PhyleticNode] = Field(default_factory=list)

    @classmethod
    def from_vocab(
        cls,
        term_map: Sequence[WDKVocabTerm],
        indent_map: Sequence[WDKVocabTerm],
    ) -> PhyleticTree:
        """Build the tree from the two vocabularies.

        Each entry states its parent term, which is the structure WDK publishes.
        An entry that names no parent, or one the map has not listed yet,
        attaches to the last node shallower than itself in the indent map. The
        synthetic root ``ALL`` is not a selectable node.
        """
        depths = {entry.term: _depth_of(entry.display) for entry in indent_map}
        roots: list[PhyleticNode] = []
        stack: list[PhyleticNode] = []
        by_code: dict[str, PhyleticNode] = {}
        for entry in term_map:
            if not entry.term or entry.term == _ROOT_CODE:
                continue
            depth = depths.get(entry.term, _DEFAULT_DEPTH)
            node = PhyleticNode(
                code=entry.term,
                label=entry.display or entry.term,
                depth=depth,
            )
            while stack and stack[-1].depth >= depth:
                stack.pop()
            stated = by_code.get(entry.parent) if entry.parent else None
            parent = stated or (stack[-1] if stack else None)
            if parent is None:
                roots.append(node)
            else:
                parent.children.append(node)
            by_code[node.code] = node
            stack.append(node)
        return cls(roots=roots)

    def nodes(self) -> Iterator[PhyleticNode]:
        """Every selectable node, in tree order. The root is not one of them."""

        def walk(nodes: list[PhyleticNode]) -> Iterator[PhyleticNode]:
            for node in nodes:
                yield node
                yield from walk(node.children)

        return walk(self.roots)

    def labels(self) -> list[VocabOption]:
        """Every selectable node as a code and its display name, in tree order."""
        return [
            VocabOption(value=node.code, display=node.label) for node in self.nodes()
        ]

    def resolve_terms(self, proposal: str | list[str]) -> ResolvedTerms:
        """Map a proposal to vocabulary codes and report what matched nothing.

        A proposal is a code or a display name, one per list entry or comma
        separated. An exact code wins over a case-insensitive match.
        """
        nodes = list(self.nodes())
        exact = {node.code for node in nodes}
        folded: dict[str, str] = {}
        for node in nodes:
            folded.setdefault(node.code.casefold(), node.code)
        for node in nodes:
            if node.label:
                folded.setdefault(node.label.casefold(), node.code)

        codes: list[str] = []
        unknown: list[str] = []
        for token in _split_proposal(proposal):
            code = token if token in exact else folded.get(token.casefold())
            if code is None:
                if token not in unknown:
                    unknown.append(token)
            elif code not in codes:
                codes.append(code)
        return ResolvedTerms(codes=codes, unknown=unknown)

    def leaf_states(
        self,
        included: Sequence[str],
        excluded: Sequence[str],
    ) -> dict[str, TriState]:
        """Push each selection down to the species the census holds.

        A clade code never appears in the census, so it takes its state to its
        leaves. An explicit leaf overrides the clade above it.
        """
        excluded_codes = set(excluded)
        included_codes = set(included)
        states: dict[str, TriState] = {}

        def walk(node: PhyleticNode, inherited: TriState | None) -> None:
            own: TriState | None = inherited
            if node.code in excluded_codes:
                own = "exclude"
            if node.code in included_codes:
                own = "include"
            if not node.children:
                if own is not None:
                    states[node.code] = own
                return
            for child in node.children:
                walk(child, own)

        for root in self.roots:
            walk(root, None)
        return states


def _split_proposal(proposal: str | list[str]) -> list[str]:
    """Split a proposal into trimmed terms, dropping blanks and the empty marker."""
    entries = [proposal] if isinstance(proposal, str) else proposal
    return [
        text
        for entry in entries
        for part in entry.split(",")
        if (text := part.strip()) and text.casefold() != NO_SPECIES
    ]


def encode_profile_pattern(states: Mapping[str, TriState]) -> str:
    """Write the census pattern for a set of species states.

    The census lists codes ascending and ``%A%B%`` means "A, then later B", so
    tokens out of that order describe a census that cannot exist. The empty
    selection is the bare wildcard, because WDK refuses an empty value.
    """
    tokens = sorted(
        f"{code}:{'Y' if state == 'include' else 'N'}" for code, state in states.items()
    )
    return f"%{'%'.join(tokens)}%" if tokens else NO_CONSTRAINT_PATTERN


_CENSUS_STATES: dict[str, TriState] = {"Y": "include", "N": "exclude"}


class CensusRead(BaseModel):
    """The states a profile_pattern holds, or why it holds none.

    ``states`` is ``None`` when the value is not built from census tokens.
    ``repeated_code`` names the code that appears twice, which is a different
    fault and gets a different message.
    """

    model_config = ConfigDict(frozen=True)

    states: dict[str, TriState] | None
    repeated_code: str | None = None


def read_census(pattern: str) -> CensusRead:
    """Read the species state each census token states.

    The value is a LIKE pattern over ``code:Y``/``code:N`` entries separated by
    the wildcard. Anything else matches nothing, and WDK reports that as a count
    rather than as an error. One code states one state, so a code that appears
    twice describes a census that cannot exist.
    """
    if not pattern.startswith("%") or not pattern.endswith("%"):
        return CensusRead(states=None)
    states: dict[str, TriState] = {}
    for entry in pattern.strip("%").split("%"):
        token = entry.strip()
        if not token:
            continue
        code, _, raw_state = token.partition(":")
        state = _CENSUS_STATES.get(raw_state)
        if not code or state is None:
            return CensusRead(states=None)
        if code in states:
            return CensusRead(states=None, repeated_code=code)
        states[code] = state
    return CensusRead(states=states)


_PATTERN_PARAM = "profile_pattern"


def _refuse_pattern(title: str, fault: str, repair: str) -> NoReturn:
    """Refuse a ``profile_pattern`` value, naming the parameter in the rows."""
    raise ValidationError(
        title=title,
        detail=f"{fault} {repair}",
        errors=param_message_rows({_PATTERN_PARAM: [fault]}),
    )


def _refuse_repeated_code(code: str, pattern: str) -> NoReturn:
    _refuse_pattern(
        "profile_pattern states one code twice",
        f"{code!r} appears twice in {pattern!r}.",
        f"A species is either present or absent, so state it once: "
        f"'%{code}:Y%' for present or '%{code}:N%' for absent.",
    )


def census_states(pattern: str) -> dict[str, TriState]:
    """The states a census pattern holds. Refuses anything that is not one.

    An empty mapping is the bare wildcard, which states no constraint.
    """
    read = read_census(pattern)
    if read.repeated_code is not None:
        _refuse_repeated_code(read.repeated_code, pattern)
    if read.states is None:
        _refuse_pattern(
            "profile_pattern is not a census pattern",
            f"{pattern!r} is not built from census tokens.",
            "Use '%code:Y%' for present and '%code:N%' for absent, in "
            "ascending code order, or '%' for no constraint. Call "
            "lookup_phyletic_codes() for the codes.",
        )
    return read.states


def sort_profile_pattern(pattern: str) -> str:
    """Rewrite a census pattern with its codes in ascending order.

    The pattern is matched against a census that lists codes ascending, and
    ``%A%B%`` means "A, then later B", so entries out of that order describe a
    census that cannot exist. A repeated code is refused here as well as on the
    expansion path, because both of them reach the wire.
    """
    read = read_census(pattern)
    if read.repeated_code is not None:
        _refuse_repeated_code(read.repeated_code, pattern)
    return pattern if read.states is None else encode_profile_pattern(read.states)


def validate_phyletic_codes(codes: Sequence[str], known_codes: set[str]) -> None:
    """Refuse a code the phyletic tree does not carry.

    WDK matches the pattern with LIKE, so an unknown code returns a count
    instead of an error.
    """
    invalid_codes = [code for code in codes if code not in known_codes]
    if invalid_codes:
        _refuse_pattern(
            "Invalid species codes in profile_pattern",
            f"Unknown codes: {', '.join(invalid_codes[:5])}.",
            "Use lookup_phyletic_codes() to find valid codes "
            "(e.g. 'pfal' for P. falciparum, 'hsap' for H. sapiens).",
        )


def _join_codes(codes: Sequence[str]) -> str:
    kept = list(dict.fromkeys(code for code in codes if code))
    return ", ".join(kept) if kept else NO_SPECIES


def species_lists(
    included: Sequence[str],
    excluded: Sequence[str],
) -> tuple[str, str]:
    """The two documentation strings: each list of codes joined in the given
    order, or the empty marker when the list is empty."""
    return _join_codes(included), _join_codes(excluded)


def derive_binding(
    tree: PhyleticTree,
    included: str | list[str],
    excluded: str | list[str],
) -> PhyleticBinding | PhyleticUnresolved:
    """Turn two proposals into the three parameter values.

    Reports the reasons instead of a binding when a term is unknown or a code is
    in both proposals, because a code the vocabulary does not carry matches
    nothing and reports no error.
    """
    resolved_included = tree.resolve_terms(included)
    resolved_excluded = tree.resolve_terms(excluded)
    excluded_codes = set(resolved_excluded.codes)
    conflicts = [code for code in resolved_included.codes if code in excluded_codes]
    if resolved_included.unknown or resolved_excluded.unknown or conflicts:
        return PhyleticUnresolved(
            included_unknown=resolved_included.unknown,
            excluded_unknown=resolved_excluded.unknown,
            conflicts=conflicts,
        )
    included_list, excluded_list = species_lists(
        resolved_included.codes, resolved_excluded.codes
    )
    return PhyleticBinding(
        profile_pattern=encode_profile_pattern(
            tree.leaf_states(resolved_included.codes, resolved_excluded.codes)
        ),
        included_species=included_list,
        excluded_species=excluded_list,
    )
