"""Text a site hides is not part of the text a reader gets."""

from veupathdb import strip_html_tags


def test_an_evalue_drops_the_sort_key_the_site_hides() -> None:
    """qa.orthomcl.org writes a BLAST hit's E-value after a hidden sort key."""
    assert (
        strip_html_tags('<span style="display:none">-161 7.0</span>7.0E-161')
        == "7.0E-161"
    )


def test_a_hidden_element_written_with_spaces_is_dropped() -> None:
    assert strip_html_tags("<div style='color: red; display: none'>x</div>y") == "y"


def test_a_highlight_keeps_its_text() -> None:
    assert strip_html_tags("<em>kinase</em> domain") == "kinase domain"


def test_a_clade_count_keeps_one_line_per_clade_and_no_indent() -> None:
    """qa.orthomcl.org indents each clade of a group's count with tabs and spaces."""
    assert (
        strip_html_tags(
            "FUNGI\n\t\t\t       Microsporidia: 49 / 51\n"
            "\t\t\t       Basidiomycota: 48 / 48\n\t\t\t  \n\t\t\t  "
        )
        == "FUNGI\nMicrosporidia: 49 / 51\nBasidiomycota: 48 / 48"
    )


def test_a_run_of_spaces_inside_a_line_reads_as_one() -> None:
    assert strip_html_tags("zinc \t  transporter") == "zinc transporter"
