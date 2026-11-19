import compresso
from compresso import bdi, bitstream, bpc, cli, stub  # noqa: F401


def test_constants():
    assert compresso.LINE_BYTES == 64
    assert compresso.PAGE_BYTES % compresso.LINE_BYTES == 0


def test_cli_parses_args():
    # Stub CLI exits non-zero until Phase 6, but must parse arguments.
    assert cli.main(["data/sample.bin", "--algo", "bpc"]) == 1
