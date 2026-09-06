import pytest

from veupathdb.domain.parameters.vocab_utils import match_vocab_value
from veupathdb.domain.parameters.wdk_vocab import WDKVocabTerm, WDKVocabulary
from veupathdb.errors import ValidationError

DEAD_TOOL = "get_dependent_vocab"
LIVE_TOOL = "get_parameter_options"


def _vocab(*terms: str) -> WDKVocabulary:
    return [WDKVocabTerm(root=(t, t, None)) for t in terms]


def test_reject_guidance_names_the_live_tool_not_the_removed_one() -> None:
    # No suggestions match, so the guidance branch fires. It must point the
    # model at a tool that actually exists.
    with pytest.raises(ValidationError) as exc:
        match_vocab_value(
            vocab=_vocab("asexual blood stages", "midgut oocysts"),
            param_name="samples_de_comp_generic_deseq",
            value="gametocytes",
        )
    detail = exc.value.detail or ""
    assert DEAD_TOOL not in detail
    assert LIVE_TOOL in detail
