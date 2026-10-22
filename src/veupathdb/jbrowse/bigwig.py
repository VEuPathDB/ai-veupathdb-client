from __future__ import annotations

import struct
import zlib
from collections.abc import Callable

from pydantic import BaseModel, ConfigDict

from veupathdb.jbrowse.client import JBrowseClient
from veupathdb.jbrowse.errors import SequenceNotIndexedError, TrackReadError
from veupathdb.jbrowse.region import genome_region

BIGWIG_MAX_REGION = 200_000
BIGWIG_MAX_RTREE_DEPTH = 4
BIGWIG_MAX_BLOCKS = 2
BIGWIG_MAX_CHROM_TREE_BYTES = 1_048_576
BIGWIG_MAX_BLOCK_BYTES = 262_144
BIGWIG_MAX_ZOOM_LEVELS = 10
BIGWIG_MAX_NODE_ITEMS = 256
BIGWIG_BYTE_ORDER = "<"

_BIGWIG_MAGIC = 0x888FFC26
_SWAPPED_MAGIC = int.from_bytes(_BIGWIG_MAGIC.to_bytes(4, "big"), "little")
_CHROM_TREE_MAGIC = 0x78CA8C91
_RTREE_MAGIC = 0x2468ACE0

_HEADER = struct.Struct(BIGWIG_BYTE_ORDER + "IHHQQQHHQQIQ")
_ZOOM_HEADER = struct.Struct(BIGWIG_BYTE_ORDER + "IIQQ")
_HEADER_READ = _HEADER.size + _ZOOM_HEADER.size * BIGWIG_MAX_ZOOM_LEVELS
_CHROM_TREE_HEADER = struct.Struct(BIGWIG_BYTE_ORDER + "IIIIQQ")
_CHROM_VALUE = struct.Struct(BIGWIG_BYTE_ORDER + "II")
_CHILD_OFFSET = struct.Struct(BIGWIG_BYTE_ORDER + "Q")
_RTREE_HEADER = struct.Struct(BIGWIG_BYTE_ORDER + "IIQIIIIQII")
_NODE_HEADER = struct.Struct(BIGWIG_BYTE_ORDER + "BBH")
_LEAF_ITEM = struct.Struct(BIGWIG_BYTE_ORDER + "IIIIQQ")
_BRANCH_ITEM = struct.Struct(BIGWIG_BYTE_ORDER + "IIIIQ")
_ROOT_READ = (
    _RTREE_HEADER.size + _NODE_HEADER.size + BIGWIG_MAX_NODE_ITEMS * _LEAF_ITEM.size
)
_SECTION_HEADER = struct.Struct(BIGWIG_BYTE_ORDER + "IIIIIBBH")
_BEDGRAPH_ITEM = struct.Struct(BIGWIG_BYTE_ORDER + "IIf")
_VARSTEP_ITEM = struct.Struct(BIGWIG_BYTE_ORDER + "If")
_FIXEDSTEP_ITEM = struct.Struct(BIGWIG_BYTE_ORDER + "f")

type _Interval = tuple[int, int, float]


class _Header(BaseModel):
    model_config = ConfigDict(frozen=True)

    chrom_tree_offset: int
    full_data_offset: int
    full_index_offset: int
    uncompress_buf_size: int


class _DataBlock(BaseModel):
    model_config = ConfigDict(frozen=True)

    offset: int
    size: int


class _Node(BaseModel):
    model_config = ConfigDict(frozen=True)

    raw: bytes
    at: int


class _Root(BaseModel):
    model_config = ConfigDict(frozen=True)

    node: _Node
    node_bytes: int


class _Query(BaseModel):
    model_config = ConfigDict(frozen=True)

    chrom_id: int
    begin: int
    end: int

    def overlaps(self, start_chrom: int, start: int, end_chrom: int, end: int) -> bool:
        return (start_chrom, start) < (self.chrom_id, self.end) and (end_chrom, end) > (
            self.chrom_id,
            self.begin,
        )


class _SectionHead(BaseModel):
    model_config = ConfigDict(frozen=True)

    chrom_id: int
    start: int
    step: int
    span: int
    kind: int
    count: int


def _unpack(layout: struct.Struct, raw: bytes, at: int) -> tuple[int, ...]:
    if at < 0 or at + layout.size > len(raw):
        msg = f"the bigWig read ends early, at byte {len(raw)} of {at + layout.size}"
        raise TrackReadError(msg)
    return layout.unpack_from(raw, at)


def _parse_header(raw: bytes) -> _Header:
    fields = _unpack(_HEADER, raw, 0)
    if fields[0] == _SWAPPED_MAGIC:
        msg = (
            "the file is a big-endian bigWig, and only BIGWIG_BYTE_ORDER "
            f"({BIGWIG_BYTE_ORDER!r}, little-endian) is read"
        )
        raise TrackReadError(msg)
    if fields[0] != _BIGWIG_MAGIC:
        msg = f"the file does not start with the bigWig magic number: {fields[0]:#x}"
        raise TrackReadError(msg)
    zoom_levels = fields[2]
    if zoom_levels > BIGWIG_MAX_ZOOM_LEVELS:
        msg = (
            f"the bigWig header names {zoom_levels} zoom levels, past "
            f"BIGWIG_MAX_ZOOM_LEVELS ({BIGWIG_MAX_ZOOM_LEVELS})"
        )
        raise TrackReadError(msg)
    zoom_end = _HEADER.size + zoom_levels * _ZOOM_HEADER.size
    if zoom_end > len(raw):
        msg = f"the bigWig read ends early, at byte {len(raw)} of {zoom_end}"
        raise TrackReadError(msg)
    return _Header(
        chrom_tree_offset=fields[3],
        full_data_offset=fields[4],
        full_index_offset=fields[5],
        uncompress_buf_size=fields[10],
    )


def _parse_chrom_tree(raw: bytes, base: int) -> dict[str, int]:
    magic, _, key_size, value_size, _, _ = _unpack(_CHROM_TREE_HEADER, raw, 0)
    if magic != _CHROM_TREE_MAGIC:
        msg = f"the chromosome tree does not start with its magic number: {magic:#x}"
        raise TrackReadError(msg)
    if value_size != _CHROM_VALUE.size:
        msg = (
            f"the chromosome tree names valSize {value_size}, and a bigWig chromosome "
            f"value is {_CHROM_VALUE.size} bytes"
        )
        raise TrackReadError(msg)
    found: dict[str, int] = {}
    pending = [_CHROM_TREE_HEADER.size]
    while pending:
        at = pending.pop()
        is_leaf, _, count = _unpack(_NODE_HEADER, raw, at)
        for index in range(count):
            item = at + _NODE_HEADER.size + index * (key_size + _CHROM_VALUE.size)
            value_at = item + key_size
            if is_leaf:
                name = raw[item:value_at].rstrip(b"\x00").decode(errors="replace")
                found[name] = _unpack(_CHROM_VALUE, raw, value_at)[0]
                continue
            child = _unpack(_CHILD_OFFSET, raw, value_at)[0] - base
            if child <= at:
                msg = f"a chromosome tree node at byte {base + at} points back"
                raise TrackReadError(msg)
            pending.append(child)
    return found


def _node_items(node: _Node, query: _Query) -> tuple[list[_DataBlock], list[int]]:
    is_leaf, _, count = _unpack(_NODE_HEADER, node.raw, node.at)
    item = _LEAF_ITEM if is_leaf else _BRANCH_ITEM
    blocks: list[_DataBlock] = []
    children: list[int] = []
    for index in range(count):
        fields = _unpack(
            item, node.raw, node.at + _NODE_HEADER.size + index * item.size
        )
        if not query.overlaps(*fields[:4]):
            continue
        if is_leaf:
            blocks.append(_DataBlock(offset=fields[4], size=fields[5]))
        else:
            children.append(fields[4])
    return blocks, children


def _bedgraph(_head: _SectionHead, body: bytes) -> list[_Interval]:
    return list(_BEDGRAPH_ITEM.iter_unpack(body))


def _varstep(head: _SectionHead, body: bytes) -> list[_Interval]:
    return [
        (start, start + head.span, value)
        for start, value in _VARSTEP_ITEM.iter_unpack(body)
    ]


def _fixedstep(head: _SectionHead, body: bytes) -> list[_Interval]:
    starts = (head.start + index * head.step for index in range(head.count))
    return [
        (start, start + head.span, value)
        for start, (value,) in zip(
            starts, _FIXEDSTEP_ITEM.iter_unpack(body), strict=True
        )
    ]


type _SectionReader = Callable[[_SectionHead, bytes], list[_Interval]]

_SECTIONS: dict[int, tuple[struct.Struct, _SectionReader]] = {
    1: (_BEDGRAPH_ITEM, _bedgraph),
    2: (_VARSTEP_ITEM, _varstep),
    3: (_FIXEDSTEP_ITEM, _fixedstep),
}


def _section_intervals(section: bytes) -> tuple[int, list[_Interval]]:
    fields = _unpack(_SECTION_HEADER, section, 0)
    head = _SectionHead(
        chrom_id=fields[0],
        start=fields[1],
        step=fields[3],
        span=fields[4],
        kind=fields[5],
        count=fields[7],
    )
    if head.kind not in _SECTIONS:
        msg = f"a bigWig data block holds the unknown section type {head.kind}"
        raise TrackReadError(msg)
    item, read = _SECTIONS[head.kind]
    end = _SECTION_HEADER.size + head.count * item.size
    if end > len(section):
        msg = (
            f"a bigWig section of {head.count} items ends early, at byte {len(section)}"
        )
        raise TrackReadError(msg)
    return head.chrom_id, read(head, section[_SECTION_HEADER.size : end])


def _inflate(raw: bytes, header: _Header) -> bytes:
    if header.uncompress_buf_size == 0:
        return raw
    try:
        return zlib.decompressobj().decompress(raw, header.uncompress_buf_size)
    except zlib.error as error:
        msg = f"a bigWig data block does not inflate: {error}"
        raise TrackReadError(msg) from error


def _check_level(found: list[_DataBlock], children: list[int], depth: int) -> None:
    for block in found:
        if block.size > BIGWIG_MAX_BLOCK_BYTES:
            msg = (
                f"a bigWig data block of {block.size} bytes is past "
                f"BIGWIG_MAX_BLOCK_BYTES ({BIGWIG_MAX_BLOCK_BYTES})"
            )
            raise TrackReadError(msg)
    for count, what in (
        (len(found), "data blocks"),
        (len(children), "R-tree nodes at one level"),
    ):
        if count > BIGWIG_MAX_BLOCKS:
            msg = (
                f"the region needs {count} {what}, past BIGWIG_MAX_BLOCKS "
                f"({BIGWIG_MAX_BLOCKS})"
            )
            raise TrackReadError(msg)
    if children and depth >= BIGWIG_MAX_RTREE_DEPTH:
        msg = (
            "the R-tree descends past BIGWIG_MAX_RTREE_DEPTH "
            f"({BIGWIG_MAX_RTREE_DEPTH}) levels"
        )
        raise TrackReadError(msg)


def _fill(values: list[float], query: _Query, section: bytes) -> None:
    chrom_id, intervals = _section_intervals(section)
    if chrom_id != query.chrom_id:
        return
    for start, end, value in intervals:
        for position in range(max(start, query.begin), min(end, query.end)):
            values[position - query.begin] = value


class BigWigReader:
    def __init__(self, client: JBrowseClient, data_path: str) -> None:
        self._client = client
        self._data_path = data_path
        self._header: _Header | None = None
        self._chroms: dict[str, int] | None = None
        self._root: _Root | None = None
        self.reads = 0

    async def _read(self, first: int, last: int) -> bytes:
        self.reads += 1
        return await self._client.store_bytes(self._data_path, (first, last))

    async def _read_header(self) -> _Header:
        if self._header is None:
            self._header = _parse_header(await self._read(0, _HEADER_READ - 1))
        return self._header

    async def _read_chroms(self, header: _Header) -> dict[str, int]:
        if self._chroms is None:
            first, end = header.chrom_tree_offset, header.full_data_offset
            if end - first > BIGWIG_MAX_CHROM_TREE_BYTES:
                msg = (
                    f"the chromosome tree of {self._data_path} spans {end - first} "
                    "bytes, past BIGWIG_MAX_CHROM_TREE_BYTES "
                    f"({BIGWIG_MAX_CHROM_TREE_BYTES})"
                )
                raise TrackReadError(msg)
            raw = await self._read(first, end - 1)
            self._chroms = _parse_chrom_tree(raw, first)
        return self._chroms

    async def _read_root(self, header: _Header) -> _Root:
        if self._root is None:
            first = header.full_index_offset
            raw = await self._read(first, first + _ROOT_READ - 1)
            magic, block_size = _unpack(_RTREE_HEADER, raw, 0)[:2]
            if magic != _RTREE_MAGIC:
                msg = (
                    f"the R-tree index does not start with its magic number: {magic:#x}"
                )
                raise TrackReadError(msg)
            if block_size > BIGWIG_MAX_NODE_ITEMS:
                msg = (
                    f"the R-tree nodes hold {block_size} items, past "
                    f"BIGWIG_MAX_NODE_ITEMS ({BIGWIG_MAX_NODE_ITEMS})"
                )
                raise TrackReadError(msg)
            self._root = _Root(
                node=_Node(raw=raw, at=_RTREE_HEADER.size),
                node_bytes=_NODE_HEADER.size + block_size * _LEAF_ITEM.size,
            )
        return self._root

    async def _read_level(self, children: list[int], node_bytes: int) -> list[_Node]:
        ordered = sorted(children)
        first, last = ordered[0], ordered[-1] + node_bytes - 1
        if last - first + 1 > len(ordered) * node_bytes:
            msg = f"the R-tree nodes of one level lie {last - first + 1} bytes apart"
            raise TrackReadError(msg)
        raw = await self._read(first, last)
        return [_Node(raw=raw, at=child - first) for child in ordered]

    async def _blocks(self, header: _Header, query: _Query) -> list[_DataBlock]:
        root = await self._read_root(header)
        nodes = [root.node]
        found: list[_DataBlock] = []
        depth = 1
        while nodes:
            children: list[int] = []
            for node in nodes:
                blocks, below = _node_items(node, query)
                found.extend(blocks)
                children.extend(below)
            _check_level(found, children, depth)
            nodes = (
                await self._read_level(children, root.node_bytes) if children else []
            )
            depth += 1
        return sorted(set(found), key=lambda block: block.offset)

    async def depth(self, seqid: str, start: int, end: int) -> list[float]:
        region = genome_region(seqid, start, end)
        if region.length > BIGWIG_MAX_REGION:
            msg = (
                f"{seqid}:{start}-{end} spans {region.length} bases, past "
                f"BIGWIG_MAX_REGION ({BIGWIG_MAX_REGION})"
            )
            raise TrackReadError(msg)
        header = await self._read_header()
        chroms = await self._read_chroms(header)
        if seqid not in chroms:
            raise SequenceNotIndexedError(self._data_path, seqid)
        query = _Query(chrom_id=chroms[seqid], begin=start - 1, end=end)
        values = [0.0] * region.length
        for block in await self._blocks(header, query):
            raw = await self._read(block.offset, block.offset + block.size - 1)
            _fill(values, query, _inflate(raw, header))
        return values
