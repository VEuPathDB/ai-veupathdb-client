"""Canonicalize parameter values using WDK parameter specs.

The canonicalizer takes a typed ``dict[str, ParamValue]`` (the discriminated
union over the 11 WDK parameter types), rewrites each value into the form WDK
will accept, and returns a fresh ``dict[str, ParamValue]``. Vocabulary matching
replaces fuzzy input with the declared term, a branch selection expands to its
leaf set, and an open range takes the parameter's own limit. Whether a value
WDK can read is one WDK accepts is WDK's verdict, not this module's.
"""

from dataclasses import dataclass

from pydantic import JsonValue

from veupathdb.domain.parameters.specs import ParamSpecNormalized
from veupathdb.domain.parameters.value_codec import (
    as_param_kind,
    from_decoded,
    to_decoded,
)
from veupathdb.domain.parameters.value_utils import (
    decode_single_value,
    decode_values,
)
from veupathdb.domain.parameters.values import (
    DateRangeValue,
    NumberRangeValue,
    ParamValue,
)
from veupathdb.domain.parameters.vocab_utils import match_vocab_value
from veupathdb.domain.parameters.wdk_vocab import (
    FAKE_ALL_SENTINEL,
    WDKVocabulary,
    collect_leaf_terms,
    find_vocab_node,
)
from veupathdb.errors import ValidationError
from veupathdb.json_types import JSONObject

_MULTI_PICK = "multi-pick-vocabulary"
_SINGLE_PICK = "single-pick-vocabulary"
_RANGE_TYPES = frozenset({"number-range", "date-range"})
_SCALAR_TYPES = frozenset({"number", "date", "timestamp", "string"})
_RANGE_PAIR_LENGTH = 2


def _stringify(value: JsonValue) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _refuse(
    spec: ParamSpecNormalized, reason: str, value: JsonValue
) -> ValidationError:
    return ValidationError(
        title="Invalid parameter value",
        detail=f"Parameter '{spec.name}' {reason}.",
        errors=[{"param": spec.name, "value": value}],
    )


def close_open_range(
    value: NumberRangeValue | DateRangeValue,
    spec: ParamSpecNormalized,
) -> NumberRangeValue | DateRangeValue:
    """Fill a range's open end from the parameter's own declared limit.

    WDK reads both ends and refuses an object missing one. A limit the
    parameter declares is not a guess; without one the value is left as it is
    so WDK refuses it by name.
    """
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


def _range_object(spec: ParamSpecNormalized, value: JsonValue) -> JSONObject:
    """A range as the ``{min, max}`` object WDK reads.

    WDK refuses a two-element array with the same message it gives a scalar,
    naming neither end, so the pair becomes the object here.
    """
    if isinstance(value, dict):
        return value
    if isinstance(value, (list, tuple)) and len(value) == _RANGE_PAIR_LENGTH:
        return {"min": value[0], "max": value[1]}
    raise _refuse(spec, "must be a range", value)


def _scalar(spec: ParamSpecNormalized, value: JsonValue) -> str:
    """A scalar as its string form.

    A container has no scalar form: stringifying it would send WDK a value that
    reads as a Python repr, which a parameter with no regex accepts.
    """
    if isinstance(value, (list, dict, tuple, set)):
        raise _refuse(spec, "must be a scalar value", value)
    return _stringify(value)


def _input_dataset(spec: ParamSpecNormalized, value: JsonValue) -> str:
    if isinstance(value, list):
        if len(value) != 1:
            raise _refuse(spec, "must be a single value", value)
        return _stringify(value[0])
    return _stringify(value)


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
        the caller, and never a choice WDK made.
        """
        canonical: dict[str, ParamValue] = {}
        for name, value in (parameters or {}).items():
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
            decoded_value = self._canonicalize_value(spec, to_decoded(value))
            built = from_decoded(as_param_kind(spec.param_type), decoded_value)
            # WDK reads both ends of a range, so an open end takes the
            # parameter's own declared limit.
            canonical[name] = (
                close_open_range(built, spec)
                if isinstance(built, (NumberRangeValue, DateRangeValue))
                else built
            )
        return canonical

    def _canonicalize_value(
        self, spec: ParamSpecNormalized, value: JsonValue
    ) -> JsonValue:
        if value == FAKE_ALL_SENTINEL or (
            isinstance(value, (list, tuple, set))
            and any(v == FAKE_ALL_SENTINEL for v in value)
        ):
            raise ValidationError(
                title="Invalid parameter value",
                detail=f"Parameter '{spec.name}' does not accept '{FAKE_ALL_SENTINEL}'.",
                errors=[{"param": spec.name, "value": value}],
            )
        if spec.param_type == _MULTI_PICK:
            matched = [
                self._match(spec, _stringify(v))
                for v in decode_values(value, spec.name)
            ]
            return list(self._enforce_leaf_values(spec, matched))
        if spec.param_type == _SINGLE_PICK:
            return self._single_pick(spec, value)
        if spec.param_type in _RANGE_TYPES:
            return _range_object(spec, value)
        if spec.param_type in _SCALAR_TYPES:
            return _scalar(spec, value)
        if spec.param_type == "input-dataset":
            return _input_dataset(spec, value)
        return value

    def _match(self, spec: ParamSpecNormalized, value: str) -> str:
        return match_vocab_value(
            vocab=spec.vocabulary, param_name=spec.name, value=value
        )

    def _single_pick(self, spec: ParamSpecNormalized, value: JsonValue) -> str:
        decoded = decode_single_value(value, spec.name)
        if len(decoded) > 1:
            raise _refuse(spec, "allows only one value", value)
        selected = _stringify(decoded[0]) if decoded else ""
        if not selected:
            return ""
        return self._enforce_leaf_value(spec, self._match(spec, selected))

    # -- leaf enforcement (canonicalizer-only) --------------------------------

    def _enforce_leaf_values(
        self, spec: ParamSpecNormalized, values: list[str]
    ) -> list[str]:
        if not spec.count_only_leaves:
            return values
        enforced: list[str] = []
        seen: set[str] = set()
        for value in values:
            leaves = self._expand_leaf_terms_for_match(spec.vocabulary, value)
            if not leaves:
                raise _refuse(spec, "requires leaf selections", value)
            for leaf in leaves:
                if leaf in seen:
                    continue
                seen.add(leaf)
                enforced.append(leaf)
        return enforced

    def _enforce_leaf_value(self, spec: ParamSpecNormalized, value: str) -> str:
        if not spec.count_only_leaves or not value:
            return value
        leaf = self._find_leaf_term_for_match(spec.vocabulary, value)
        if not leaf:
            raise _refuse(spec, "requires leaf selections", value)
        return leaf

    def _expand_leaf_terms_for_match(
        self, vocabulary: WDKVocabulary | None, match: str
    ) -> list[str]:
        matched_node = find_vocab_node(vocabulary, match)
        if matched_node is None:
            return []
        return collect_leaf_terms(matched_node)

    def _find_leaf_term_for_match(
        self, vocabulary: WDKVocabulary | None, match: str
    ) -> str | None:
        matched_node = find_vocab_node(vocabulary, match)
        if matched_node is None or matched_node.children:
            return None
        return matched_node.data.term or None
