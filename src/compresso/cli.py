"""Run a compressor over a raw .bin memory dump and write CSV stats (issue #3).

Usage:
  python -m compresso.cli DUMP.bin [--algo bpc] [--out results/] [options]

If DUMP.json exists next to the dump it is read as the sidecar (format in
data/README.md) and results are also split by tag, dtype and kind.

Outputs, in --out:
  NAME.ALGO.summary.csv  one row per group (all / tag / dtype / kind)
  NAME.ALGO.lines.csv    one row per line, only with --per-line (large!)

Page-level numbers (512 B page packing, metadata) come from the page model, #2.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import dataclass, field, replace
from pathlib import Path

from compresso import bdi, bpc, stub
from compresso.dump import UNTAGGED, Sidecar, iter_lines, load_sidecar, sidecar_path, tail_bytes

ALGOS = {"bpc": bpc, "bdi": bdi, "stub": stub}

SUMMARY_FIELDS = [
    "dump", "algo", "line_bytes", "word_bits", "try_no_transform", "bins",
    "group_by", "group",
    "lines", "zero_lines", "zero_line_pct",
    "orig_bytes", "compressed_bits", "unbinned_bytes", "binned_bytes",
    "ratio_unbinned", "ratio_binned", "bin_hist",
]  # fmt: skip


@dataclass
class GroupStats:
    """Running totals for one group of lines. Constant size, whatever the dump size."""

    lines: int = 0
    zero_lines: int = 0
    compressed_bits: int = 0
    unbinned_bytes: int = 0  # ceil(bits / 8), capped at the line size (raw fallback)
    binned_bytes: int = 0  # after rounding up to a size bin
    bin_hist: Counter = field(default_factory=Counter)

    def add(self, is_zero: bool, size_bits: int, unbinned: int, binned: int) -> None:
        self.lines += 1
        self.zero_lines += is_zero
        self.compressed_bits += size_bits
        self.unbinned_bytes += unbinned
        self.binned_bytes += binned
        self.bin_hist[binned] += 1


def _ratio(orig: int, comp: int) -> float:
    return orig / comp if comp else float("inf")


def _parse_bins(text: str) -> tuple[int, ...]:
    if text.lower() in ("none", ""):
        return ()
    try:
        return tuple(sorted(int(b) for b in text.split(",")))
    except ValueError:
        raise argparse.ArgumentTypeError(f"bins must be comma-separated ints or 'none': {text!r}")


def _positive_int(text: str) -> int:
    try:
        n = int(text)
    except ValueError:
        n = 0
    if n < 1:
        raise argparse.ArgumentTypeError(f"must be a positive integer: {text!r}")
    return n


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="compresso.cli", description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    p.add_argument("dump", help="raw memory dump (.bin), read as fixed-size lines")
    p.add_argument("--algo", choices=sorted(ALGOS), default="bpc")
    p.add_argument("--out", default="results/", help="output directory (default: results/)")

    g = p.add_argument_group("BPC config (defaults = Compresso)")
    g.add_argument(
        "--word-bits",
        type=int,
        choices=[8, 16, 32, 64],
        default=None,
        help="BPC symbol width (Compresso: 16, original BPC: 32)",
    )
    g.add_argument(
        "--no-transform-path",
        action="store_true",
        help="disable Compresso's 'without transform' path (original BPC behaviour)",
    )
    g.add_argument(
        "--bins",
        type=_parse_bins,
        default=None,
        help="line size bins in bytes, e.g. 0,8,32,64 (default), or 'none'",
    )
    g.add_argument(
        "--line-bytes",
        type=_positive_int,
        default=None,
        help="compression granularity in bytes (default 64; needs --bins if not 64)",
    )

    s = p.add_argument_group("input / output")
    s.add_argument("--sidecar", default=None, help="sidecar JSON (default: DUMP with .json)")
    s.add_argument("--no-sidecar", action="store_true", help="ignore any sidecar")
    s.add_argument("--per-line", action="store_true", help="also write the per-line CSV")
    s.add_argument("--limit-lines", type=_positive_int, default=None, help="only read the first N lines")
    s.add_argument("--chunk-lines", type=_positive_int, default=1 << 16, help=argparse.SUPPRESS)
    s.add_argument("-q", "--quiet", action="store_true", help="don't print the summary table")
    return p  # fmt: skip


def build_config(args: argparse.Namespace) -> bpc.BPCConfig:
    cfg = bpc.COMPRESSO
    if args.word_bits is not None:
        cfg = replace(cfg, word_bits=args.word_bits)
    if args.no_transform_path:
        cfg = replace(cfg, try_no_transform=False)
    if args.line_bytes is not None:
        if args.bins is None and args.line_bytes != cfg.line_bytes:
            raise ValueError("--line-bytes other than 64 needs explicit --bins (or --bins none)")
        cfg = replace(cfg, line_bytes=args.line_bytes)
    if args.bins is not None:
        cfg = replace(cfg, bins=args.bins)
    if cfg.bins and max(cfg.bins) != cfg.line_bytes:
        raise ValueError(f"largest bin must equal the line size ({cfg.line_bytes} B): {cfg.bins}")
    return cfg


def make_compressor(algo: str, cfg: bpc.BPCConfig) -> Callable[[bytes], tuple[bytes, int]]:
    if algo == "bpc":
        return lambda line: bpc.compress_line(line, cfg)
    return ALGOS[algo].compress_line


def run(
    dump: Path,
    compress: Callable[[bytes], tuple[bytes, int]],
    cfg: bpc.BPCConfig,
    sidecar: Sidecar | None = None,
    per_line_writer=None,
    limit_lines: int | None = None,
    chunk_lines: int = 1 << 16,
) -> dict[tuple[str, str], GroupStats]:
    """Compress every line; return stats keyed by (group_by, group)."""
    stats: dict[tuple[str, str], GroupStats] = {}

    def get(key: tuple[str, str]) -> GroupStats:
        if key not in stats:
            stats[key] = GroupStats()
        return stats[key]

    total = get(("all", "all"))
    for offset, line in iter_lines(dump, cfg.line_bytes, chunk_lines, limit_lines):
        _, size_bits = compress(line)
        is_zero = not any(line)
        unbinned = min(-(-size_bits // 8), cfg.line_bytes)
        binned = bpc.binned_bytes(line, size_bits, cfg)
        total.add(is_zero, size_bits, unbinned, binned)

        tag = UNTAGGED
        if sidecar is not None:
            region = sidecar.region_at(offset)  # line belongs to the region it starts in
            tag = region.tag if region else UNTAGGED
            dtype = region.dtype if region else UNTAGGED
            kind = region.kind if region else UNTAGGED
            for key in (("tag", tag), ("dtype", dtype), ("kind", kind)):
                get(key).add(is_zero, size_bits, unbinned, binned)
        if per_line_writer is not None:
            per_line_writer.writerow((offset, size_bits, binned, tag))
    return stats


def summary_rows(
    stats: dict[tuple[str, str], GroupStats], dump: Path, algo: str, cfg: bpc.BPCConfig
) -> list[dict]:
    order = {"all": 0, "kind": 1, "dtype": 2, "tag": 3}
    rows = []
    for (group_by, group), s in sorted(stats.items(), key=lambda kv: (order[kv[0][0]], kv[0][1])):
        orig = s.lines * cfg.line_bytes
        rows.append({
            "dump": dump.name,
            "algo": algo,
            "line_bytes": cfg.line_bytes,
            "word_bits": cfg.word_bits if algo == "bpc" else "",
            "try_no_transform": cfg.try_no_transform if algo == "bpc" else "",
            "bins": ",".join(map(str, cfg.bins)) or "none",
            "group_by": group_by,
            "group": group,
            "lines": s.lines,
            "zero_lines": s.zero_lines,
            "zero_line_pct": round(100 * s.zero_lines / s.lines, 3) if s.lines else 0.0,
            "orig_bytes": orig,
            "compressed_bits": s.compressed_bits,
            "unbinned_bytes": s.unbinned_bytes,
            "binned_bytes": s.binned_bytes,
            "ratio_unbinned": round(_ratio(orig, s.unbinned_bytes), 4),
            "ratio_binned": round(_ratio(orig, s.binned_bytes), 4),
            "bin_hist": ";".join(f"{b}:{n}" for b, n in sorted(s.bin_hist.items())),
        })  # fmt: skip
    return rows


def _print_table(rows: list[dict]) -> None:
    cols = ["group_by", "group", "lines", "zero_line_pct", "ratio_unbinned", "ratio_binned"]
    widths = {c: max(len(c), *(len(str(r[c])) for r in rows)) for c in cols}
    print("  ".join(c.ljust(widths[c]) for c in cols))
    for r in rows:
        print("  ".join(str(r[c]).ljust(widths[c]) for c in cols))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    dump = Path(args.dump)

    def fail(msg: str) -> int:
        print(f"compresso.cli: error: {msg}", file=sys.stderr)
        return 2

    if not dump.is_file():
        return fail(f"dump not found: {dump}")
    try:
        cfg = build_config(args)
    except ValueError as e:
        return fail(str(e))

    sidecar = None
    sc_path = Path(args.sidecar) if args.sidecar else sidecar_path(dump)
    if args.sidecar and not sc_path.is_file():
        return fail(f"sidecar not found: {sc_path}")
    if not args.no_sidecar and sc_path.is_file():
        try:
            sidecar = load_sidecar(sc_path, dump.stat().st_size)
        except (ValueError, OSError) as e:
            return fail(str(e))
        misaligned = [r.tag for r in sidecar.regions if r.offset % cfg.line_bytes]
        if misaligned:
            print(
                f"compresso.cli: warning: {len(misaligned)} region(s) not aligned to "
                f"{cfg.line_bytes} B lines (e.g. {misaligned[0]!r}); straddling lines "
                "count toward the region they start in",
                file=sys.stderr,
            )

    tail = tail_bytes(dump, cfg.line_bytes)
    if tail:
        print(f"compresso.cli: warning: ignoring {tail} trailing bytes (partial line)",
              file=sys.stderr)  # fmt: skip

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = f"{dump.stem}.{args.algo}"
    compress = make_compressor(args.algo, cfg)

    lines_path = out / f"{stem}.lines.csv"
    try:
        with ExitStack() as stack:
            writer = None
            if args.per_line:
                writer = csv.writer(stack.enter_context(open(lines_path, "w", newline="")))
                writer.writerow(("offset", "size_bits", "binned_bytes", "tag"))
            stats = run(dump, compress, cfg, sidecar, writer, args.limit_lines, args.chunk_lines)
    except NotImplementedError:
        lines_path.unlink(missing_ok=True)
        return fail(f"--algo {args.algo} is not implemented yet")
    if stats[("all", "all")].lines == 0:
        lines_path.unlink(missing_ok=True)
        return fail(f"no complete {cfg.line_bytes} B lines in {dump}")

    rows = summary_rows(stats, dump, args.algo, cfg)
    summary_path = out / f"{stem}.summary.csv"
    with open(summary_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SUMMARY_FIELDS)
        w.writeheader()
        w.writerows(rows)

    if not args.quiet:
        _print_table(rows)
        print(f"wrote {summary_path}" + (f" and {lines_path}" if args.per_line else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
