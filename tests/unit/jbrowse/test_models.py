from veupathdb.jbrowse.models import SubTrack, TrackConfig, TrackList


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


def test_a_tabix_track_reads_its_index_beside_its_data() -> None:
    track = TrackConfig.model_validate(
        {
            "storeClass": "JBrowse/Store/SeqFeature/GFF3Tabix",
            "urlTemplate": "/a/service/jbrowse/store?data=PcynomolgiM%2FgenomeBrowser%2Fgff%2FunifiedIntronJunction.gff.gz",
        }
    )
    assert track.index_path == (
        "PcynomolgiM/genomeBrowser/gff/unifiedIntronJunction.gff.gz.tbi"
    )
    assert track.reads_with_tabix


def test_a_tbi_url_template_names_the_index() -> None:
    track = TrackConfig.model_validate(
        {
            "urlTemplate": "/a/service/jbrowse/store?data=org%2Fx.gff.gz",
            "tbiUrlTemplate": "/a/service/jbrowse/store?data=org%2Findex%2Fx.tbi",
        }
    )
    assert track.index_path == "org/index/x.tbi"


def test_a_track_that_is_not_tabix_says_so() -> None:
    track = TrackConfig.model_validate(
        {"storeClass": "JBrowse/Store/SeqFeature/BigWig", "urlTemplate": "/s?data=a"}
    )
    assert not track.reads_with_tabix


def test_a_multi_track_lists_its_subtracks_from_its_url_templates() -> None:
    track = TrackConfig.model_validate(
        {
            "key": "Example study coverage",
            "storeClass": "MultiBigWig/Store/SeqFeature/MultiBigWig",
            "urlTemplates": [
                {
                    "url": "/a/service/jbrowse/store?data=org1%2Fbigwig%2Fs1%2Fforward.bw",
                    "name": "sample 1 (+)",
                    "color": "blue",
                },
                {
                    "url": "/a/service/jbrowse/store?data=org1%2Fbigwig%2Fs1%2Freverse.bw",
                    "name": "sample 1 (-)",
                },
            ],
        }
    )
    assert track.subtracks() == [
        SubTrack(
            url="/a/service/jbrowse/store?data=org1%2Fbigwig%2Fs1%2Fforward.bw",
            name="sample 1 (+)",
        ),
        SubTrack(
            url="/a/service/jbrowse/store?data=org1%2Fbigwig%2Fs1%2Freverse.bw",
            name="sample 1 (-)",
        ),
    ]
    assert [sub.data_path for sub in track.subtracks()] == [
        "org1/bigwig/s1/forward.bw",
        "org1/bigwig/s1/reverse.bw",
    ]
    assert track.reads_with_bigwig


def test_a_single_track_is_its_own_one_subtrack() -> None:
    track = TrackConfig.model_validate(
        {
            "label": "s2_unique",
            "key": "Example sample 2",
            "storeClass": "JBrowse/Store/SeqFeature/BigWig",
            "urlTemplate": "/a/service/jbrowse/store?data=org1%2Fbigwig%2Fs2.bw",
        }
    )
    assert track.subtracks() == [
        SubTrack(
            url="/a/service/jbrowse/store?data=org1%2Fbigwig%2Fs2.bw",
            name="Example sample 2",
        )
    ]
    assert track.reads_with_bigwig


def test_a_track_without_a_key_names_its_subtrack_by_its_label() -> None:
    track = TrackConfig.model_validate({"label": "s3", "urlTemplate": "/s?data=x.bw"})
    assert [sub.name for sub in track.subtracks()] == ["s3"]


def test_a_track_with_no_url_has_no_subtrack() -> None:
    track = TrackConfig.model_validate({"label": "s4"})
    assert track.subtracks() == []
    assert not track.reads_with_bigwig


def test_a_tabix_track_does_not_read_as_bigwig() -> None:
    track = TrackConfig.model_validate(
        {"storeClass": "JBrowse/Store/SeqFeature/GFF3Tabix"}
    )
    assert not track.reads_with_bigwig
