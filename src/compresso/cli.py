"""Run a compressor over a raw .bin memory dump (Phase 6).

Usage: python -m compresso.cli DUMP.bin --algo bpc --out results/
"""

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="compresso.cli", description=__doc__)
    p.add_argument("dump", help="raw memory dump, read as 64-byte lines")
    p.add_argument("--algo", choices=["bpc", "bdi", "stub"], default="bpc")
    p.add_argument("--out", default="results/", help="output directory for CSV stats")
    p.parse_args(argv)
    print("compresso.cli: not implemented yet (Phase 6)", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
