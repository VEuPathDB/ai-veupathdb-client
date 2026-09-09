"""The prefix that tags a helper strategy is the deployment's, not the client's."""

from __future__ import annotations

from collections.abc import Generator

import pytest

from veupathdb.settings import (
    DEFAULT_INTERNAL_STRATEGY_NAME_PREFIX,
    VEuPathDBSettings,
    use_veupathdb_settings_source,
    veupathdb_settings_source,
)
from veupathdb.wdk.strategy_api import (
    is_internal_wdk_strategy_name,
    strip_internal_wdk_strategy_name,
    tag_internal_wdk_strategy_name,
)

_HOST_PREFIX = "__host_internal__:"


@pytest.fixture
def host_prefix() -> Generator[None]:
    previous = veupathdb_settings_source()
    stated = VEuPathDBSettings(veupathdb_internal_strategy_name_prefix=_HOST_PREFIX)
    use_veupathdb_settings_source(lambda: stated)
    yield
    use_veupathdb_settings_source(previous)


def test_the_default_prefix_names_no_product() -> None:
    assert DEFAULT_INTERNAL_STRATEGY_NAME_PREFIX == "__internal__:"
    assert "pathfinder" not in DEFAULT_INTERNAL_STRATEGY_NAME_PREFIX


def test_a_process_that_states_no_prefix_tags_with_the_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No settings source and no variable: the helpers tag with ``__internal__:``."""
    monkeypatch.delenv("VEUPATHDB_INTERNAL_STRATEGY_NAME_PREFIX", raising=False)
    use_veupathdb_settings_source(VEuPathDBSettings)

    assert tag_internal_wdk_strategy_name("step counts") == "__internal__:step counts"
    assert is_internal_wdk_strategy_name("__internal__:step counts")
    assert strip_internal_wdk_strategy_name("__internal__:step counts") == "step counts"


def test_the_prefix_is_read_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VEUPATHDB_INTERNAL_STRATEGY_NAME_PREFIX", "__acme__:")

    settings = VEuPathDBSettings()

    assert settings.veupathdb_internal_strategy_name_prefix == "__acme__:"


def test_the_host_prefix_tags_the_name(host_prefix: None) -> None:
    del host_prefix

    assert tag_internal_wdk_strategy_name("step counts") == f"{_HOST_PREFIX}step counts"


def test_tagging_a_tagged_name_changes_nothing(host_prefix: None) -> None:
    del host_prefix
    once = tag_internal_wdk_strategy_name("step counts")

    assert tag_internal_wdk_strategy_name(once) == once


def test_the_host_prefix_recognises_and_strips_its_own(host_prefix: None) -> None:
    del host_prefix

    assert is_internal_wdk_strategy_name(f"{_HOST_PREFIX}control test")
    assert strip_internal_wdk_strategy_name(f"{_HOST_PREFIX}control test") == (
        "control test"
    )


def test_a_name_under_another_prefix_is_not_internal(host_prefix: None) -> None:
    """A deployment recognises the strategies it wrote, and no others."""
    del host_prefix

    assert not is_internal_wdk_strategy_name("__internal__:control test")
    assert strip_internal_wdk_strategy_name("__internal__:x") == "__internal__:x"


def test_no_name_is_not_internal(host_prefix: None) -> None:
    del host_prefix

    assert not is_internal_wdk_strategy_name(None)
    assert not is_internal_wdk_strategy_name("")
