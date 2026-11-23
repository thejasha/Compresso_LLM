#!/usr/bin/env python3
"""Stub traffic replay on a Compresso writebacks.bin.

Does not use the real BPC/Compresso code. Uses a fake line size so we can
test the control-vs-treatment comparison on a real gem5 trace.

Fake compressor:
  all-zero line -> 0 B
  else          -> 32 B   (always "compressible")

Control (naive):
  a line that grows past its previous packed size causes +1 extra memory trip.

Compresso stub:
  each line gets 32 B of inflation room once; growth within that room is free;
  growth beyond that causes +1 extra trip (and the room is not expanded here).

Usage:
  python3 sim/stub_replay.py data/traces/write_array/writebacks.bin
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

RECORD_FMT = "<QQ64s"
RECORD_SIZE = struct.calcsize(RECORD_FMT)


def fake_size(payload: bytes) -> int:
    if payload == bytes(64):
        return 0
    return 32


def replay(records: list[tuple[int, int, bytes]], mode: str) -> dict:
    """Return counts for mode in {'control', 'compresso'}."""
    # state[addr] = (packed_size, inflation_room)
    state: dict[int, tuple[int, int]] = {}
    overflows = 0
    first_installs = 0
    rewrites = 0

    for _tick, addr, payload in records:
        new_size = fake_size(payload)
        if addr not in state:
            room = 32 if mode == "compresso" else 0
            state[addr] = (new_size, room)
            first_installs += 1
            continue

        rewrites += 1
        old_size, room = state[addr]
        if new_size <= old_size:
            state[addr] = (new_size, room)
            continue

        growth = new_size - old_size
        if growth <= room:
            state[addr] = (new_size, room - growth)
            continue

        overflows += 1
        state[addr] = (new_size, 0)

    return {
        "mode": mode,
        "lines_seen": len(state),
        "first_installs": first_installs,
        "rewrites": rewrites,
        "overflow_extra_trips": overflows,
        "writebacks": len(records),
    }


def load_records(path: Path) -> list[tuple[int, int, bytes]]:
    data = path.read_bytes()
    if len(data) % RECORD_SIZE != 0:
        raise ValueError(f"{path}: size {len(data)} not multiple of {RECORD_SIZE}")
    out = []
    for off in range(0, len(data), RECORD_SIZE):
        out.append(struct.unpack_from(RECORD_FMT, data, off))
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("writebacks", type=Path)
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="optional markdown summary path (default: results/stub_replay_<name>.md)",
    )
    args = p.parse_args(argv)

    records = load_records(args.writebacks)
    control = replay(records, "control")
    compresso = replay(records, "compresso")

    name = args.writebacks.parent.name
    out = args.out or Path("results") / f"stub_replay_{name}.md"
    out.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        f"# Stub replay: `{name}`",
        "",
        "Fake compressor only (not real BPC). Proves the trace can drive a",
        "control vs Compresso-style comparison.",
        "",
        f"- writebacks file: `{args.writebacks.as_posix()}`",
        f"- records: **{len(records)}**",
        f"- unique lines: **{control['lines_seen']}**",
        f"- same-line rewrites: **{control['rewrites']}**",
        "",
        "| Mode | Extra trips (overflows) | Lines touched |",
        "|---|---:|---:|",
        f"| Control (naive) | {control['overflow_extra_trips']} | {control['lines_seen']} |",
        f"| Compresso stub | {compresso['overflow_extra_trips']} | {compresso['lines_seen']} |",
        "",
    ]
    if control["rewrites"] == 0:
        lines += [
            "This trace has **no same-line rewrites**, so overflows stay 0 in both",
            "modes. That still validates the file pipeline. A later workload that",
            "rewrites the same addresses (or a longer run of `write_array`) is what",
            "makes control vs Compresso diverge.",
            "",
        ]
    else:
        lines += [
            "If Compresso stub trips < control trips, the inflation-room idea is",
            "visible even with this toy size model.",
            "",
        ]
    lines += [
        "Replace `fake_size` with the real compressor when the group model is ready.",
        "",
    ]
    out.write_text("\n".join(lines), encoding="utf-8")

    print(f"records: {len(records)}")
    print(f"same-line rewrites: {control['rewrites']}")
    print(
        f"control overflows: {control['overflow_extra_trips']}  "
        f"compresso-stub overflows: {compresso['overflow_extra_trips']}"
    )
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
