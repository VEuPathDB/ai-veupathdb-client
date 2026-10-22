"""Range reads of a bgzipped, tabix-indexed genome browser track through the store."""

from __future__ import annotations

import asyncio
import gzip
import struct
import zlib
from typing import Self

import pydantic
from pydantic import BaseModel, ConfigDict, Field, model_validator

from veupathdb.jbrowse.client import JBrowseClient
from veupathdb.jbrowse.errors import SequenceNotIndexedError, TrackReadError
from veupathdb.jbrowse.models import TrackConfig
from veupathdb.jbrowse.region import GenomeRegion, genome_region

TABIX_MAGIC = b"TBI\x01"
BGZF_MAX_BLOCK = 65536
MAX_COMPRESSED_SPAN = 16 * 1024 * 1024
LINEAR_SHIFT = 14
PSEUDO_BIN = 37450
BIN_LEVELS = ((26, 1), (23, 9), (20, 73), (17, 585), (14, 4681))
GENERIC_FORMAT = 0
ZERO_BASED_FLAG = 0x10000

_HEADER = "<8i"
_HEADER_FIELDS = (
    "n_ref",
    "file_format",
    "col_seq",
    "col_beg",
    "col_end",
    "meta",
    "skip",
    "l_nm",
)
_BGZF_FIXED = struct.Struct("<BBBBIBBH")
_BGZF_FOOTER = struct.Struct("<II")
_GZIP_ID = (31, 139, 8, 4)
_BC = (66, 67, 2)


class Chunk(BaseModel):
    model_config = ConfigDict(frozen=True)

    begin: int = Field(ge=0)
    end: int

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.end < self.begin:
            msg = f"the chunk {self.begin}-{self.end} ends before it begins"
            raise ValueError(msg)
        return self


class RefIndex(BaseModel):
    model_config = ConfigDict(frozen=True)

    bins: dict[int, tuple[Chunk, ...]]
    linear: tuple[int, ...]

    def min_offset(self, begin: int) -> int:
        if not self.linear:
            return 0
        return self.linear[min(begin >> LINEAR_SHIFT, len(self.linear) - 1)]


class TabixHeader(BaseModel):
    model_config = ConfigDict(frozen=True)

    file_format: int
    col_seq: int = Field(ge=1)
    col_beg: int = Field(ge=1)
    col_end: int = Field(ge=1)
    meta: int = Field(ge=0, le=255)

    @model_validator(mode="after")
    def _generic(self) -> Self:
        if self.file_format & 0xFFFF != GENERIC_FORMAT:
            msg = f"only a generic tabix index is read, this one is {self.file_format}"
            raise ValueError(msg)
        return self

    @property
    def zero_based(self) -> bool:
        return bool(self.file_format & ZERO_BASED_FLAG)


class TabixIndex(BaseModel):
    model_config = ConfigDict(frozen=True)

    header: TabixHeader
    names: tuple[str, ...]
    refs: tuple[RefIndex, ...]

    @model_validator(mode="after")
    def _one_ref_per_name(self) -> Self:
        if len(self.names) != len(self.refs):
            msg = f"the index names {len(self.names)} sequences and {len(self.refs)}"
            raise ValueError(msg)
        return self

    def ref(self, name: str) -> RefIndex | None:
        if name not in self.names:
            return None
        return self.refs[self.names.index(name)]


class _Cursor:
    def __init__(self, data: bytes) -> None:
        self._data = data
        self._at = 0

    def take(self, size: int) -> bytes:
        if self._at + size > len(self._data):
            msg = f"the tabix index ends early, at byte {len(self._data)}"
            raise TrackReadError(msg)
        taken = self._data[self._at : self._at + size]
        self._at += size
        return taken

    def ints(self, layout: str) -> tuple[int, ...]:
        try:
            size = struct.calcsize(layout)
        except struct.error as error:
            msg = f"the tabix index holds a negative count: {layout}"
            raise TrackReadError(msg) from error
        return struct.unpack(layout, self.take(size))


def _ref_index(cursor: _Cursor) -> RefIndex:
    bins: dict[int, tuple[Chunk, ...]] = {}
    for _ in range(cursor.ints("<i")[0]):
        bin_id, n_chunk = cursor.ints("<Ii")
        pairs = cursor.ints(f"<{2 * n_chunk}Q")
        if bin_id != PSEUDO_BIN:
            bins[bin_id] = tuple(
                Chunk(begin=pairs[i], end=pairs[i + 1]) for i in range(0, len(pairs), 2)
            )
    n_intv = cursor.ints("<i")[0]
    return RefIndex(bins=bins, linear=cursor.ints(f"<{n_intv}Q"))


def _inflate_index(raw: bytes) -> bytes:
    try:
        return gzip.decompress(raw)
    except (OSError, EOFError, zlib.error) as error:
        msg = f"the tabix index is not gzip data: {error}"
        raise TrackReadError(msg) from error


def parse_index(raw: bytes) -> TabixIndex:
    cursor = _Cursor(_inflate_index(raw))
    if cursor.take(4) != TABIX_MAGIC:
        msg = "the index does not start with the tabix magic"
        raise TrackReadError(msg)
    fields = dict(zip(_HEADER_FIELDS, cursor.ints(_HEADER), strict=True))
    raw_names = cursor.take(fields["l_nm"]).split(b"\x00")
    try:
        names = tuple(name.decode() for name in raw_names if name)
    except UnicodeDecodeError as error:
        msg = f"the tabix index holds sequence names that are not UTF-8: {error}"
        raise TrackReadError(msg) from error
    try:
        header = TabixHeader.model_validate(fields)
        refs = tuple(_ref_index(cursor) for _ in range(fields["n_ref"]))
        return TabixIndex(header=header, names=names, refs=refs)
    except pydantic.ValidationError as error:
        msg = f"the tabix index is not valid: {error}"
        raise TrackReadError(msg) from error


def region_bins(begin: int, end: int) -> list[int]:
    last = end - 1
    bins = [0]
    for shift, offset in BIN_LEVELS:
        bins.extend(range(offset + (begin >> shift), offset + (last >> shift) + 1))
    return bins


def region_chunks(ref: RefIndex, begin: int, end: int) -> list[Chunk]:
    floor = ref.min_offset(begin)
    found = sorted(
        (
            chunk
            for bin_id in region_bins(begin, end)
            for chunk in ref.bins.get(bin_id, ())
            if chunk.end > floor
        ),
        key=lambda chunk: chunk.begin,
    )
    merged: list[Chunk] = []
    for chunk in found:
        if merged and chunk.begin <= merged[-1].end:
            last = merged.pop()
            merged.append(Chunk(begin=last.begin, end=max(last.end, chunk.end)))
        else:
            merged.append(Chunk(begin=max(chunk.begin, floor), end=chunk.end))
    return merged


def read_groups(chunks: list[Chunk]) -> list[list[Chunk]]:
    groups: list[list[Chunk]] = []
    for chunk in chunks:
        if groups and chunk.begin >> 16 <= _last_byte(groups[-1]):
            groups[-1].append(chunk)
        else:
            groups.append([chunk])
    return groups


def _last_byte(group: list[Chunk]) -> int:
    return max(chunk.end >> 16 for chunk in group) + BGZF_MAX_BLOCK - 1


class _Block(BaseModel):
    model_config = ConfigDict(frozen=True)

    start: int
    length: int


class BgzfText(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: bytes
    blocks: dict[int, _Block]

    def at(self, virtual_offset: int) -> int:
        block = self.blocks.get(virtual_offset >> 16)
        within = virtual_offset & 0xFFFF
        if block is None or within > block.length:
            msg = f"the read ends inside the block at byte {virtual_offset >> 16}"
            raise TrackReadError(msg)
        return block.start + within

    def between(self, chunk: Chunk) -> bytes:
        return self.text[self.at(chunk.begin) : self.at(chunk.end)]


def _block_size(raw: bytes, position: int) -> int | None:
    if position + _BGZF_FIXED.size > len(raw):
        return None
    id1, id2, method, flags, _, _, _, xlen = _BGZF_FIXED.unpack_from(raw, position)
    if (id1, id2, method, flags) != _GZIP_ID:
        msg = f"a BGZF block does not start with the gzip magic at byte {position}"
        raise TrackReadError(msg)
    extra_at = position + _BGZF_FIXED.size
    if extra_at + xlen > len(raw):
        return None
    cursor = extra_at
    while cursor + 4 <= extra_at + xlen:
        si1, si2, slen = struct.unpack_from("<BBH", raw, cursor)
        if (si1, si2, slen) == _BC:
            return int(struct.unpack_from("<H", raw, cursor + 4)[0]) + 1
        cursor += 4 + slen
    msg = f"the gzip member at byte {position} carries no BGZF block size"
    raise TrackReadError(msg)


def _inflate_block(raw: bytes, position: int, size: int) -> bytes:
    xlen = int(struct.unpack_from("<H", raw, position + 10)[0])
    payload = raw[position + _BGZF_FIXED.size + xlen : position + size - 8]
    crc, length = _BGZF_FOOTER.unpack_from(raw, position + size - 8)
    try:
        text = zlib.decompress(payload, -15)
    except zlib.error as error:
        msg = f"the BGZF block at byte {position} does not inflate: {error}"
        raise TrackReadError(msg) from error
    if len(text) != length or zlib.crc32(text) != crc:
        msg = f"the BGZF block at byte {position} fails its checksum"
        raise TrackReadError(msg)
    return text


def inflate_blocks(raw: bytes, base: int) -> BgzfText:
    texts: list[bytes] = []
    blocks: dict[int, _Block] = {}
    produced = 0
    position = 0
    size = _block_size(raw, position)
    while size is not None and position + size <= len(raw):
        text = _inflate_block(raw, position, size)
        blocks[base + position] = _Block(start=produced, length=len(text))
        texts.append(text)
        produced += len(text)
        position += size
        size = _block_size(raw, position)
    blocks.setdefault(base + position, _Block(start=produced, length=0))
    return BgzfText(text=b"".join(texts), blocks=blocks)


def _span(header: TabixHeader, columns: list[str]) -> tuple[str, int, int]:
    needed = max(header.col_seq, header.col_beg, header.col_end)
    if len(columns) < needed:
        msg = f"a track line has {len(columns)} columns, the index reads {needed}"
        raise TrackReadError(msg)
    try:
        begin = int(columns[header.col_beg - 1]) - (0 if header.zero_based else 1)
        end = (
            begin + 1
            if header.col_end == header.col_beg
            else int(columns[header.col_end - 1])
        )
    except ValueError as error:
        msg = f"a track line has a position that is not a number: {error}"
        raise TrackReadError(msg) from error
    return columns[header.col_seq - 1], begin, end


def _decoded(text: bytes) -> str:
    try:
        return text.decode()
    except UnicodeDecodeError as error:
        msg = f"a track line is not UTF-8 text: {error}"
        raise TrackReadError(msg) from error


def _overlapping(header: TabixHeader, text: bytes, region: GenomeRegion) -> list[str]:
    kept: list[str] = []
    for line in _decoded(text).split("\n"):
        if not line or ord(line[0]) == header.meta:
            continue
        seqid, begin, end = _span(header, line.split("\t"))
        if seqid == region.seqid and begin < region.end and end >= region.start:
            kept.append(line)
    return kept


def _decode_group(
    header: TabixHeader, raw: bytes, group: list[Chunk], region: GenomeRegion
) -> list[str]:
    text = inflate_blocks(raw, group[0].begin >> 16)
    return [
        line
        for chunk in group
        for line in _overlapping(header, text.between(chunk), region)
    ]


class TabixReader:
    def __init__(self, client: JBrowseClient) -> None:
        self._client = client
        self._indexes: dict[str, TabixIndex] = {}

    async def index(self, track: TrackConfig) -> TabixIndex:
        path = track.index_path
        if path not in self._indexes:
            self._indexes[path] = parse_index(await self._client.store_bytes(path))
        return self._indexes[path]

    async def lines(
        self, track: TrackConfig, seqid: str, start: int, end: int
    ) -> list[str]:
        region = genome_region(seqid, start, end)
        index = await self.index(track)
        ref = index.ref(seqid)
        if ref is None:
            raise SequenceNotIndexedError(track.data_path, seqid)
        groups = read_groups(region_chunks(ref, start - 1, end))
        span = sum(_last_byte(group) - (group[0].begin >> 16) + 1 for group in groups)
        if span > MAX_COMPRESSED_SPAN:
            msg = f"{seqid}:{start}-{end} spans {span} compressed bytes"
            raise TrackReadError(msg)
        try:
            return [
                line
                for group in groups
                for line in await self._group_lines(track, index.header, group, region)
            ]
        except TrackReadError:
            self._indexes.pop(track.index_path, None)
            raise

    async def _group_lines(
        self,
        track: TrackConfig,
        header: TabixHeader,
        group: list[Chunk],
        region: GenomeRegion,
    ) -> list[str]:
        byte_range = (group[0].begin >> 16, _last_byte(group))
        raw = await self._client.store_bytes(track.data_path, byte_range)
        return await asyncio.to_thread(_decode_group, header, raw, group, region)
