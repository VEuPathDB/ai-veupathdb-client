"""Reads a site's JBrowse service: track lists, genome sequence, tabix and bigWig tracks."""

from veupathdb.jbrowse.bigwig import (
    BIGWIG_BYTE_ORDER,
    BIGWIG_MAX_BLOCK_BYTES,
    BIGWIG_MAX_BLOCKS,
    BIGWIG_MAX_CHROM_TREE_BYTES,
    BIGWIG_MAX_NODE_ITEMS,
    BIGWIG_MAX_REGION,
    BIGWIG_MAX_RTREE_DEPTH,
    BIGWIG_MAX_ZOOM_LEVELS,
    BigWigReader,
    BigWigSummary,
)
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
from veupathdb.jbrowse.models import SubTrack, TrackConfig, TrackList
from veupathdb.jbrowse.tabix import TabixReader

__all__ = [
    "BIGWIG_BYTE_ORDER",
    "BIGWIG_MAX_BLOCKS",
    "BIGWIG_MAX_BLOCK_BYTES",
    "BIGWIG_MAX_CHROM_TREE_BYTES",
    "BIGWIG_MAX_NODE_ITEMS",
    "BIGWIG_MAX_REGION",
    "BIGWIG_MAX_RTREE_DEPTH",
    "BIGWIG_MAX_ZOOM_LEVELS",
    "BigWigReader",
    "BigWigSummary",
    "FaiEntry",
    "GenomeIndexError",
    "GenomeReader",
    "GenomeWindow",
    "GffFeature",
    "JBrowseClient",
    "JBrowseError",
    "SequenceNotIndexedError",
    "SubTrack",
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
