"""One WDK exchange reported as data, including the failures.

The ordinary client turns a 4xx into an exception, which is right for the
application and wrong for a caller whose subject is the response itself.
"""

from __future__ import annotations

import json

from pydantic import ConfigDict, JsonValue

from veupathdb.model import CamelModel


class WDKProbe(CamelModel):
    """What WDK answered: the status, the content type and the body."""

    model_config = ConfigDict(frozen=True)

    method: str
    url: str
    status: int
    content_type: str = ""
    text: str = ""

    def json_body(self) -> JsonValue | None:
        """The body parsed as JSON, or None when the body is prose.

        WDK serves JSON under ``text/plain``, so the content type decides
        nothing here.
        """
        if not self.text.strip():
            return None
        try:
            parsed: JsonValue = json.loads(self.text)
        except json.JSONDecodeError:
            return None
        return parsed
