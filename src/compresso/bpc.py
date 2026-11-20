"""Bit-Plane Compression (Kim et al., ISCA 2016), as adapted by Compresso (Phases 3-4)."""

"""Notes:
Each data block gets transfromed -> Delta BitPlane-XOR (DBX)
1.9x for floating point if we wanted more for LLM usecase.
need to swap compression model. examples of others :iC-pack [13] and Base Delta Immediate [14] 
TLDR -> BPC is general compression, use FPC and RLE after.
BPC is data transfomration before encoding.

can: (1) reduce entropy to increase
potential compressibility; (2) increase the frequency of all-zero
symbols for efficient run-length encoding (RLE); (3) increase
the frequency of other simple patterns for frequent-pattern
compression (FPC); and (4) have a low-latency and low-cost
hardware implementation. 

The DBX transformation is composed of three simple
transformations applied in sequence: Delta that subtracts
neighboring values (Figure 1a); Bit Plane that rotates input
symbols such that each of its output symbol includes one bit
of every input symbol, all at the same bit position (Figure 1b);
and an XOR of neighboring symbols.



OG paper uses 128 Byters -> Compresso uses 64 B
"""

from dataclasses import dataclass

from compresso.bitstream import BitReader, BitWriter

# =============================================================================
# Parameters
#
# Defaults reproduce Compresso (Choukse et al., MICRO'18). Every field says what
# the original BPC paper (Kim et al., ISCA'16) uses and what changing it does.
# Build variants with dataclasses.replace(COMPRESSO, word_bits=32) etc.
# =============================================================================


@dataclass(frozen=True)
class BPCConfig:
    # Compression granularity, in bytes.
    #   Compresso: 64 (one CPU cache line).  BPC paper: 128 (GPU memory block).
    #   Bigger blocks -> more planes per zero run -> better ratio, but more latency
    #   and more data moved per access.
    line_bytes: int = 64

    # Symbol width the line is split into before DBX.
    #   Compresso: 16 (not stated, but its HW model handles "17 bit-planes" per
    #   line = 17-bit deltas = 16-bit words).  BPC paper: 32.
    #   Match the data type: 16 for fp16/bf16 (LLM weights/KV), 32 for fp32/int32,
    #   64 for doubles. Sets plane width: 64 B / 16-bit -> 31-bit planes (paper's
    #   codes fit as-is); 64 B / 32-bit -> 15-bit planes.
    word_bits: int = 16

    # Byte order when reading words out of a line. x86/ARM dumps are little-endian.
    byteorder: str = "little"

    # Also encode the line WITHOUT the DBX transform and keep the smaller result.
    #   Compresso: True ("compresses data with and without the transform, in
    #   parallel, and chooses the best", ~13% more memory saved).  BPC paper: False.
    #   Costs a 1-bit mode flag at the start of every compressed line.
    try_no_transform: bool = True

    # Width of the run-length field in the zero-run code {2'b01, (run-2)[k:0]}.
    #   BPC paper: 5 (runs of 2..33 planes). Compresso: not stated, kept at 5.
    #   With 17 planes the longest run is 17, so 4 bits would be enough.
    run_bits: int = 5

    # Base-word encoder size classes, in bits (Orig Encoder, Fig. 3a).
    #   BPC paper: 0 / 4 / 8 / 16, else raw word. Classes >= word_bits are skipped,
    #   so with 16-bit words this is 0 / 4 / 8, else raw 16 bits.
    base_classes: tuple[int, ...] = (4, 8, 16)

    # Compressed cache-line size bins, in bytes (used by binned_bytes()).
    #   Compresso: 4 bins, 0/8/32/64 B. 8 bins compress better (1.82 vs 1.59)
    #   but cause 17.5% more overflows (MICRO'18 Sec. 4). () = no binning.
    bins: tuple[int, ...] = (0, 8, 32, 64)

    def __post_init__(self):
        if self.word_bits not in (8, 16, 32, 64):
            raise ValueError(f"word_bits must be 8/16/32/64, got {self.word_bits}")
        if (self.line_bytes * 8) % self.word_bits:
            raise ValueError("line_bytes must hold a whole number of words")
        if self.byteorder not in ("little", "big"):
            raise ValueError(f"byteorder must be 'little' or 'big', got {self.byteorder}")
        if len(self.base_classes) > 3:
            raise ValueError("base_classes: at most 3 (codes 001/010/011)")
        if self.run_bits < 1:
            raise ValueError("run_bits must be >= 1")

    # ---- derived sizes (don't set these, they follow from the above) ----
    @property
    def n_words(self) -> int:  # 32 for Compresso
        return self.line_bytes * 8 // self.word_bits

    @property
    def delta_bits(self) -> int:  # 17 for Compresso (word + borrow bit)
        return self.word_bits + 1

    @property
    def n_planes(self) -> int:  # 17 for Compresso: DBP[top] + DBX[top-1..0]
        return self.delta_bits

    @property
    def plane_bits(self) -> int:  # 31 for Compresso (one bit per delta)
        return self.n_words - 1

    @property
    def pos_bits(self) -> int:  # 5 for Compresso: bit index inside a plane
        return (self.plane_bits - 1).bit_length()

    @property
    def base_widths(self) -> tuple[int, ...]:  # (4, 8) for Compresso
        return tuple(b for b in self.base_classes if b < self.word_bits)


COMPRESSO = BPCConfig()
PAPER_BPC = BPCConfig(line_bytes=128, word_bits=32, try_no_transform=False, bins=())



# =============================================================================
# First part: DBX transformation (Fig. 1). All values are plain Python ints.
#
# Bit order inside a plane: bit j of a plane comes from symbol j, so the
# figure's left-most entry ({Delta1, Delta2, ...}) is bit 0 of the int.
# =============================================================================


def _words(line: bytes, cfg: BPCConfig) -> list[int]:
    """Split the line into cfg.n_words unsigned ints of cfg.word_bits, cfg.byteorder."""
    step = cfg.word_bits // 8
    return [int.from_bytes(line[i : i + step], cfg.byteorder) for i in range(0, len(line), step)]


def _delta(words: list[int], cfg: BPCConfig) -> tuple[int, list[int]]:
    """Fig. 1a. Returns (base, deltas).

    base = words[0]; deltas[i-1] = words[i] - words[i-1] as plain signed ints. They always
    fit in cfg.delta_bits signed bits, and >> / & treat negatives as two's complement, so
    no mask is needed. len(deltas) == cfg.plane_bits.
    """

    n = len(words)
    deltas = [words[i] - words[i - 1] for i in range(1, n)]

    return words[0], deltas


def _transpose(values: list[int], nbits: int) -> list[int]:
    """Bit-matrix transpose: out[k] bit j = values[j] bit k. Returns nbits ints of len(values) bits."""
    planes = [0] * nbits
    for j, v in enumerate(values):
        for k in range(nbits):
            if (v >> k) & 1:
                planes[k] |= 1 << j
    return planes


def _bit_plane(deltas: list[int], cfg: BPCConfig) -> list[int]:
    """Fig. 1b. Returns dbp, cfg.n_planes ints of cfg.plane_bits each.

    Bit j of dbp[k] = bit k of deltas[j]. dbp[-1] is the sign plane (DBP16 for Compresso).
    """
    return _transpose(deltas, cfg.delta_bits)


def _xor(dbp: list[int], cfg: BPCConfig) -> list[int]:
    """Fig. 1c. Returns dbx, same length as dbp.

    dbx[k] = dbp[k] ^ dbp[k+1] for k < top; dbx[top] = dbp[top] (sign plane, no neighbour).
    """
    return [dbp[k] ^ dbp[k + 1] for k in range(len(dbp) - 1)] + [dbp[-1]]


def _un_xor(dbx: list[int], cfg: BPCConfig) -> list[int]:
    """Inverse of _xor: dbp[top] = dbx[top], then dbp[k] = dbx[k] ^ dbp[k+1] going down."""
    dbp = list(dbx)
    for k in range(len(dbp) - 2, -1, -1):
        dbp[k] = dbx[k] ^ dbp[k + 1]
    return dbp


def _un_bit_plane(dbp: list[int], cfg: BPCConfig) -> list[int]:
    """Inverse of _bit_plane: transpose planes back into cfg.plane_bits signed deltas."""
    raw = _transpose(dbp, cfg.plane_bits)  # unsigned delta_bits-wide values
    sign = 1 << cfg.word_bits
    return [v - (sign << 1) if v & sign else v for v in raw]  # sign-extend


def _un_delta(base: int, deltas: list[int], cfg: BPCConfig) -> list[int]:
    """Inverse of _delta: prefix sum from base, masked to cfg.word_bits."""
    mask = (1 << cfg.word_bits) - 1
    words = [base]
    for d in deltas:
        words.append((words[-1] + d) & mask)
    return words


def _to_line(words: list[int], cfg: BPCConfig) -> bytes:
    """Inverse of _words."""
    step = cfg.word_bits // 8
    return b"".join(w.to_bytes(step, cfg.byteorder) for w in words)


# =============================================================================
# Second part: Encoding with FWC and VWC (Fig. 3a pipeline, Fig. 3b codes)
#
# Code map (prefix-free):  1xxx  raw plane     01   zero run 2..     001  zero run 1
#                          00000 all 1s        00001 DBX!=0, DBP==0
#                          00010 two 1s + pos  00011 single 1 + pos
# =============================================================================


def _encode_base(w: BitWriter, base: int, cfg: BPCConfig) -> None:
    """Orig Encoder. Shortest of:
    3'b000 (zero) | 3'b001 + 4 bit | 3'b010 + 8 bit | 3'b011 + 16 bit | 1'b1 + raw word.
    Size classes come from cfg.base_widths; value must fit as a *signed* int of that width.
    Codes follow the position in cfg.base_classes, so they match the paper for any word size.
    """
    if base == 0:
        w.write(0b000, 3)
        return
    s = base - (1 << cfg.word_bits) if base >> (cfg.word_bits - 1) else base  # as signed
    for b in cfg.base_widths:
        if -(1 << (b - 1)) <= s < (1 << (b - 1)):
            w.write(cfg.base_classes.index(b) + 1, 3)
            w.write(s, b)  # writer keeps the low b bits = two's complement
            return
    w.write(1, 1)
    w.write(base, cfg.word_bits)


def _decode_base(r: BitReader, cfg: BPCConfig) -> int:
    if r.read(1):
        return r.read(cfg.word_bits)
    c = r.read(2)
    if c == 0:
        return 0
    b = cfg.base_classes[c - 1]
    v = r.read(b)
    if v >> (b - 1):
        v -= 1 << b  # sign-extend
    return v & ((1 << cfg.word_bits) - 1)


def _encode_zero_run(w: BitWriter, run: int, cfg: BPCConfig) -> None:
    """ZBP-RLE. run == 1 -> 3'b001; run >= 2 -> {2'b01, (run - 2)[cfg.run_bits-1:0]}.
    Does nothing for run == 0. Runs longer than the field allows are split.
    """
    max_run = (1 << cfg.run_bits) + 1
    while run > 0:
        chunk = min(run, max_run)
        if chunk == 1:
            w.write(0b001, 3)
        else:
            w.write(0b01, 2)
            w.write(chunk - 2, cfg.run_bits)
        run -= chunk


def _encode_plane(w: BitWriter, x: int, p: int, width: int) -> None:
    """BP Encoder for one NON-zero plane of `width` bits. x = DBX value, p = matching DBP value.
    First match wins:
      all 1s               5'b00000
      x != 0 and p == 0    5'b00001
      two consecutive 1s   5'b00010 + start position (lower bit) [pos_bits]
      single 1             5'b00011 + position                   [pos_bits]
      otherwise            1'b1 + x                              [width]
    """
    pos_bits = (width - 1).bit_length()
    if x == (1 << width) - 1:
        w.write(0b00000, 5)
    elif p == 0:
        w.write(0b00001, 5)
    elif x & (x - 1) == 0:  # exactly one bit set
        w.write(0b00011, 5)
        w.write(x.bit_length() - 1, pos_bits)
    elif (lo := x & -x) * 3 == x:  # exactly two adjacent bits set
        w.write(0b00010, 5)
        w.write(lo.bit_length() - 1, pos_bits)
    else:
        w.write(1, 1)
        w.write(x, width)


def _encode_planes(w: BitWriter, xs: list[int], ps: list[int], width: int, cfg: BPCConfig) -> None:
    """Fig. 3a BP Encoders + ZBP-RLE: planes top-down, zero planes merged into runs."""
    run = 0
    for k in reversed(range(len(xs))):
        if xs[k] == 0:
            run += 1
            continue
        _encode_zero_run(w, run, cfg)
        run = 0
        _encode_plane(w, xs[k], ps[k], width)
    _encode_zero_run(w, run, cfg)


def _decode_planes(r: BitReader, n: int, width: int, cfg: BPCConfig, xor: bool) -> list[int]:
    """Read codes until n planes are rebuilt; returns them with index 0 = lowest plane.

    With xor=True these are DBX planes: the "DBX != 0, DBP == 0" code means
    DBX[k] = DBP[k+1], which is known because planes are decoded top-down.
    """
    pos_bits = (width - 1).bit_length()
    out = [0] * n
    above = 0  # DBP of the plane above the one being decoded
    k = n - 1
    while k >= 0:
        if r.read(1):  # 1 -> raw plane
            x = r.read(width)
        elif r.read(1):  # 01 -> zero run >= 2
            run = r.read(cfg.run_bits) + 2
            for _ in range(run):
                out[k] = 0  # a zero DBX plane means DBP[k] == DBP[k+1]
                k -= 1
            if k < -1:
                raise ValueError("zero run past the last plane")
            continue
        elif r.read(1):  # 001 -> zero run of 1
            k -= 1
            continue
        else:  # 000xx
            op = r.read(2)
            if op == 0b00:
                x = (1 << width) - 1
            elif op == 0b01:
                if not xor or k == n - 1:
                    raise ValueError("DBP==0 code is only valid below the sign plane")
                x = above
            elif op == 0b10:
                x = 0b11 << r.read(pos_bits)
            else:
                x = 1 << r.read(pos_bits)
        out[k] = x
        if xor:
            above = x if k == n - 1 else x ^ above
        k -= 1
    return out


def _encode_dbx(w: BitWriter, line: bytes, cfg: BPCConfig) -> None:
    """Full Fig. 3a path: transform, then base + planes top-down (DBP[top], DBX[top-1]..DBX0)."""
    base, deltas = _delta(_words(line, cfg), cfg)
    dbp = _bit_plane(deltas, cfg)
    dbx = _xor(dbp, cfg)
    _encode_base(w, base, cfg)
    _encode_planes(w, dbx, dbp, cfg.plane_bits, cfg)


def _decode_dbx(r: BitReader, cfg: BPCConfig) -> bytes:
    base = _decode_base(r, cfg)
    dbx = _decode_planes(r, cfg.n_planes, cfg.plane_bits, cfg, xor=True)
    deltas = _un_bit_plane(_un_xor(dbx, cfg), cfg)
    return _to_line(_un_delta(base, deltas, cfg), cfg)


def _encode_no_transform(w: BitWriter, line: bytes, cfg: BPCConfig) -> None:
    """Compresso's "without the transform" path (cfg.try_no_transform).

    The paper doesn't define it. OUR CHOICE: no Delta and no XOR. Bit-plane the raw
    words (cfg.word_bits planes of cfg.n_words bits) and run the same encoder. That
    keeps the zero-run and few-1s patterns but skips the delta, which helps lines
    with no value locality (e.g. sparse or mixed data). There is no base word, and
    the "DBX!=0, DBP==0" code is never used (x == p here).
    """
    planes = _transpose(_words(line, cfg), cfg.word_bits)
    _encode_planes(w, planes, planes, cfg.n_words, cfg)


def _decode_no_transform(r: BitReader, cfg: BPCConfig) -> bytes:
    planes = _decode_planes(r, cfg.word_bits, cfg.n_words, cfg, xor=False)
    return _to_line(_transpose(planes, cfg.n_words), cfg)


# =============================================================================
# Public API
# =============================================================================


def compress_line(line: bytes, cfg: BPCConfig = COMPRESSO) -> tuple[bytes, int]:
    """Compress one line. Returns (payload, size_bits).

    With cfg.try_no_transform the payload starts with a 1-bit mode flag
    (0 = DBX, 1 = no transform) and the smaller encoding is kept.
    """
    if len(line) != cfg.line_bytes:
        raise ValueError(f"expected {cfg.line_bytes} bytes, got {len(line)}")

    candidates = [(0, _encode_dbx)]
    if cfg.try_no_transform:
        candidates.append((1, _encode_no_transform))

    best = None
    for mode, encode in candidates:
        w = BitWriter()
        if cfg.try_no_transform:
            w.write(mode, 1)
        encode(w, line, cfg)
        if best is None or w.bit_length < best.bit_length:
            best = w
    return best.to_bytes(), best.bit_length


def decompress_line(payload: bytes, size_bits: int, cfg: BPCConfig = COMPRESSO) -> bytes:
    """Inverse of compress_line (must use the same cfg). Returns the original line."""
    r = BitReader(payload, size_bits)
    if cfg.try_no_transform and r.read(1) == 1:
        line = _decode_no_transform(r, cfg)
    else:
        line = _decode_dbx(r, cfg)
    if r.remaining:
        raise ValueError(f"{r.remaining} unused bits after decoding")
    return line


def binned_bytes(line: bytes, size_bits: int, cfg: BPCConfig = COMPRESSO) -> int:
    """Bytes the line takes in memory after rounding up to a size bin.

    An all-zero line uses the 0 B bin (it lives only in metadata). Anything that
    doesn't fit a smaller bin is stored uncompressed in the largest one.
    """
    if not cfg.bins:
        return min(-(-size_bits // 8), cfg.line_bytes)
    if not any(line) and 0 in cfg.bins:
        return 0
    need = -(-size_bits // 8)
    return next((b for b in sorted(cfg.bins) if b and b >= need), max(cfg.bins))
