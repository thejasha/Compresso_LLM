"""Bit-level writer/reader used by the compressors (Phase 2)."""


class BitWriter:
    def write(self, value: int, nbits: int) -> None:
        raise NotImplementedError


class BitReader:
    def read(self, nbits: int) -> int:
        raise NotImplementedError
