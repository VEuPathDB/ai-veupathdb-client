"""Canonicalize parameter values using WDK parameter specs.

The canonicalizer takes a typed ``dict[str, ParamValue]`` (the discriminated
union over the 11 WDK parameter types), rewrites each value into the form WDK
will accept, and returns a fresh ``dict[str, ParamValue]``. A stated pick
becomes the term its exact step names, or is refused with the ranked
candidates. A branch selection expands to its leaf set, and an open range takes
the parameter's own limit. Whether a value WDK can read is one WDK accepts is
WDK's verdict, not this module's.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from pydantic import JsonValue
from pydantic import ValidationError as PydanticValidationError

from veupathdb.domain.parameters.specs import ParamSpecNormalized, accepts_empty
from veupathdb.domain.parameters.stated import empty_refusal
from veupathdb.domain.parameters.value_codec import as_param_kind, from_wire, to_decoded
from veupathdb.domain.parameters.values import (
    DateRangeValue,
    HeldValue,
    MultiPickValue,
    NumberRangeValue,
    ParamValue,
    SinglePickValue,
    empty_value,
)
from veupathdb.domain.parameters.vocab_lookup import entries_or_refusal
from veupathdb.domain.parameters.wdk_vocab import (
    FAKE_ALL_SENTINEL,
    WDKVocabulary,
    find_vocab_node,
    flatten_vocab,
    leaf_terms,
)
from veupathdb.errors import ValidationError


def _refuse(
    spec: ParamSpecNormalized, reason: str, value: JsonValue
) -> ValidationError:
    return ValidationError(
        title="Invalid parameter value",
        detail=f"Parameter '{spec.name}' {reason}.",
        errors=[{"param": spec.name, "value": value}],
    )


def _read(spec: ParamSpecNormalized | None, raw: str) -> ParamValue:
    if spec is None:
        return HeldValue(wire=raw)
    try:
        return from_wire(as_param_kind(spec.param_type), raw)
    except PydanticValidationError, ValueError, TypeError:
        return HeldValue(wire=raw)


def close_open_range(
    value: NumberRangeValue | DateRangeValue,
    spec: ParamSpecNormalized,
) -> NumberRangeValue | DateRangeValue:
    """Fill a range's open end from the parameter's own declared limit.

    WDK reads both ends and refuses an object missing one. A limit the
    parameter declares is not a guess; without one the value is left as it is
    so WDK refuses it by name. The empty value stays empty.
    """
    if value.empty:
        return value
    if isinstance(value, NumberRangeValue):
        low = value.min if value.min is not None else spec.min
        high = value.max if value.max is not None else spec.max
        if low is None or high is None:
            return value
        return NumberRangeValue(min=low, max=high)
    low_date = value.min if value.min is not None else spec.min_date
    high_date = value.max if value.max is not None else spec.max_date
    if low_date is None or high_date is None:
        return value
    return DateRangeValue(min=low_date, max=high_date)


@dataclass(frozen=True)
class ParameterCanonicalizer:
    """Canonicalize ``ParamValue`` parameters using canonical parameter specs."""

    specs: dict[str, ParamSpecNormalized]

    def canonicalize(
        self,
        parameters: dict[str, ParamValue],
    ) -> dict[str, ParamValue]:
        """Canonicalize each value against its spec.

        An ``input-step`` value is left out: its value is structural, wired by
        the caller, and never a choice WDK made. A held value is WDK's own and
        goes through untouched.
        """
        canonical: dict[str, ParamValue] = {}
        for name, value in (parameters or {}).items():
            if isinstance(value, HeldValue):
                canonical[name] = value
                continue
            spec = self.specs.get(name)
            if not spec:
                available = sorted(self.specs.keys())
                raise ValidationError(
                    title="Unknown parameter",
                    detail=f"Parameter '{name}' does not exist for this search. Available parameters: {', '.join(available)}",
                    errors=[{"param": name, "value": to_decoded(value)}],
                )
            if spec.param_type == "input-step":
                continue
            if value.type != spec.param_type:
                raise _refuse(
                    spec,
                    f"takes a {spec.param_type} value, not a {value.type} value",
                    to_decoded(value),
                )
            if value == empty_value(value.type) and not accepts_empty(spec):
                raise empty_refusal(name, to_decoded(value))
            canonical[name] = self._canonicalize_value(spec, value)
        return canonical

    def held(self, wire: Mapping[str, str]) -> dict[str, ParamValue]:
        """Each value WDK holds, read as its kind and never refused or rewritten.

        A value no kind reads, and a value of a name with no spec, is held in
        its wire form. A declared ``input-step`` value is the wiring WDK makes.
        """
        held: dict[str, ParamValue] = {}
        for name, raw in wire.items():
            spec = self.specs.get(name)
            if spec is not None and spec.param_type == "input-step":
                continue
            held[name] = _read(spec, raw)
        return held

    def _canonicalize_value(
        self, spec: ParamSpecNormalized, value: ParamValue
    ) -> ParamValue:
        match value:
            case MultiPickValue(values=values):
                terms = self._terms(spec, values)
                return MultiPickValue(values=self._enforce_leaf_values(spec, terms))
            case SinglePickValue(value=""):
                return value
            case SinglePickValue(value=selected):
                [term] = self._terms(spec, [selected])
                return SinglePickValue(value=self._enforce_leaf_value(spec, term))
            case NumberRangeValue() | DateRangeValue():
                return close_open_range(value, spec)
            case _:
                return value

    def _terms(self, spec: ParamSpecNormalized, values: list[str]) -> list[str]:
        if FAKE_ALL_SENTINEL in values:
            raise _refuse(
                spec, f"does not accept '{FAKE_ALL_SENTINEL}'", FAKE_ALL_SENTINEL
            )
        return entries_or_refusal(spec.name, flatten_vocab(spec.vocabulary), values)

    # -- leaf enforcement (canonicalizer-only) --------------------------------

    def _enforce_leaf_values(
        self, spec: ParamSpecNormalized, values: list[str]
    ) -> list[str]:
        if not spec.count_only_leaves:
            return values
        leaves = leaf_terms(spec.vocabulary, values)
        if leaves is None:
            unknown = next(
                v for v in values if leaf_terms(spec.vocabulary, [v]) is None
            )
            raise _refuse(spec, "requires leaf selections", unknown)
        return leaves

    def _enforce_leaf_value(self, spec: ParamSpecNormalized, value: str) -> str:
        if not spec.count_only_leaves or not value:
            return value
        leaf = self._find_leaf_term_for_match(spec.vocabulary, value)
        if not leaf:
            raise _refuse(spec, "requires leaf selections", value)
        return leaf

    def _find_leaf_term_for_match(
        self, vocabulary: WDKVocabulary | None, match: str
    ) -> str | None:
        matched_node = find_vocab_node(vocabulary, match)
        if matched_node is None or matched_node.children:
            return None
        return matched_node.data.term or None
