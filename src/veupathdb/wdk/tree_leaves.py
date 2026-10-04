"""Tree parameter values as the leaves WDK counts under ``countOnlyLeaves``.

WDK counts only the selected leaves of such a parameter, so a parent term alone
selects nothing (WDK-VOCAB-002). A parent is sent as every leaf under it.
"""

import json
from collections.abc import Sequence

from veupathdb.domain.parameters.value_utils import decode_values
from veupathdb.domain.parameters.wdk_vocab import (
    FAKE_ALL_SENTINEL,
    WDKTreeBoxVocabNode,
    collect_leaf_terms,
    find_vocab_node,
)
from veupathdb.logging import get_logger
from veupathdb.wdk.wdk_parameters import WDKParameter

logger = get_logger(__name__)

_PICKS = ("multi-pick-vocabulary", "single-pick-vocabulary")


def leaves_of_tree_values(
    wdk_params: Sequence[WDKParameter],
    params: dict[str, str],
    search_name: str,
) -> dict[str, str]:
    """The parameters with each parent term of a countOnlyLeaves tree as its leaves."""
    result = dict(params)
    for spec in wdk_params:
        if spec.name not in result:
            continue
        if spec.type not in _PICKS:
            continue
        if not spec.count_only_leaves:
            continue
        vocab = spec.vocabulary
        if not isinstance(vocab, WDKTreeBoxVocabNode):
            continue
        expanded = _leaves_of(vocab, result[spec.name])
        if expanded is not None:
            original_values = decode_values(result[spec.name], spec.name)
            if expanded != [str(v) for v in original_values]:
                logger.info(
                    "Expanded tree param to leaves",
                    param=spec.name,
                    search=search_name,
                    original_count=len(original_values),
                    expanded_count=len(expanded),
                )
                result[spec.name] = json.dumps(expanded)
    return result


def _leaves_of(vocab: WDKTreeBoxVocabNode, raw_value: str) -> list[str] | None:
    values = decode_values(raw_value, "tree-param")
    if not values:
        return None

    expanded: list[str] = []
    seen: set[str] = set()
    for val in values:
        val_str = str(val)
        # The synthetic root names no real term. Expanding it would select
        # the whole vocabulary instead of failing.
        node = None if val_str == FAKE_ALL_SENTINEL else find_vocab_node(vocab, val_str)
        if node is None:
            if val_str not in seen:
                expanded.append(val_str)
                seen.add(val_str)
            continue
        leaves = collect_leaf_terms(node)
        if not leaves:
            if val_str not in seen:
                expanded.append(val_str)
                seen.add(val_str)
        else:
            for leaf in leaves:
                if leaf not in seen:
                    expanded.append(leaf)
                    seen.add(leaf)
    return expanded
