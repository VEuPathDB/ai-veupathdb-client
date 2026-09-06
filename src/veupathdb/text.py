"""Pure text utilities."""

import re


def strip_html_tags(value: str | None) -> str:
    """Strip HTML tags from a string.

    Site-search highlights matches with ``<em>`` tags. This removes all tags.
    """
    return re.sub(r"</?[^>]+>", "", value or "").strip()
