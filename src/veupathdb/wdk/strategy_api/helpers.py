"""Module-level helpers for WDK strategy operations.

Internal strategy name tagging utilities and shared constants.
"""

import pydantic

from veupathdb.settings import get_veupathdb_settings
from veupathdb.wdk.client import VEuPathDBClient
from veupathdb.wdk.wdk_models import WDKUserInfo

# Use current user session (guest or authenticated)
CURRENT_USER = "current"


def _internal_prefix() -> str:
    """The prefix this deployment tags its own helper strategies with."""
    return get_veupathdb_settings().veupathdb_internal_strategy_name_prefix


def is_internal_wdk_strategy_name(name: str | None) -> bool:
    """Check if a WDK strategy name is an internal helper strategy.

    WDK carries no metadata on a strategy, so a helper strategy for a step
    count or a control test is tagged by a reserved prefix on its name. An
    unsaved strategy is not internal by itself.

    :param name: WDK strategy name or None.
    :returns: True if the name carries this deployment's internal prefix.
    """
    return bool(name) and str(name).startswith(_internal_prefix())


def tag_internal_wdk_strategy_name(name: str) -> str:
    """Add the internal strategy name prefix if not already present."""
    prefix = _internal_prefix()
    if name.startswith(prefix):
        return name
    return f"{prefix}{name}"


def strip_internal_wdk_strategy_name(name: str) -> str:
    """Remove the internal strategy name prefix if present.

    :param name: WDK strategy name (may include the internal prefix).
    :returns: Display name without the prefix.
    """
    prefix = _internal_prefix()
    if name.startswith(prefix):
        return name[len(prefix) :]
    return name


async def resolve_wdk_user_id(client: VEuPathDBClient) -> str | None:
    """Resolve the concrete WDK user ID from a ``/users/current`` call.

    This is the one call that may name the alias. Every later request carries
    the numeric id, which an ownership check can refuse.

    :returns: Resolved user ID string, or ``None`` if resolution failed.
    """
    me = await client.get("/users/current")
    try:
        user = WDKUserInfo.model_validate(me)
        return str(user.id)
    except pydantic.ValidationError:
        return None
