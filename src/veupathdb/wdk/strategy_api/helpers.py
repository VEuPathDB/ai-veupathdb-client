"""Module-level helpers for WDK strategy operations.

Internal strategy name tagging utilities and shared constants.
"""

import pydantic

from veupathdb.wdk.client import VEuPathDBClient
from veupathdb.wdk.wdk_models import WDKUserInfo

# Internal (Pathfinder-created) WDK strategies.
#
# WDK doesn't support arbitrary metadata on a strategy. To reliably identify
# "internal helper" strategies (step counts, etc.) later, we tag the WDK name
# with a reserved prefix. This avoids incorrectly treating *all* unsaved
# strategies (`isSaved=false`) as internal.
PATHFINDER_INTERNAL_STRATEGY_NAME_PREFIX = "__pathfinder_internal__:"

# Use current user session (guest or authenticated)
CURRENT_USER = "current"


def is_internal_wdk_strategy_name(name: str | None) -> bool:
    """Check if a WDK strategy name is a Pathfinder internal helper strategy.

    Internal strategies are used for control tests and step counts.
    They are tagged with ``__pathfinder_internal__:`` prefix.

    :param name: WDK strategy name or None.
    :returns: True if the name indicates an internal strategy.
    """
    return bool(name) and str(name).startswith(PATHFINDER_INTERNAL_STRATEGY_NAME_PREFIX)


def tag_internal_wdk_strategy_name(name: str) -> str:
    """Add the internal strategy name prefix if not already present."""
    if name.startswith(PATHFINDER_INTERNAL_STRATEGY_NAME_PREFIX):
        return name
    return f"{PATHFINDER_INTERNAL_STRATEGY_NAME_PREFIX}{name}"


def strip_internal_wdk_strategy_name(name: str) -> str:
    """Remove the internal strategy name prefix if present.

    :param name: WDK strategy name (may include internal prefix).
    :returns: Display name without the ``__pathfinder_internal__:`` prefix.
    """
    if name.startswith(PATHFINDER_INTERNAL_STRATEGY_NAME_PREFIX):
        return name[len(PATHFINDER_INTERNAL_STRATEGY_NAME_PREFIX) :]
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


__all__ = [
    "CURRENT_USER",
    "PATHFINDER_INTERNAL_STRATEGY_NAME_PREFIX",
    "is_internal_wdk_strategy_name",
    "resolve_wdk_user_id",
    "strip_internal_wdk_strategy_name",
    "tag_internal_wdk_strategy_name",
]
