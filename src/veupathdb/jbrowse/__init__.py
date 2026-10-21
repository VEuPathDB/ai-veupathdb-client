"""Reads a site's JBrowse service: track lists, genome sequence and tabix tracks."""

from veupathdb.jbrowse.client import JBrowseClient, TrackKind
from veupathdb.jbrowse.errors import (
    JBrowseError,
    SequenceNotIndexedError,
    TrackReadError,
)
from veupathdb.jbrowse.factory import close_all_jbrowse_clients, get_jbrowse_client
from veupathdb.jbrowse.genome import (
    FaiEntry,
    GenomeIndexError,
    GenomeReader,
    GenomeWindow,
    data_prefix,
    parse_fai,
)
from veupathdb.jbrowse.gff import GffFeature, parse_gff_line
from veupathdb.jbrowse.models import TrackConfig, TrackList
from veupathdb.jbrowse.tabix import TabixReader

__all__ = [
    "FaiEntry",
    "GenomeIndexError",
    "GenomeReader",
    "GenomeWindow",
    "GffFeature",
    "JBrowseClient",
    "JBrowseError",
    "SequenceNotIndexedError",
    "TabixReader",
    "TrackConfig",
    "TrackKind",
    "TrackList",
    "TrackReadError",
    "close_all_jbrowse_clients",
    "data_prefix",
    "get_jbrowse_client",
    "parse_fai",
    "parse_gff_line",
]
