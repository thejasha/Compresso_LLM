"""Walk the BPC paper's own examples through every step of bpc.py and print each stage.

Use it next to papers/isca2016_bpc.pdf to compare numbers:
  Part 1  Fig. 1a/1b (page 5): 8 x 8-bit symbols 0x00..0x07
  Part 2  Fig. 1c   (page 5): 128 B block of 32 x 32-bit words, Base 0x803F_0000
  Part 3  Fig. 3a/3b (page 8): encoding that Fig. 1c block, code by code
  Part 4  Round trip + final size

Plane bit order matches the figure: the left-most entry of a plane is Delta1
(bit 0 of the int). Words marked "filler" are hidden behind "..." in Fig. 1c;
we fill them with small +4 steps, same as tests/test_bpc.py.

Run:  .venv/bin/python scripts/trace_bpc.py
"""

from compresso import bpc
from compresso.bitstream import BitWriter

# ---------------------------------------------------------------------------
# Inputs (same as tests/test_bpc.py)
# ---------------------------------------------------------------------------

ORIG_8 = list(range(8))
FIG1_8x8 = bpc.BPCConfig(line_bytes=8, word_bits=8, try_no_transform=False, bins=())

FIG1C_SHOWN = [0x803F_0000, 0x803F_0004, 0x803F_0040, 0x803F_0044, 0x803F_0020]
FIG1C_FILL = [0x803F_0020 + 4 * i for i in range(1, 25)] + [0x803F_0080, 0x803F_0080]
FIG1C_WORDS = FIG1C_SHOWN + FIG1C_FILL + [0x803F_0084]
FIG1C_LINE = b"".join(w.to_bytes(4, "little") for w in FIG1C_WORDS)
SHOWN_IDX = {0, 1, 2, 3, 4, 31}  # words printed in the figure

CFG = bpc.PAPER_BPC  # 128 B, 32-bit words, no "without transform" path, no bins


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def header(title: str) -> None:
    print("\n" + "=" * 78 + f"\n{title}\n" + "=" * 78)


def plane_str(plane: int, width: int, group: int = 4) -> str:
    """Figure order: left-most char = bit 0 (Delta1). Grouped for readability."""
    s = "".join(str((plane >> j) & 1) for j in range(width))
    return " ".join(s[i : i + group] for i in range(0, width, group))


def signed_hex(v: int) -> str:
    return f"-0x{-v:02X}" if v < 0 else f"+0x{v:02X}"


def bitstring(w: BitWriter) -> str:
    n = w.bit_length
    if n == 0:
        return ""
    return format(int.from_bytes(w.to_bytes(), "big") >> (-n % 8), f"0{n}b")


def written(fn, *args) -> str:
    """Run one encoder call on a fresh writer and return the bits it wrote."""
    w = BitWriter()
    fn(w, *args)
    return bitstring(w)


def plane_kind(x: int, p: int, width: int) -> str:
    """Same priority as bpc._encode_plane, as a label."""
    if x == (1 << width) - 1:
        return "all 1s"
    if p == 0:
        return "DBX!=0, DBP==0"
    if x & (x - 1) == 0:
        return f"single 1 @ pos {x.bit_length() - 1}"
    if (lo := x & -x) * 3 == x:
        return f"two 1s @ pos {lo.bit_length() - 1}"
    return "uncompressed"


# ---------------------------------------------------------------------------
# Part 1: Fig. 1a / 1b
# ---------------------------------------------------------------------------


def part1() -> None:
    header("PART 1  Fig. 1a/1b: 8 x 8-bit symbols")
    print("Orig0..Orig7:", " ".join(f"0x{v:02X}" for v in ORIG_8))

    base, deltas = bpc._delta(ORIG_8, FIG1_8x8)
    print("\n[Fig. 1a] Delta")
    print(f"  Base   = 0x{base:02X}")
    print("  Delta1..Delta7 =", " ".join(signed_hex(d) for d in deltas))

    print("\n[Fig. 1b] BitPlane of the ORIGINAL symbols (no delta), entries Orig0..Orig7")
    bp = bpc._transpose(ORIG_8, 8)
    for k in reversed(range(8)):
        print(f"  BP{k}: {plane_str(bp[k], 8, 8)}")


# ---------------------------------------------------------------------------
# Part 2: Fig. 1c transform
# ---------------------------------------------------------------------------


def part2():
    header("PART 2  Fig. 1c: DBX transform of a 128 B block (PAPER_BPC config)")

    print("[Input] 128 bytes, little-endian, first 32 bytes:")
    print("  " + FIG1C_LINE[:32].hex(" "))

    words = bpc._words(FIG1C_LINE, CFG)
    print("\n[Step 1] Split into 32 x 32-bit words")
    for i, w in enumerate(words):
        tag = "" if i in SHOWN_IDX else "   (filler)"
        print(f"  Orig{i:<2} = 0x{w >> 16:04X}_{w & 0xFFFF:04X}{tag}")

    base, deltas = bpc._delta(words, CFG)
    print("\n[Step 2] Delta  (Fig. 1c, 'Delta' row; 33-bit signed deltas)")
    print(f"  Base    = 0x{base >> 16:04X}_{base & 0xFFFF:04X}")
    for i, d in enumerate(deltas, start=1):
        tag = "" if i in {1, 2, 3, 4, 31} else "   (filler)"
        print(f"  Delta{i:<2} = {signed_hex(d)}{tag}")

    dbp = bpc._bit_plane(deltas, CFG)
    print("\n[Step 3] BitPlane -> DBP32..DBP0  (31 bits each, left = Delta1)")
    print("  Compare the first 4 entries of each row with the figure.")
    for k in reversed(range(CFG.n_planes)):
        print(f"  DBP{k:<2}: {plane_str(dbp[k], CFG.plane_bits)}")

    dbx = bpc._xor(dbp, CFG)
    print("\n[Step 4] XOR -> DBP32 kept, DBXk = DBPk ^ DBP(k+1)")
    for k in reversed(range(CFG.n_planes)):
        name = f"DBP{k}" if k == CFG.n_planes - 1 else f"DBX{k}"
        zero = "   <- all-zero" if dbx[k] == 0 else ""
        print(f"  {name:<5}: {plane_str(dbx[k], CFG.plane_bits)}{zero}")
    nz = sum(1 for x in dbx if x == 0)
    print(f"\n  {nz} of {len(dbx)} planes are all-zero (figure: DBX0, DBX3, DBX6..DBX31)")
    return base, dbp, dbx


# ---------------------------------------------------------------------------
# Part 3: Fig. 3a/3b encoding
# ---------------------------------------------------------------------------


def part3(base: int, dbp: list[int], dbx: list[int]) -> int:
    header("PART 3  Fig. 3a/3b: encode Base, then planes top-down with ZBP-RLE")
    width = CFG.plane_bits
    total = 0

    bits = written(bpc._encode_base, base, CFG)
    total += len(bits)
    print(f"[Base]  0x{base:08X} -> {bits}  ({len(bits)} bits; doesn't fit 4/8/16 signed -> raw)")

    print("\n[Planes]  (zero planes are buffered until the next non-zero plane)")
    print(f"  {'plane':<6} {'kind':<26} {'code':<40} bits")
    run, run_top = 0, None

    def flush(run: int, run_top: int | None) -> int:
        if run == 0:
            return 0
        bits = written(bpc._encode_zero_run, run, CFG)
        lo = run_top - run + 1
        span = f"{run_top}..{lo}" if run > 1 else f"{run_top}"
        print(f"  {'':<6} {'zero run x' + str(run) + ' (' + span + ')':<26} {bits:<40} {len(bits)}")
        return len(bits)

    for k in reversed(range(len(dbx))):
        if dbx[k] == 0:
            if run == 0:
                run_top = k
            run += 1
            continue
        total += flush(run, run_top)
        run = 0
        bits = written(bpc._encode_plane, dbx[k], dbp[k], width)
        name = f"DBP{k}" if k == len(dbx) - 1 else f"DBX{k}"
        shown = bits if len(bits) <= 40 else bits[:36] + "..."
        print(f"  {name:<6} {plane_kind(dbx[k], dbp[k], width):<26} {shown:<40} {len(bits)}")
        total += len(bits)
    total += flush(run, run_top)

    print("\n  Note: codes are in stream order (MSB first), so an uncompressed plane's 31 bits")
    print("  read Delta31..Delta1, the reverse of the plane rows printed in Part 2.")
    print(f"\n  Total: {total} bits")
    return total


# ---------------------------------------------------------------------------
# Part 4: public API, round trip, ratio
# ---------------------------------------------------------------------------


def part4(traced_bits: int) -> None:
    header("PART 4  compress_line / decompress_line")
    payload, n = bpc.compress_line(FIG1C_LINE, CFG)
    print(f"compress_line -> {n} bits ({len(payload)} bytes)   traced above: {traced_bits} bits")
    print(f"payload: {payload.hex(' ')}")
    back = bpc.decompress_line(payload, n, CFG)
    print(f"round trip ok: {back == FIG1C_LINE}")
    raw = CFG.line_bytes * 8
    print(f"ratio: {raw} / {n} = {raw / n:.2f}x")

    # Same 128 B through Compresso's config (2 x 64 B lines, 16-bit words, bins)
    print("\nFor comparison, Compresso config (64 B lines, 16-bit words, 0/8/32/64 B bins):")
    for i in range(0, 128, 64):
        line = FIG1C_LINE[i : i + 64]
        p, nb = bpc.compress_line(line, bpc.COMPRESSO)
        mode = "no-transform" if p[0] >> 7 else "DBX"
        print(
            f"  bytes {i:>3}..{i + 63:<3}: {nb:>3} bits via {mode:<12} "
            f"-> {bpc.binned_bytes(line, nb)} B bin"
        )


if __name__ == "__main__":
    part1()
    base, dbp, dbx = part2()
    traced = part3(base, dbp, dbx)
    part4(traced)
