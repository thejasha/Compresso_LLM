#!/usr/bin/env python3
"""Parse Compresso writebacks.bin and print a short summary.

Record layout (little-endian, 80 bytes):
  u64 tick
  u64 phys_addr   # 64 B aligned
  64 bytes data
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

RECORD_FMT = "<QQ64s"
RECORD_SIZE = struct.calcsize(RECORD_FMT)
assert RECORD_SIZE == 80


def iter_records(path: Path):
    data = path.read_bytes()
    if len(data) % RECORD_SIZE != 0:
        raise ValueError(
            f"{path}: size {len(data)} is not a multiple of {RECORD_SIZE}"
        )
    for offset in range(0, len(data), RECORD_SIZE):
        tick, addr, payload = struct.unpack_from(RECORD_FMT, data, offset)
        yield tick, addr, payload


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("writebacks", type=Path, help="path to writebacks.bin")
    p.add_argument(
        "-n",
        "--head",
        type=int,
        default=5,
        help="how many records to print (default: 5)",
    )
    args = p.parse_args(argv)

    records = list(iter_records(args.writebacks))
    print(f"file: {args.writebacks}")
    print(f"records: {len(records)}")
    print(f"bytes: {args.writebacks.stat().st_size}")
    if not records:
        return 0

    addrs = [addr for _, addr, _ in records]
    print(f"addr range: 0x{min(addrs):x} .. 0x{max(addrs):x}")
    print(f"unique lines: {len(set(addrs))}")
    print()
    print("first records:")
    for i, (tick, addr, payload) in enumerate(records[: args.head]):
        preview = payload[:8].hex()
        print(f"  [{i}] tick={tick} addr=0x{addr:x} data[0:8]={preview}...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
