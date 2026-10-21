"""Builds BGZF files and tabix indexes in memory, and a store that serves them."""

from __future__ import annotations

import struct
import zlib

import httpx

from veupathdb.jbrowse.client import JBrowseClient

BASE = "https://qa.plasmodb.org/plasmo.qa"
GENERIC = 0
TBI_GFF_COLUMNS = (1, 4, 5)

type Bins = dict[int, list[tuple[int, int]]]


def bgzf_block(text: bytes) -> bytes:
    compressor = zlib.compressobj(6, zlib.DEFLATED, -15)
    deflated = compressor.compress(text) + compressor.flush()
    size = 12 + 6 + len(deflated) + 8
    header = struct.pack(
        "<BBBBIBBHBBHH", 31, 139, 8, 4, 0, 0, 255, 6, 66, 67, 2, size - 1
    )
    return header + deflated + struct.pack("<II", zlib.crc32(text), len(text))


def bgzf(*texts: bytes) -> tuple[bytes, list[int]]:
    blocks = [bgzf_block(text) for text in texts]
    starts = [sum(len(block) for block in blocks[:i]) for i in range(len(blocks))]
    return b"".join(blocks) + bgzf_block(b""), starts


def virtual(block_start: int, within: int) -> int:
    return block_start << 16 | within


def tbi(
    refs: dict[str, tuple[Bins, list[int]]],
    *,
    file_format: int = GENERIC,
    columns: tuple[int, int, int] = TBI_GFF_COLUMNS,
) -> bytes:
    names = b"".join(name.encode() + b"\x00" for name in refs)
    body = struct.pack(
        "<4s8i", b"TBI\x01", len(refs), file_format, *columns, ord("#"), 0, len(names)
    )
    body += names
    for bins, linear in refs.values():
        body += struct.pack("<i", len(bins))
        for bin_id, chunks in bins.items():
            body += struct.pack("<Ii", bin_id, len(chunks))
            for begin, end in chunks:
                body += struct.pack("<QQ", begin, end)
        body += struct.pack(f"<i{len(linear)}Q", len(linear), *linear)
    return bgzf_block(body) + bgzf_block(b"")


def gff(seqid: str, start: int, end: int, ident: str) -> bytes:
    return (
        f"{seqid}\tVEuPathDB\tintronJunction\t{start}\t{end}\t5\t+\t.\tID={ident}\n"
    ).encode()


class Store:
    def __init__(self, files: dict[str, bytes]) -> None:
        self.files = files
        self.requests: list[httpx.Request] = []
        self.cut_at: int | None = None
        self.whole_answer = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        body = self.files[request.url.params["data"]]
        if "Range" not in request.headers:
            return httpx.Response(200, content=body)
        if self.whole_answer:
            return httpx.Response(200, content=body)
        first, last = request.headers["Range"].removeprefix("bytes=").split("-")
        answer = body[int(first) : int(last) + 1]
        if self.cut_at is not None:
            answer = answer[: self.cut_at]
        return httpx.Response(206, content=answer)

    def client(self) -> JBrowseClient:
        return JBrowseClient(base_url=BASE, transport=httpx.MockTransport(self))

    def ranges(self) -> list[str]:
        return [r.headers["Range"] for r in self.requests if "Range" in r.headers]
