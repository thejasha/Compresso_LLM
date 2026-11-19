"""Base-Delta-Immediate compression, used as a baseline."""


def compress_line(line: bytes) -> tuple[bytes, int]:
    raise NotImplementedError


def decompress_line(payload: bytes, size_bits: int) -> bytes:
    raise NotImplementedError
