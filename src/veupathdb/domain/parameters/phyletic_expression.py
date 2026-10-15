"""OrthoMCL's phyletic pattern expression: the grammar of ``phyletic_expression``,
its written form, the codes it names and a reading of it in words."""

from __future__ import annotations

import re
from typing import Literal, NoReturn

from pydantic import BaseModel, ConfigDict, Field

from veupathdb.domain.parameters.phyletic import (
    PHYLETIC_ROOT_CODE,
    PhyleticTree,
    refuse_phyletic_value,
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

_UNITS = {True: ("taxon", "taxa"), False: ("sequence", "sequences")}

_TOKEN = re.compile(
    r"\s*(?:(?P<open>\()|(?P<close>\))|(?P<join>AND|OR)\b"
    r"|(?P<codes>[A-Za-z]+(?:\s*\+\s*[A-Za-z]*)*)"
    r"(?:\s*(?P<op>>=|<=|>|<|=)\s*(?P<count>\d+)(?P<taxa>[Tt])?)?)",
    re.IGNORECASE,
)

_GRAMMAR = (
    "A unit is codes joined by '+', an operator (>, <, =, >= or <=) and a count; "
    "a count ending in T counts taxa, a bare count counts sequences. AND and OR "
    "join units, and parentheses group them, for example "
    "'pfal>=1T AND pfag+pfhb<=1T'."
)


class TaxaCount(BaseModel):
    """One unit: how many taxa or sequences of these codes a group holds."""

    model_config = ConfigDict(frozen=True)

    codes: tuple[str, ...] = Field(min_length=1)
    op: ExpressionOp
    count: int = Field(ge=0)
    taxa: bool

    def render(self, *, nested: bool = False) -> str:
        return f"{'+'.join(self.codes)}{self.op}{self.count}{'T' if self.taxa else ''}"

    def describe(self, tree: PhyleticTree, *, nested: bool = False) -> str:
        labels = {node.code: node.label for node in tree.nodes()}
        named = ", ".join(labels.get(code, code) for code in self.codes)
        unit = _UNITS[self.taxa][self.count != 1]
        listed = f"these {len(self.codes)}: " if len(self.codes) > 1 else ""
        return f"{_OP_WORDS[self.op]} {self.count} {unit} of {listed}{named}"


class Combination(BaseModel):
    """Two or more terms joined by one operator."""

    model_config = ConfigDict(frozen=True)

    join: Join
    terms: tuple[TaxaCount | Combination, ...] = Field(min_length=2)

    def render(self, *, nested: bool = False) -> str:
        text = f" {self.join} ".join(term.render(nested=True) for term in self.terms)
        return f"({text})" if nested else text

    def describe(self, tree: PhyleticTree, *, nested: bool = False) -> str:
        text = f" {self.join.lower()} ".join(
            term.describe(tree, nested=True) for term in self.terms
        )
        return f"({text})" if nested else text


Term = TaxaCount | Combination


class PhyleticExpression(BaseModel):
    """A parsed ``phyletic_expression``. Mixed AND and OR need parentheses,
    because the site does not state which one binds first."""

    model_config = ConfigDict(frozen=True)

    root: Term

    @classmethod
    def parse(cls, text: str) -> PhyleticExpression:
        if not text.strip():
            _refuse(f"{text!r} is empty.")
        tokens = _tokens(text)
        root, rest = _expression(tokens, text)
        if rest:
            _refuse(f"In {text!r}, a ')' closes nothing.")
        return cls(root=root)

    def render(self) -> str:
        return self.root.render()

    def describe(self, tree: PhyleticTree) -> str:
        return self.root.describe(tree)

    def units(self) -> list[TaxaCount]:
        found: list[TaxaCount] = []
        pending: list[Term] = [self.root]
        while pending:
            term = pending.pop(0)
            if isinstance(term, TaxaCount):
                found.append(term)
            else:
                pending[:0] = term.terms
        return found

    def codes(self) -> list[str]:
        return list(dict.fromkeys(code for unit in self.units() for code in unit.codes))


def check_expression(expression: PhyleticExpression, tree: PhyleticTree) -> None:
    """Refuse a code the taxonomy does not carry, and a unit every group meets or
    none can, which states no constraint. ``ALL`` is the whole tree."""
    validate_phyletic_codes(
        expression.codes(),
        tree.codes() | {PHYLETIC_ROOT_CODE},
        param_name=PHYLETIC_EXPRESSION_PARAM,
    )
    for unit in expression.units():
        span = len(tree.species_under(unit.codes)) if unit.taxa else None
        if _decides_nothing(unit, span):
            spanned = f" over {span} taxa" if span is not None else ""
            _refuse(
                f"{unit.render()}{spanned} is true of every group or of none, so "
                f"it states no constraint.",
                title="phyletic_expression holds a unit that decides nothing",
            )


def _decides_nothing(unit: TaxaCount, span: int | None) -> bool:
    match unit.op:
        case ">=":
            return unit.count == 0 or (span is not None and unit.count > span)
        case "<=":
            return span is not None and unit.count >= span
        case "<":
            return unit.count == 0 or (span is not None and unit.count > span)
        case ">":
            return span is not None and unit.count >= span
        case "=":
            return span is not None and unit.count > span


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


def _term(tokens: list[_Token], text: str) -> tuple[Term, list[_Token]]:
    if not tokens:
        _refuse(f"{text!r} ends where a unit belongs.")
    kind, value = tokens[0]
    if kind == "unit" and isinstance(value, TaxaCount):
        return value, tokens[1:]
    if kind == "open":
        inner, rest = _expression(tokens[1:], text)
        if not rest or rest[0][0] != "close":
            _refuse(f"In {text!r}, a '(' is never closed.")
        return inner, rest[1:]
    _refuse(f"In {text!r}, {value!r} stands where a unit belongs.")


def _expression(tokens: list[_Token], text: str) -> tuple[Term, list[_Token]]:
    first, rest = _term(tokens, text)
    terms: list[Term] = [first]
    join: str | None = None
    while rest and rest[0][0] != "close":
        kind, value = rest[0]
        if kind != "join":
            _refuse(f"In {text!r}, AND or OR joins two units.")
        if join is not None and value != join:
            _refuse(
                f"In {text!r}, AND and OR stand side by side. State which one "
                "binds first with parentheses."
            )
        join = str(value)
        if len(rest) == 1:
            _refuse(f"{text!r} ends after {join}.")
        term, rest = _term(rest[1:], text)
        terms.append(term)
    if join is None:
        return first, rest
    return Combination(join="AND" if join == "AND" else "OR", terms=tuple(terms)), rest
