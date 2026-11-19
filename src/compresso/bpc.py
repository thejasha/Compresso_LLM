"""Bit-Plane Compression (Kim et al., ISCA 2016), as adapted by Compresso (Phases 3-4)."""


def compress_line(line: bytes) -> tuple[bytes, int]:
    """Compress one 64-byte line. Returns (payload, size_bits)."""
    raise NotImplementedError


def decompress_line(payload: bytes, size_bits: int) -> bytes:
    """Inverse of compress_line. Returns the original 64-byte line."""
    raise NotImplementedError
