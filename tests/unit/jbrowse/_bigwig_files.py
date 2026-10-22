from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass

BIGWIG_MAGIC = 0x888FFC26
CHROM_TREE_MAGIC = 0x78CA8C91
RTREE_MAGIC = 0x2468ACE0
BEDGRAPH = 1
VARSTEP = 2
FIXEDSTEP = 3
HEADER_BYTES = 64
ZOOM_HEADER_BYTES = 24


@dataclass(frozen=True)
class Section:
    chrom_id: int
    start: int
    end: int
    payload: bytes


def bedgraph(chrom_id: int, items: list[tuple[int, int, float]]) -> Section:
    start, end = items[0][0], items[-1][1]
    head = struct.pack("<IIIIIBBH", chrom_id, start, end, 0, 0, BEDGRAPH, 0, len(items))
    body = b"".join(struct.pack("<IIf", s, e, v) for s, e, v in items)
    return Section(chrom_id, start, end, head + body)


def varstep(chrom_id: int, span: int, items: list[tuple[int, float]]) -> Section:
    start, end = items[0][0], items[-1][0] + span
    head = struct.pack(
        "<IIIIIBBH", chrom_id, start, end, 0, span, VARSTEP, 0, len(items)
    )
    body = b"".join(struct.pack("<If", s, v) for s, v in items)
    return Section(chrom_id, start, end, head + body)


def fixedstep(
    chrom_id: int, start: int, step: int, span: int, values: list[float]
) -> Section:
    end = start + (len(values) - 1) * step + span
    head = struct.pack(
        "<IIIIIBBH", chrom_id, start, end, step, span, FIXEDSTEP, 0, len(values)
    )
    return Section(
        chrom_id, start, end, head + struct.pack(f"<{len(values)}f", *values)
    )


def typed(section: Section, kind: int) -> Section:
    payload = section.payload[:20] + bytes([kind]) + section.payload[21:]
    return Section(section.chrom_id, section.start, section.end, payload)


def _chrom_tree(chroms: list[str], block_size: int, at: int) -> list[bytes]:
    key_size = max(len(name) for name in chroms)
    head = struct.pack(
        "<IIIIQQ", CHROM_TREE_MAGIC, block_size, key_size, 8, len(chroms), 0
    )
    keys = [name.encode().ljust(key_size, b"\x00") for name in chroms]
    if len(chroms) <= block_size:
        items = b"".join(
            key + struct.pack("<II", index, 1_000_000) for index, key in enumerate(keys)
        )
        return [head + struct.pack("<BBH", 1, 0, len(chroms)) + items]
    leaves = [
        list(enumerate(keys))[at : at + block_size]
        for at in range(0, len(keys), block_size)
    ]
    leaf_size = 4 + block_size * (key_size + 8)
    root_size = 4 + len(leaves) * (key_size + 8)
    root_items = b"".join(
        leaf[0][1] + struct.pack("<Q", at + 32 + root_size + index * leaf_size)
        for index, leaf in enumerate(leaves)
    )
    nodes = [head + struct.pack("<BBH", 0, 0, len(leaves)) + root_items]
    for leaf in leaves:
        items = b"".join(key + struct.pack("<II", ix, 1_000_000) for ix, key in leaf)
        nodes.append(
            (struct.pack("<BBH", 1, 0, len(leaf)) + items).ljust(leaf_size, b"\x00")
        )
    return nodes


@dataclass(frozen=True)
class _Box:
    start: tuple[int, int]
    end: tuple[int, int]


def _levels(boxes: list[_Box], block_size: int) -> list[list[list[int]]]:
    levels: list[list[list[int]]] = []
    count = len(boxes)
    while True:
        groups = [
            list(range(at, min(at + block_size, count)))
            for at in range(0, count, block_size)
        ]
        levels.append(groups)
        if len(groups) == 1:
            return levels
        count = len(groups)


def _index(
    boxes: list[_Box], blocks: list[tuple[int, int]], block_size: int, at: int
) -> bytes:
    levels = _levels(boxes, block_size)
    leaf_size = 4 + block_size * 32
    branch_size = 4 + block_size * 24
    order = list(reversed(levels))
    offsets: list[list[int]] = []
    cursor = at + 48
    for depth, groups in enumerate(order):
        size = leaf_size if depth == len(order) - 1 else branch_size
        offsets.append([cursor + index * size for index in range(len(groups))])
        cursor += len(groups) * size
    level_boxes = [boxes]
    for groups in levels[:-1]:
        below = level_boxes[-1]
        level_boxes.append(
            [_Box(below[group[0]].start, below[group[-1]].end) for group in groups]
        )
    nodes: list[bytes] = []
    for depth, groups in enumerate(order):
        leaf = depth == len(order) - 1
        below = level_boxes[len(order) - 1 - depth]
        for group in groups:
            items = b""
            for child in group:
                box = below[child]
                bounds = struct.pack("<IIII", *box.start, *box.end)
                if leaf:
                    items += bounds + struct.pack("<QQ", *blocks[child])
                else:
                    items += bounds + struct.pack("<Q", offsets[depth + 1][child])
            size = leaf_size if leaf else branch_size
            nodes.append(
                (struct.pack("<BBH", int(leaf), 0, len(group)) + items).ljust(
                    size, b"\x00"
                )
            )
    first, last = boxes[0], boxes[-1]
    head = struct.pack(
        "<IIQIIIIQII",
        RTREE_MAGIC,
        block_size,
        len(boxes),
        *first.start,
        *last.end,
        at,
        1,
        0,
    )
    return head + b"".join(nodes)


@dataclass(frozen=True)
class Layout:
    block_size: int = 256
    chrom_block_size: int = 256
    zoom_levels: int = 0
    compressed: bool = True
    magic: int = BIGWIG_MAGIC
    summary: tuple[int, float, float, float, float] | None = None
    summary_at_end: bool = False


DEFAULT_LAYOUT = Layout()


def bigwig(
    chroms: list[str], sections: list[Section], layout: Layout = DEFAULT_LAYOUT
) -> bytes:
    summary = b"" if layout.summary is None else struct.pack("<Qdddd", *layout.summary)
    front, tail = (b"", summary) if layout.summary_at_end else (summary, b"")
    zooms_end = HEADER_BYTES + layout.zoom_levels * ZOOM_HEADER_BYTES
    chrom_at = zooms_end + len(front)
    chrom_tree = b"".join(_chrom_tree(chroms, layout.chrom_block_size, chrom_at))
    data_at = chrom_at + len(chrom_tree)
    data = struct.pack("<I", len(sections))
    blocks: list[tuple[int, int]] = []
    for section in sections:
        body = zlib.compress(section.payload) if layout.compressed else section.payload
        blocks.append((data_at + len(data), len(body)))
        data += body
    index_at = data_at + len(data)
    boxes = [
        _Box((section.chrom_id, section.start), (section.chrom_id, section.end))
        for section in sections
    ]
    index = _index(boxes, blocks, layout.block_size, index_at)
    buffer_size = max(len(s.payload) for s in sections) if layout.compressed else 0
    summary_at = index_at + len(index) if tail else zooms_end if front else 0
    header = struct.pack(
        "<IHHQQQHHQQIQ",
        layout.magic,
        4,
        layout.zoom_levels,
        chrom_at,
        data_at,
        index_at,
        0,
        0,
        0,
        summary_at,
        buffer_size,
        0,
    )
    zooms = bytes(layout.zoom_levels * ZOOM_HEADER_BYTES)
    return header + zooms + front + chrom_tree + data + index + tail
