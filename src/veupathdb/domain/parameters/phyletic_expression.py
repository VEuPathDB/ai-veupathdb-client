"""OrthoMCL's phyletic pattern expression: the grammar of ``phyletic_expression``,
its written form, the codes it names and a reading of it in words."""

from __future__ import annotations

import operator
import re
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from typing import Literal, NoReturn

from pydantic import BaseModel, ConfigDict, Field

from veupathdb.domain.parameters.phyletic import (
    PHYLETIC_ROOT_CODE,
    PhyleticNode,
    PhyleticTree,
    refuse_phyletic_value,
    species_of,
    validate_phyletic_codes,
)

PHYLETIC_EXPRESSION_PARAM = "phyletic_expression"
"""The one parameter of OrthoMCL's ``GroupsByPhyleticPattern``."""

PHYLETIC_EXPRESSION_SEARCH = "GroupsByPhyleticPattern"

ExpressionOp = Literal[">=", "<=", ">", "<", "="]
Join = Literal["AND", "OR"]

_OP_WORDS: dict[ExpressionOp, str] = {
    ">=": "at least",
    "<=": "at most",
    ">": "more than",
    "<": "fewer than",
    "=": "exactly",
}

_UNITS = {True: ("genome", "genomes"), False: ("protein", "proteins")}

_COMPARED: dict[ExpressionOp, Callable[[int, int], bool]] = {
    ">=": operator.ge,
    "<=": operator.le,
    ">": operator.gt,
    "<": operator.lt,
    "=": operator.eq,
}

_NO_PARENTHESES = str.maketrans("", "", "()")

_TOKEN = re.compile(
    r"\s*(?:(?P<open>\()|(?P<close>\))|(?P<join>AND|OR)\b"
    r"|(?P<codes>[A-Za-z]+(?:\s*\+\s*[A-Za-z]*)*)"
    r"(?:\s*(?P<op>>=|<=|>|<|=)\s*(?P<count>\d+)(?P<taxa>[Tt])?)?)",
    re.IGNORECASE,
)

_GRAMMAR = (
    "A unit is codes joined by '+', an operator (>, <, =, >= or <=) and a count; "
    "a count ending in T counts genomes, a bare count counts proteins. A unit "
    "holds only for a group with a protein of its codes, except =0T or =0, "
    "which is absence. AND binds before OR and the site drops parentheses, so "
    "write an OR of AND terms, for example "
    "'hsap>=1T AND mmus+rnor<=1T OR hsap>=1T AND mmus+rnor=0T'."
)


class _TreeIndex:
    def __init__(self, tree: PhyleticTree) -> None:
        self.labels: dict[str, str] = {}
        self.below: dict[str, frozenset[str]] = {}
        self.position: dict[str, int] = {}
        self.species: dict[str, str] = {}
        for root in tree.roots:
            self._walk(root)
        self.below[PHYLETIC_ROOT_CODE] = frozenset(self.position)

    def _walk(self, node: PhyleticNode) -> frozenset[str]:
        self.labels[node.code] = node.label
        if not node.clade:
            self.position[node.code] = len(self.position)
            self.species[node.code] = species_of(node.label)
            held = frozenset({node.code})
        else:
            held = frozenset(
                genome for child in node.children for genome in self._walk(child)
            )
        self.below[node.code] = held
        return held

    def genomes(self, codes: Sequence[str]) -> set[str]:
        return {genome for code in codes for genome in self.below.get(code, ())}

    def span(self, codes: Sequence[str]) -> str:
        grouped: dict[str, int] = {}
        for genome in sorted(self.genomes(codes), key=self.position.__getitem__):
            name = self.species[genome]
            grouped[name] = grouped.get(name, 0) + 1
        genomes = sum(grouped.values())
        if genomes <= 1:
            return ""
        counted = f"{genomes} genomes of {len(grouped)} species"
        shared = sorted(
            ((name, held) for name, held in grouped.items() if held > 1),
            key=lambda pair: (-pair[1], pair[0]),
        )
        if not shared:
            return f" ({counted})"
        named = ", ".join(f"{name} {held}" for name, held in shared)
        return f" ({counted}; {named})"


class TaxaCount(BaseModel):
    """One unit: how many genomes or proteins of these codes a group holds."""

    model_config = ConfigDict(frozen=True)

    codes: tuple[str, ...] = Field(min_length=1)
    op: ExpressionOp
    count: int = Field(ge=0)
    taxa: bool

    def render(self, *, nested: bool = False) -> str:
        return f"{'+'.join(self.codes)}{self.op}{self.count}{'T' if self.taxa else ''}"

    def describe(self, tree: PhyleticTree, *, nested: bool = False) -> str:
        return self.read(_TreeIndex(tree), nested=nested)

    def read(self, index: _TreeIndex, *, nested: bool = False) -> str:
        named = ", ".join(index.labels.get(code, code) for code in self.codes)
        unit = _UNITS[self.taxa][self.count != 1]
        listed = f"these {len(self.codes)}: " if len(self.codes) > 1 else ""
        spanned = index.span(self.codes)
        return f"{_OP_WORDS[self.op]} {self.count} {unit} of {listed}{named}{spanned}"

    def operands(self, join: Join) -> tuple[Term, ...]:
        return (self,)

    def repeated(self, tree: PhyleticTree) -> list[str]:
        return self.repeated_in(_TreeIndex(tree))

    def repeated_in(self, index: _TreeIndex) -> list[str]:
        written = Counter(self.codes)
        held = Counter(
            genome for code in written for genome in index.below.get(code, ())
        )
        return sorted(
            {code for code, times in written.items() if times > 1}
            | {genome for genome, times in held.items() if times > 1}
        )

    def holds_for(self, proteins: Mapping[str, int], tree: PhyleticTree) -> bool:
        return self.holds_in(proteins, _TreeIndex(tree))

    def holds_in(self, proteins: Mapping[str, int], index: _TreeIndex) -> bool:
        _refuse_repeats(self, index)
        held = [
            proteins[genome]
            for genome in index.genomes(self.codes)
            if genome in proteins and proteins[genome] > 0
        ]
        if not held:
            return self.op == "=" and self.count == 0
        value = len(held) if self.taxa else sum(held)
        return _COMPARED[self.op](value, self.count)


class Combination(BaseModel):
    """Two or more terms joined by one operator."""

    model_config = ConfigDict(frozen=True)

    join: Join
    terms: tuple[TaxaCount | Combination, ...] = Field(min_length=2)

    def render(self, *, nested: bool = False) -> str:
        text = f" {self.join} ".join(term.render(nested=True) for term in self.terms)
        return f"({text})" if nested else text

    def describe(self, tree: PhyleticTree, *, nested: bool = False) -> str:
        return self.read(_TreeIndex(tree), nested=nested)

    def read(self, index: _TreeIndex, *, nested: bool = False) -> str:
        text = f" {self.join.lower()} ".join(
            term.read(index, nested=True) for term in self.terms
        )
        return f"({text})" if nested else text

    def operands(self, join: Join) -> tuple[Term, ...]:
        return self.terms if join == self.join else (self,)

    def holds_for(self, proteins: Mapping[str, int], tree: PhyleticTree) -> bool:
        return self.holds_in(proteins, _TreeIndex(tree))

    def holds_in(self, proteins: Mapping[str, int], index: _TreeIndex) -> bool:
        met = (term.holds_in(proteins, index) for term in self.terms)
        return all(met) if self.join == "AND" else any(met)


Term = TaxaCount | Combination


def _joined(join: Join, terms: Sequence[Term]) -> Term:
    flat = tuple(operand for term in terms for operand in term.operands(join))
    return flat[0] if len(flat) == 1 else Combination(join=join, terms=flat)


class PhyleticExpression(BaseModel):
    """A parsed ``phyletic_expression``. AND binds before OR, and parentheses
    group terms; ``site_reading`` drops them, as the site does."""

    model_config = ConfigDict(frozen=True)

    root: Term

    @classmethod
    def parse(cls, text: str) -> PhyleticExpression:
        if not text.strip():
            _refuse(f"{text!r} is empty.")
        tokens = _tokens(text)
        root, end = _expression(tokens, 0, text)
        if end < len(tokens):
            _refuse(f"In {text!r}, a ')' closes nothing.")
        return cls(root=root)

    def render(self) -> str:
        return self.root.render()

    def describe(self, tree: PhyleticTree) -> str:
        return self.root.read(_TreeIndex(tree))

    def units(self) -> list[TaxaCount]:
        found: list[TaxaCount] = []
        pending: list[Term] = [self.root]
        while pending:
            term = pending.pop()
            if isinstance(term, TaxaCount):
                found.append(term)
            else:
                pending.extend(reversed(term.terms))
        return found

    def codes(self) -> list[str]:
        return list(dict.fromkeys(code for unit in self.units() for code in unit.codes))

    def site_reading(self) -> PhyleticExpression:
        return PhyleticExpression.parse(self.render().translate(_NO_PARENTHESES))

    def holds_for(self, proteins: Mapping[str, int], tree: PhyleticTree) -> bool:
        return self.site_reading().root.holds_in(proteins, _TreeIndex(tree))


def check_expression(expression: PhyleticExpression, tree: PhyleticTree) -> None:
    """Refuse a code the taxonomy does not carry, parentheses the site drops, a
    unit that names a genome twice, an upper bound of zero, and a unit that states
    no constraint or none beyond presence. ``ALL`` is the whole tree."""
    validate_phyletic_codes(
        expression.codes(),
        tree.codes() | {PHYLETIC_ROOT_CODE},
        param_name=PHYLETIC_EXPRESSION_PARAM,
    )
    read = expression.site_reading()
    if read != expression:
        _refuse(
            f"{expression.render()} groups terms the site does not: it reads "
            f"{read.render()}, because the site drops parentheses and reads AND "
            "before OR; write an OR of AND terms, repeating shared units in each "
            "term.",
            title="phyletic_expression groups terms the site does not group",
        )
    index = _TreeIndex(tree)
    for unit in expression.units():
        _check_unit(unit, index)


def _refuse_repeats(unit: TaxaCount, index: _TreeIndex) -> None:
    repeated = unit.repeated_in(index)
    if repeated:
        _refuse(
            f"{unit.render()} names these codes more than once: "
            f"{', '.join(repeated)}; name each genome once.",
            title="phyletic_expression names a genome twice in one unit",
        )


def _check_unit(unit: TaxaCount, index: _TreeIndex) -> None:
    codes = "+".join(unit.codes)
    _refuse_repeats(unit, index)
    genomes = len(index.genomes(unit.codes))
    if (unit.op, unit.count) in {("<=", 0), ("<", 1)}:
        _refuse(
            f"{unit.render()} matches no group, because the site counts a unit "
            f"only in a group with a protein of its codes; write {codes}=0T for "
            "absence.",
            title="phyletic_expression writes absence as an upper bound",
        )
    spanned = f" over {genomes} {_UNITS[True][genomes != 1]}" if unit.taxa else ""
    bound = genomes if unit.taxa else None
    if genomes == 0 or _constant(unit, bound):
        _refuse(
            f"{unit.render()}{spanned} is true of every group or of none, so it "
            "states no constraint.",
            title="phyletic_expression holds a unit that decides nothing",
        )
    if _presence(unit, bound):
        _refuse(
            f"{unit.render()}{spanned} holds exactly the groups with a protein of "
            f"its codes, so it states no constraint beyond "
            f"{codes}>=1{'T' if unit.taxa else ''}.",
            title="phyletic_expression holds a unit that decides nothing",
        )


def _constant(unit: TaxaCount, bound: int | None) -> bool:
    match unit.op:
        case "<":
            return unit.count == 0
        case ">" if bound is not None:
            return unit.count >= bound
        case "=" | ">=" if bound is not None:
            return unit.count > bound
        case _:
            return False


def _presence(unit: TaxaCount, bound: int | None) -> bool:
    match unit.op:
        case ">=":
            return unit.count == 0
        case "<=" if bound is not None:
            return unit.count >= bound
        case "<" if bound is not None:
            return unit.count > bound
        case _:
            return False


_Token = tuple[str, str | TaxaCount]


def _refuse(
    fault: str,
    *,
    title: str = "phyletic_expression is not a phyletic pattern expression",
) -> NoReturn:
    refuse_phyletic_value(PHYLETIC_EXPRESSION_PARAM, title, fault, _GRAMMAR)


def _unit(match: re.Match[str], text: str) -> TaxaCount:
    codes = [code.strip() for code in match["codes"].split("+")]
    if not all(codes):
        _refuse(f"In {text!r}, a '+' joins two codes and stands at neither end.")
    if match["op"] is None:
        _refuse(
            f"In {text!r}, {match['codes'].strip()!r} needs an operator and a count."
        )
    return TaxaCount.model_validate(
        {
            "codes": codes,
            "op": match["op"],
            "count": match["count"],
            "taxa": match["taxa"] is not None,
        }
    )


def _tokens(text: str) -> list[_Token]:
    tokens: list[_Token] = []
    position = 0
    while position < len(text.rstrip()):
        match = _TOKEN.match(text, position)
        if match is None or match.end() == position:
            _refuse(
                f"In {text!r}, {text[position:].strip()!r} is not part of the grammar."
            )
        if match["open"]:
            tokens.append(("open", "("))
        elif match["close"]:
            tokens.append(("close", ")"))
        elif match["join"]:
            tokens.append(("join", match["join"].upper()))
        else:
            tokens.append(("unit", _unit(match, text)))
        position = match.end()
    return tokens


def _term(tokens: list[_Token], at: int, text: str) -> tuple[Term, int]:
    if at >= len(tokens):
        _refuse(f"{text!r} ends where a unit belongs.")
    kind, value = tokens[at]
    if kind == "unit" and isinstance(value, TaxaCount):
        return value, at + 1
    if kind == "open":
        inner, end = _expression(tokens, at + 1, text)
        if end >= len(tokens) or tokens[end][0] != "close":
            _refuse(f"In {text!r}, a '(' is never closed.")
        return inner, end + 1
    _refuse(f"In {text!r}, {value!r} stands where a unit belongs.")


def _expression(tokens: list[_Token], at: int, text: str) -> tuple[Term, int]:
    first, at = _term(tokens, at, text)
    products: list[list[Term]] = [[first]]
    while at < len(tokens) and tokens[at][0] != "close":
        kind, value = tokens[at]
        if kind != "join":
            _refuse(f"In {text!r}, AND or OR joins two units.")
        if at + 1 == len(tokens):
            _refuse(f"{text!r} ends after {value}.")
        if value == "OR":
            products.append([])
        term, at = _term(tokens, at + 1, text)
        products[-1].append(term)
    return _joined("OR", [_joined("AND", product) for product in products]), at
