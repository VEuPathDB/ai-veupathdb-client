from veupathdb.jbrowse.models import TrackConfig, TrackList


def test_a_track_reads_its_data_path_from_the_store_query() -> None:
    track = TrackConfig.model_validate(
        {
            "label": "Annotated Transcripts",
            "storeClass": "JBrowse/Store/SeqFeature/GFF3Tabix",
            "urlTemplate": "/a/service/jbrowse/store?data=pfal3D7%2FgenomeAndProteome%2Fgff%2Fannotated_transcripts.gff.gz",
            "metadata": {"subcategory": "Gene Models", "rank": 1},
            "unexpected": {"ignored": True},
        }
    )
    assert (
        track.data_path == "pfal3D7/genomeAndProteome/gff/annotated_transcripts.gff.gz"
    )
    assert track.store_class.endswith("GFF3Tabix")


def test_a_track_without_a_store_query_uses_its_path() -> None:
    track = TrackConfig.model_validate(
        {"urlTemplate": "/a/jbrowse/tracks/x/{refseq}.json"}
    )
    assert track.data_path == "/a/jbrowse/tracks/x/{refseq}.json"


def test_a_track_list_keeps_every_track() -> None:
    listed = TrackList.model_validate(
        {"tracks": [{"label": "a"}, {"label": "b"}], "include": "x.json"}
    )
    assert [t.label for t in listed.tracks] == ["a", "b"]


def test_a_store_query_is_decoded_once() -> None:
    track = TrackConfig.model_validate({"urlTemplate": "/s?data=a%2525b"})
    assert track.data_path == "a%25b"
