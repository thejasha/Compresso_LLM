import compresso
from compresso import bdi, bitstream, bpc, cli, stub  # noqa: F401


def test_constants():
    assert compresso.LINE_BYTES == 64
    assert compresso.PAGE_BYTES % compresso.LINE_BYTES == 0


def test_cli_parses_args():
    # Stub CLI exits non-zero until Phase 6, but must parse arguments.
    assert cli.main(["data/sample.bin", "--algo", "bpc"]) == 1


def test_bpc_config_defaults_are_compresso():
    c = bpc.COMPRESSO
    assert (c.line_bytes, c.word_bits, c.try_no_transform, c.bins) == (64, 16, True, (0, 8, 32, 64))
    assert (c.n_words, c.n_planes, c.plane_bits, c.pos_bits) == (32, 17, 31, 5)  # "17 bit-planes"
    assert c.base_widths == (4, 8)


def test_bpc_config_variants():
    import dataclasses

    c32 = dataclasses.replace(bpc.COMPRESSO, word_bits=32)
    assert (c32.n_words, c32.n_planes, c32.plane_bits, c32.pos_bits) == (16, 33, 15, 4)
    p = bpc.PAPER_BPC
    assert (p.n_words, p.n_planes, p.plane_bits, p.pos_bits) == (32, 33, 31, 5)


def test_binned_bytes():
    z, nz = bytes(64), b"\x01" + bytes(63)
    assert bpc.binned_bytes(z, 10) == 0
    assert bpc.binned_bytes(nz, 64) == 8
    assert bpc.binned_bytes(nz, 65) == 32
    assert bpc.binned_bytes(nz, 300) == 64
    assert bpc.binned_bytes(nz, 600) == 64  # didn't compress -> stored raw


def test_cli_word_bits():
    assert cli.main(["data/sample.bin", "--word-bits", "32"]) == 1
