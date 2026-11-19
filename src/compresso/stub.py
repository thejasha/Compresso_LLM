"""Random-size stand-in compressor so Track B can start before BPC is done (Phase 1)."""


def compress_line(line: bytes) -> tuple[bytes, int]:
    raise NotImplementedError


def decompress_line(payload: bytes, size_bits: int) -> bytes:
    raise NotImplementedError
