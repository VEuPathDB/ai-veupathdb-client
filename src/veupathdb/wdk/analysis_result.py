"""Names the absence of a step-analysis result, which WDK reports as 204."""

from __future__ import annotations

from veupathdb.errors import VEuPathDBError, VEuPathDBErrorCode


class WDKAnalysisNotReadyError(VEuPathDBError):
    """WDK holds no execution result for the analysis instance."""

    def __init__(self, step_id: int, analysis_id: int) -> None:
        super().__init__(
            code=VEuPathDBErrorCode.WDK_ERROR,
            title="Step analysis result is not available",
            status=502,
            detail=(
                f"WDK has no result for analysis {analysis_id} on step {step_id}. "
                f"The run did not finish, or its cached result was discarded."
            ),
        )
