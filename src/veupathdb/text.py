"""Pure text utilities."""

import re

# A site writes a sort key into an element it hides, before the visible value.
_HIDDEN = re.compile(
    r"<(\w+)[^>]*\bstyle\s*=\s*[\"'][^\"']*display\s*:\s*none[^\"']*[\"'][^>]*>"
    r".*?</\1\s*>",
    re.IGNORECASE | re.DOTALL,
)


def strip_html_tags(value: str | None) -> str:
    """Strip HTML tags from a string, and the text of any element the site hides.

    Site-search highlights matches with ``<em>`` tags. This removes all tags.
    """
    return re.sub(r"</?[^>]+>", "", _HIDDEN.sub("", value or "")).strip()
