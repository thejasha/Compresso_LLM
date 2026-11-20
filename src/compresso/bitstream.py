"""Bit-level writer/reader used by the compressors (Phase 2).

Bit order: MSB-first. write(0b101, 3) then write(0b1, 1) gives the stream 1011.
Both sides keep the whole stream in one Python int, which is simple and fast
enough for 64 B lines.
"""


class BitWriter:
    def __init__(self) -> None:
        self._acc = 0
        self._n = 0

    def write(self, value: int, nbits: int) -> None:
        """Append the low `nbits` bits of `value`."""
        if nbits < 0:
            raise ValueError("nbits must be >= 0")
        self._acc = (self._acc << nbits) | (value & ((1 << nbits) - 1))
        self._n += nbits

    @property
    def bit_length(self) -> int:
        """Number of bits written so far."""
        return self._n

    def to_bytes(self) -> bytes:
        """The stream, zero-padded at the end to a whole byte."""
        nbytes = (self._n + 7) // 8
        return (self._acc << (nbytes * 8 - self._n)).to_bytes(nbytes, "big")


class BitReader:
    def __init__(self, data: bytes, nbits: int) -> None:
        """Read the first `nbits` bits of `data` (as produced by BitWriter.to_bytes)."""
        if nbits > len(data) * 8:
            raise ValueError(f"nbits={nbits} but data has only {len(data) * 8} bits")
        self._acc = int.from_bytes(data, "big") >> (len(data) * 8 - nbits)
        self._n = nbits
        self._pos = 0

    def read(self, nbits: int) -> int:
        if self._pos + nbits > self._n:
            raise EOFError(f"read {nbits} bits at {self._pos}, stream is {self._n} bits")
        self._pos += nbits
        return (self._acc >> (self._n - self._pos)) & ((1 << nbits) - 1)

    @property
    def remaining(self) -> int:
        return self._n - self._pos
