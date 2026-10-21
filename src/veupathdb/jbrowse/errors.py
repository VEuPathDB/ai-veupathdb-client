"""The errors a JBrowse read raises."""

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


class TrackReadError(VEuPathDBError[VEuPathDBErrorCode]):
    def __init__(
        self,
        detail: str,
        *,
        title: str = "Genome browser track unreadable",
        status: int = 502,
    ) -> None:
        super().__init__(
            code=VEuPathDBErrorCode.DATA_PARSING_ERROR,
            title=title,
            status=status,
            detail=detail,
        )


class SequenceNotIndexedError(TrackReadError):
    def __init__(self, data_path: str, seqid: str) -> None:
        super().__init__(
            f"the index of {data_path} names no sequence {seqid}",
            title="Sequence not in the track index",
            status=404,
        )
        self.data_path = data_path
        self.seqid = seqid
