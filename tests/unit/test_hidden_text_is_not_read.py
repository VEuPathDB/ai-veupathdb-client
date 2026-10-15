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
