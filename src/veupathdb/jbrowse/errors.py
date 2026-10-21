"""The error a JBrowse read raises."""

from __future__ import annotations

from veupathdb.errors import VEuPathDBError, VEuPathDBErrorCode


class JBrowseError(VEuPathDBError[VEuPathDBErrorCode]):
    def __init__(self, method: str, url: str, upstream_status: int) -> None:
        super().__init__(
            code=VEuPathDBErrorCode.EXTERNAL_SERVICE_ERROR,
            title="Genome browser service error",
            status=502,
            detail=f"{method} {url} answered {upstream_status}",
        )
        self.method = method
        self.url = url
        self.upstream_status = upstream_status
