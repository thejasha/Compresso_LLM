"""BPC tests.

The first block reproduces Fig. 1 of the BPC paper (Kim et al., ISCA'16, page 5)
with the exact numbers printed in the figure. The figure lists bit-plane
entries left to right as {Delta1, Delta2, ...}; in our ints that left-most
entry is bit 0 (see the bit-order note in bpc.py).
"""

import math
import os
from collections import Counter
from dataclasses import replace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from compresso import bpc
from compresso.bitstream import BitReader, BitWriter


def bits(plane: int, n: int) -> list[int]:
    """First n entries of a plane, figure order (left-most = bit 0)."""
    return [(plane >> j) & 1 for j in range(n)]


def entropy(symbols: list[int]) -> float:
    counts = Counter(symbols)
    return -sum(c / len(symbols) * math.log2(c / len(symbols)) for c in counts.values())


# ---------------------------------------------------------------------------
# Fig. 1a / 1b: 8 x 8-bit symbols, Orig0..Orig7 = 0x00..0x07
# ---------------------------------------------------------------------------

FIG1_8x8 = bpc.BPCConfig(line_bytes=8, word_bits=8, try_no_transform=False, bins=())
ORIG_8 = list(range(8))


def test_fig1a_delta():
    base, deltas = bpc._delta(ORIG_8, FIG1_8x8)
    assert base == 0x00  # Base = Orig0 = 0x00
    assert deltas == [0x01] * 7  # Delta1..Delta7 = 0x01


def test_fig1a_entropy():
    assert entropy(ORIG_8) == pytest.approx(3.0)  # "Entropy = 3"
    base, deltas = bpc._delta(ORIG_8, FIG1_8x8)
    # p0 = 1/8, p1 = 7/8. The paper prints 0.75, but its own formula
    # 1/8*log2(8) + 7/8*log2(8/7) evaluates to 0.544.
    assert entropy([base, *deltas]) == pytest.approx(0.5436, abs=1e-3)


def test_fig1b_bitplanes():
    bp = bpc._transpose(ORIG_8, 8)  # BitPlane on the original symbols, no Delta
    assert bits(bp[0], 8) == [0, 1, 0, 1, 0, 1, 0, 1]  # BP0
    assert bits(bp[1], 8) == [0, 0, 1, 1, 0, 0, 1, 1]  # BP1
    assert bits(bp[2], 8) == [0, 0, 0, 0, 1, 1, 1, 1]  # BP2
    assert bp[3:] == [0] * 5  # BP3..BP7 all zero


def test_fig1b_entropy():
    # p0 = 5/8, p0x0F = p0x33 = p0x55 = 1/8 -> 5/8*log2(8/5) + 3/8*3 = 1.549 ("1.5")
    assert entropy(bpc._transpose(ORIG_8, 8)) == pytest.approx(1.549, abs=1e-3)


# ---------------------------------------------------------------------------
# Fig. 1c: 128 B = 32 x 32-bit, the paper's own configuration
# ---------------------------------------------------------------------------

# Values printed in the figure: Orig0..Orig4 and Orig31 (Delta31 = +0x04 -> Orig30 = 0x803F_0080).
# Orig5..Orig29 are elided ("...") in the figure. Filler: +4 steps up to 0x803F_0080,
# which gives 24 deltas of +4 and two of 0. Only the figure's entries are checked
# exactly; the filler keeps every other delta small, like the figure implies.
FIG1C_SHOWN = [0x803F_0000, 0x803F_0004, 0x803F_0040, 0x803F_0044, 0x803F_0020]
FIG1C_FILL = [0x803F_0020 + 4 * i for i in range(1, 25)] + [0x803F_0080, 0x803F_0080]
FIG1C_WORDS = FIG1C_SHOWN + FIG1C_FILL + [0x803F_0084]
FIG1C_LINE = b"".join(w.to_bytes(4, "little") for w in FIG1C_WORDS)


def _fig1c():
    cfg = bpc.PAPER_BPC
    words = bpc._words(FIG1C_LINE, cfg)
    base, deltas = bpc._delta(words, cfg)
    dbp = bpc._bit_plane(deltas, cfg)
    dbx = bpc._xor(dbp, cfg)
    return words, base, deltas, dbp, dbx


def test_fig1c_words():
    words, *_ = _fig1c()
    assert len(words) == 32
    assert words[:5] == FIG1C_SHOWN
    assert words[31] == 0x803F_0084


def test_fig1c_delta():
    _, base, deltas, _, _ = _fig1c()
    assert base == 0x803F_0000
    assert deltas[:4] == [+0x04, +0x3C, +0x04, -0x24]  # Delta1..Delta4
    assert deltas[30] == +0x04  # Delta31
    assert len(deltas) == 31  # "33-bit delta sym" x 31


def test_fig1c_dbp():
    _, _, _, dbp, _ = _fig1c()
    assert len(dbp) == 33  # DBP0..DBP32, "31-bit DBP sym"
    shown = {  # first four entries of each plane as printed in the figure
        32: [0, 0, 0, 1],
        31: [0, 0, 0, 1],
        30: [0, 0, 0, 1],
        7: [0, 0, 0, 1],
        6: [0, 0, 0, 1],
        5: [0, 1, 0, 0],
        4: [0, 1, 0, 1],
        3: [0, 1, 0, 1],
        2: [1, 1, 1, 1],
        1: [0, 0, 0, 0],
        0: [0, 0, 0, 0],
    }
    for k, want in shown.items():
        assert bits(dbp[k], 4) == want, f"DBP{k}"
    # last entry (Delta31 = +4): only bit 2 set
    assert [(dbp[k] >> 30) & 1 for k in range(33)] == [1 if k == 2 else 0 for k in range(33)]


def test_fig1c_dbx():
    _, _, _, dbp, dbx = _fig1c()
    assert dbx[32] == dbp[32]  # sign plane kept as is
    shown = {
        31: [0, 0, 0, 0],
        30: [0, 0, 0, 0],
        7: [0, 0, 0, 0],
        6: [0, 0, 0, 0],
        5: [0, 1, 0, 1],
        4: [0, 0, 0, 1],
        3: [0, 0, 0, 0],
        2: [1, 0, 1, 0],
        1: [1, 1, 1, 1],
        0: [0, 0, 0, 0],
    }
    for k, want in shown.items():
        assert bits(dbx[k], 4) == want, f"DBX{k}"
    # "All-zero symbols": DBX0, DBX3 and DBX6..DBX31 are zero across the whole block
    assert all(dbx[k] == 0 for k in [0, 3, *range(6, 32)])


def test_fig1c_round_trip():
    payload, n = bpc.compress_line(FIG1C_LINE, bpc.PAPER_BPC)
    assert bpc.decompress_line(payload, n, bpc.PAPER_BPC) == FIG1C_LINE
    assert n < 1024 // 4  # the figure's block compresses well over 4x


# ---------------------------------------------------------------------------
# Fig. 3b codes and the base encoder
# ---------------------------------------------------------------------------


def _plane_code(x, p, width=31):
    w = BitWriter()
    bpc._encode_plane(w, x, p, width)
    return format(int.from_bytes(w.to_bytes(), "big") >> (-w.bit_length % 8), f"0{w.bit_length}b")


def test_plane_codes():
    assert _plane_code((1 << 31) - 1, 1) == "00000"  # all 1s
    assert _plane_code(0b1010, 0) == "00001"  # DBX != 0, DBP == 0
    assert _plane_code(0b11 << 7, 1) == "00010" + "00111"  # two 1s at 7
    assert _plane_code(1 << 30, 1) == "00011" + "11110"  # single 1 at 30
    assert _plane_code(0b101, 1) == "1" + format(0b101, "031b")  # uncompressed, 32 bits


def _zero_run_code(run):
    w = BitWriter()
    bpc._encode_zero_run(w, run, bpc.COMPRESSO)
    return format(int.from_bytes(w.to_bytes(), "big") >> (-w.bit_length % 8), f"0{w.bit_length}b")


def test_zero_run_codes():
    assert _zero_run_code(1) == "001"
    assert _zero_run_code(2) == "01" + "00000"
    assert _zero_run_code(17) == "01" + "01111"
    assert _zero_run_code(33) == "01" + "11111"
    assert _zero_run_code(34) == "01" + "11111" + "001"  # split when longer than the field


@pytest.mark.parametrize(
    "cfg, base, nbits",
    [
        (bpc.COMPRESSO, 0, 3),
        (bpc.COMPRESSO, 7, 7),  # 4-bit class
        (bpc.COMPRESSO, 0xFFF8, 7),  # -8 as 16-bit -> 4-bit class
        (bpc.COMPRESSO, 100, 11),  # 8-bit class
        (bpc.COMPRESSO, 1000, 17),  # 16-bit word: no 16-bit class, raw = 1 + 16
        (bpc.PAPER_BPC, 1000, 19),  # 32-bit word: 16-bit class
        (bpc.PAPER_BPC, 0x803F_0000, 33),  # Fig. 1c base: raw = 1 + 32
    ],
)
def test_base_encoder(cfg, base, nbits):
    w = BitWriter()
    bpc._encode_base(w, base, cfg)
    assert w.bit_length == nbits
    assert bpc._decode_base(BitReader(w.to_bytes(), w.bit_length), cfg) == base


# ---------------------------------------------------------------------------
# Round trips
# ---------------------------------------------------------------------------

CONFIGS = {
    "compresso": bpc.COMPRESSO,
    "compresso_dbx_only": replace(bpc.COMPRESSO, try_no_transform=False),
    "word32": replace(bpc.COMPRESSO, word_bits=32),
    "word8": replace(bpc.COMPRESSO, word_bits=8),
    "word64": replace(bpc.COMPRESSO, word_bits=64),
    "paper": bpc.PAPER_BPC,
    "big_endian": replace(bpc.COMPRESSO, byteorder="big"),
}


@pytest.mark.parametrize("name", CONFIGS)
@settings(max_examples=200, deadline=None)
@given(data=st.data())
def test_round_trip_random(name, data):
    cfg = CONFIGS[name]
    line = data.draw(st.binary(min_size=cfg.line_bytes, max_size=cfg.line_bytes))
    payload, n = bpc.compress_line(line, cfg)
    assert bpc.decompress_line(payload, n, cfg) == line


@pytest.mark.parametrize("name", CONFIGS)
@settings(max_examples=200, deadline=None)
@given(data=st.data())
def test_round_trip_structured(name, data):
    """Small deltas and repeated words hit the zero-run and few-1s codes far more than random bytes."""
    cfg = CONFIGS[name]
    mask = (1 << cfg.word_bits) - 1
    start = data.draw(st.integers(0, mask))
    steps = data.draw(st.lists(st.integers(-9, 9), min_size=cfg.n_words - 1, max_size=cfg.n_words - 1))
    words = [start]
    for s in steps:
        words.append((words[-1] + s) & mask)
    line = bpc._to_line(words, cfg)
    payload, n = bpc.compress_line(line, cfg)
    assert bpc.decompress_line(payload, n, cfg) == line


@pytest.mark.parametrize("name", CONFIGS)
def test_transform_inverts(name):
    cfg = CONFIGS[name]
    for _ in range(50):
        line = os.urandom(cfg.line_bytes)
        base, deltas = bpc._delta(bpc._words(line, cfg), cfg)
        dbp = bpc._bit_plane(deltas, cfg)
        assert bpc._un_xor(bpc._xor(dbp, cfg), cfg) == dbp
        assert bpc._un_bit_plane(dbp, cfg) == deltas
        assert bpc._to_line(bpc._un_delta(base, deltas, cfg), cfg) == line


# ---------------------------------------------------------------------------
# Sizes
# ---------------------------------------------------------------------------


def test_zero_line_is_tiny():
    _, n = bpc.compress_line(bytes(64))
    assert n == 8  # flag + one zero-run code over all 16 raw planes
    assert bpc.binned_bytes(bytes(64), n) == 0


def test_random_line_expands_slightly_then_bins_to_64():
    line = os.urandom(64)
    _, n = bpc.compress_line(line)
    assert 512 <= n <= 600
    assert bpc.binned_bytes(line, n) == 64


def test_dbx_wins_on_ascending_words():
    line = bpc._to_line([1000 + 4 * i for i in range(32)], bpc.COMPRESSO)
    payload, n = bpc.compress_line(line)
    assert payload[0] >> 7 == 0  # mode flag 0 = DBX path chosen
    assert bpc.binned_bytes(line, n) == 8


def test_dbp_zero_code_round_trips(monkeypatch):
    """Deltas of only 0 and 2: DBP0 == 0 but DBP1 isn't, so DBX0 = DBP1 uses the 5'b00001 code."""
    used = []
    real = bpc._encode_plane

    def spy(w, x, p, width):
        used.append(p == 0 and x != (1 << width) - 1)
        real(w, x, p, width)

    monkeypatch.setattr(bpc, "_encode_plane", spy)
    steps = [2, 0, 2, 2, 0, 0, 2, 0] * 4
    words = [500]
    for s in steps[:31]:
        words.append(words[-1] + s)
    line = bpc._to_line(words, bpc.COMPRESSO)
    payload, n = bpc.compress_line(line)
    assert any(used)
    assert bpc.decompress_line(payload, n) == line
