from veupathdb.testing.wire.drift import DriftRow, compare, render_report


def test_counts_shape_and_status_are_named() -> None:
    old = b'{"meta": {"totalCount": 10}, "records": [{"id": 1}], "a": 1}'
    new = b'{"meta": {"totalCount": 12}, "records": [{"id": 1}, {"id": 2}], "b": "x"}'

    row = compare("c", [("GET /x", 200, 200, old, new), ("GET /y", 200, 500, b"", b"")])

    assert row.counts == ["GET /x meta.totalCount 10 -> 12", "GET /x records 1 -> 2"]
    assert row.shapes == ["GET /x removed $.a", "GET /x added $.b"]
    assert row.statuses == ["GET /y 200 -> 500"]


def test_ids_are_not_drift() -> None:
    row = compare("c", [("POST /s", 200, 200, b'{"id": 1}', b'{"id": 2}')])
    assert row.changed() is False


def test_the_report_leads_with_totals_and_shape_changes() -> None:
    rows = [
        DriftRow(cassette="same"),
        DriftRow(cassette="counted", counts=["GET /x estimatedSize 10 -> 12"]),
        DriftRow(cassette="reshaped", shapes=["GET /x added $.b"]),
    ]
    report = render_report(rows, {"qa.plasmodb.org": (68, 69)}, [])

    lines = report.splitlines()
    assert lines[0] == "# WDK refresh"
    assert (
        "3 tests: 1 unchanged, 1 with count changes only, 1 with shape or status changes."
        in lines
    )
    assert "- qa.plasmodb.org: build 68 -> 69" in lines
    assert lines.index("### reshaped") < lines.index(
        "| counted | GET /x estimatedSize 10 -> 12 |"
    )
