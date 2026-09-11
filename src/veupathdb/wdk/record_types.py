"""The match from a record type string to one WDK record type."""

from veupathdb.wdk.wdk_models import WDKRecordType


def resolve_record_type(
    available_types: list[WDKRecordType],
    user_input: str,
) -> str | None:
    """The ``url_segment`` of the record type a string names, or ``None``.

    The string is matched, ignoring case and surrounding space, against
    ``url_segment``, then ``full_name``, then ``display_name``. A display name
    that two record types share names neither of them.
    """
    normalized = user_input.strip().lower()

    for record_type in available_types:
        if record_type.url_segment.strip().lower() == normalized:
            return record_type.url_segment or None

    for record_type in available_types:
        if (
            record_type.full_name
            and record_type.full_name.strip().lower() == normalized
        ):
            return record_type.url_segment or None

    display_matches = [
        record_type
        for record_type in available_types
        if record_type.display_name
        and record_type.display_name.strip().lower() == normalized
    ]
    if len(display_matches) == 1:
        return display_matches[0].url_segment or None

    return None
