import pytest

from veupathdb.jbrowse.errors import TrackReadError
from veupathdb.jbrowse.gff import parse_gff_line

JUNCTION = (
    "PcyM_07\tVEuPathDB\tintronJunction\t1381746\t1381886\t1436\t+\t.\t"
    "contained=1;matchesGeneStrand=1;isrpm=865.47;totalscore=1436;"
    "intronpercent=78.49;annotatedintron=No;genesourceid=PcyM_0736700;"
    "evidence=Strong Evidence;ID=PcyM_07_1381746_1381886_0"
)


def test_a_junction_line_reads_its_columns() -> None:
    feature = parse_gff_line(JUNCTION)
    assert (feature.seqid, feature.source, feature.kind) == (
        "PcyM_07",
        "VEuPathDB",
        "intronJunction",
    )
    assert (feature.start, feature.end, feature.score) == (1381746, 1381886, 1436.0)
    assert (feature.strand, feature.phase) == ("+", None)


def test_a_junction_line_reads_its_attributes() -> None:
    feature = parse_gff_line(JUNCTION)
    assert feature.attributes["evidence"] == ("Strong Evidence",)
    assert feature.attributes["genesourceid"] == ("PcyM_0736700",)
    assert feature.attributes["ID"] == ("PcyM_07_1381746_1381886_0",)
    assert len(feature.attributes) == 9


def test_an_empty_attribute_value_holds_no_value() -> None:
    line = JUNCTION.replace("genesourceid=PcyM_0736700", "genesourceid=")
    assert parse_gff_line(line).attributes["genesourceid"] == ()


def test_escaped_attribute_text_is_decoded() -> None:
    line = JUNCTION.replace("evidence=Strong Evidence", "Note=a%3Bb%3Dc%2C d")
    assert parse_gff_line(line).attributes["Note"] == ("a;b=c, d",)


def test_gff3_column_9_splits_values_on_a_comma_before_it_decodes_them() -> None:
    line = JUNCTION.replace("evidence=Strong Evidence", "Parent=g1,g2;Note=x%2Cy")
    attributes = parse_gff_line(line).attributes
    assert (attributes["Parent"], attributes["Note"]) == (("g1", "g2"), ("x,y",))


def test_a_repeated_attribute_is_refused() -> None:
    with pytest.raises(TrackReadError, match="ID"):
        parse_gff_line(JUNCTION + ";ID=other")


def test_a_trailing_separator_adds_no_attribute() -> None:
    assert len(parse_gff_line(JUNCTION + ";").attributes) == 9


def test_a_missing_score_and_a_phase_are_read() -> None:
    columns = JUNCTION.split("\t")
    columns[5], columns[7] = ".", "2"
    feature = parse_gff_line("\t".join(columns))
    assert (feature.score, feature.phase) == (None, 2)


def test_a_line_without_nine_columns_is_refused() -> None:
    with pytest.raises(TrackReadError, match="9 columns"):
        parse_gff_line("PcyM_07\tVEuPathDB\tintronJunction\t1\t2")


def test_a_feature_that_ends_before_it_starts_is_refused() -> None:
    line = JUNCTION.replace("1381746\t1381886", "1381886\t1381746")
    with pytest.raises(TrackReadError, match="ends before it starts"):
        parse_gff_line(line)


def test_a_coordinate_that_is_not_a_number_is_refused() -> None:
    with pytest.raises(TrackReadError, match="start"):
        parse_gff_line(JUNCTION.replace("1381746\t", "x\t", 1))


def test_an_attribute_without_a_value_separator_is_refused() -> None:
    with pytest.raises(TrackReadError, match="contained"):
        parse_gff_line(JUNCTION.replace("contained=1", "contained"))


def test_an_unknown_strand_is_refused() -> None:
    columns = JUNCTION.split("\t")
    columns[6] = "x"
    with pytest.raises(TrackReadError, match="strand"):
        parse_gff_line("\t".join(columns))
