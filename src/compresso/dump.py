"""Reading memory dumps: NAME.bin (raw bytes) + optional NAME.json sidecar.

The format is documented in data/README.md. It is the contract between the
LLM track (#4), the simulator track (#5) and everything in this package.

Dumps can be several GB, so the .bin is memory-mapped and read in chunks;
nothing here holds the whole file in memory.
"""

from __future__ import annotations

import itertools
import json
import mmap
from bisect import bisect_right
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

KINDS = ("weight", "kv", "activation", "other")
UNTAGGED = "untagged"  # group name for lines outside every sidecar region


@dataclass(frozen=True)
class Region:
    """A byte range of the dump with known contents."""

    offset: int
    length: int
    tag: str
    dtype: str = "unknown"
    kind: str = "other"

    @property
    def end(self) -> int:
        return self.offset + self.length


@dataclass
class Sidecar:
    source: str | None = None
    model: str | None = None
    regions: list[Region] = field(default_factory=list)
    extra: dict = field(default_factory=dict)  # any other top-level keys, kept as-is

    def __post_init__(self) -> None:
        self.regions.sort(key=lambda r: r.offset)
        self._starts = [r.offset for r in self.regions]

    def region_at(self, offset: int) -> Region | None:
        """The region containing byte `offset`, or None."""
        i = bisect_right(self._starts, offset) - 1
        if i >= 0 and offset < self.regions[i].end:
            return self.regions[i]
        return None


def sidecar_path(dump: str | Path) -> Path:
    return Path(dump).with_suffix(".json")


def load_sidecar(path: str | Path, dump_size: int | None = None) -> Sidecar:
    """Parse and validate a sidecar JSON. Raises ValueError on a bad file."""
    with open(path) as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        # ValueError, not TypeError: every bad-sidecar problem is reported the same way.
        raise ValueError(f"{path}: top level must be a JSON object")  # noqa: TRY004

    regions = []
    for i, r in enumerate(raw.get("regions", [])):
        try:
            reg = Region(
                offset=int(r["offset"]),
                length=int(r["length"]),
                tag=str(r["tag"]),
                dtype=str(r.get("dtype", "unknown")),
                kind=str(r.get("kind", "other")),
            )
        except (KeyError, TypeError) as e:
            raise ValueError(f"{path}: region {i} needs offset, length and tag ({e})") from e
        if reg.offset < 0 or reg.length <= 0:
            raise ValueError(f"{path}: region {i} ({reg.tag}) has a bad offset/length")
        if reg.kind not in KINDS:
            raise ValueError(f"{path}: region {i} ({reg.tag}) kind must be one of {KINDS}")
        if dump_size is not None and reg.end > dump_size:
            raise ValueError(f"{path}: region {i} ({reg.tag}) ends past the dump ({dump_size} B)")
        regions.append(reg)

    regions.sort(key=lambda r: r.offset)
    for a, b in itertools.pairwise(regions):
        if b.offset < a.end:
            raise ValueError(f"{path}: regions {a.tag!r} and {b.tag!r} overlap")

    extra = {k: v for k, v in raw.items() if k not in ("source", "model", "regions")}
    return Sidecar(raw.get("source"), raw.get("model"), regions, extra)


def iter_lines(
    path: str | Path,
    line_bytes: int = 64,
    chunk_lines: int = 1 << 16,
    limit_lines: int | None = None,
) -> Iterator[tuple[int, bytes]]:
    """Yield (byte_offset, line) for every whole line of the dump.

    The file is memory-mapped and sliced one chunk at a time, so memory use is
    constant whatever the dump size. A trailing partial line is skipped; use
    tail_bytes() to report it.
    """
    size = Path(path).stat().st_size
    n_lines = size // line_bytes
    if limit_lines is not None:
        n_lines = min(n_lines, limit_lines)
    if n_lines == 0:
        return
    with open(path, "rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
        chunk = chunk_lines * line_bytes
        end = n_lines * line_bytes
        for start in range(0, end, chunk):
            buf = mm[start : min(start + chunk, end)]  # copies one chunk only
            for i in range(0, len(buf), line_bytes):
                yield start + i, buf[i : i + line_bytes]


def tail_bytes(path: str | Path, line_bytes: int = 64) -> int:
    """Bytes at the end of the dump that don't make a whole line (ignored)."""
    return Path(path).stat().st_size % line_bytes
