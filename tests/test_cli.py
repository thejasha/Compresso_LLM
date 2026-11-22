"""CLI + dump pipeline tests (issue #3)."""

import csv
import json
import os
import struct
from dataclasses import replace

import pytest

from compresso import bpc, cli, dump

LINE = 64


def _fp16_ramp(n_lines: int) -> bytes:
    """Smooth fp16-like data: small deltas between neighbouring 16-bit words."""
    return b"".join(struct.pack("<H", 0x3C00 + (i % 512)) for i in range(n_lines * LINE // 2))


@pytest.fixture
def synthetic(tmp_path):
    """A 4-region dump with a sidecar, plus 2 untagged lines at the end."""
    rng = bytes(os.urandom(8 * LINE))
    parts = [
        ("zeros", bytes(8 * LINE), "fp16", "kv"),
        ("ramp.weight", _fp16_ramp(8), "fp16", "weight"),
        ("noise.weight", rng, "int8", "weight"),
        ("const.act", b"\x11\x22" * (4 * LINE // 2), "bf16", "activation"),
    ]
    data, regions, off = b"", [], 0
    for tag, blob, dtype, kind in parts:
        regions.append(
            {"offset": off, "length": len(blob), "tag": tag, "dtype": dtype, "kind": kind}
        )
        data += blob
        off += len(blob)
    data += _fp16_ramp(2)  # untagged tail lines
    path = tmp_path / "synth.bin"
    path.write_bytes(data)
    (tmp_path / "synth.json").write_text(
        json.dumps({"source": "test", "model": "none", "regions": regions})
    )
    return path


def _read_summary(path):
    with open(path, newline="") as f:
        return {(r["group_by"], r["group"]): r for r in csv.DictReader(f)}


def _direct(data: bytes, cfg=bpc.COMPRESSO):
    """Totals computed by calling bpc.compress_line directly, no CLI involved."""
    bits = binned = unbinned = zeros = 0
    for i in range(0, len(data) - len(data) % cfg.line_bytes, cfg.line_bytes):
        line = data[i : i + cfg.line_bytes]
        _, b = bpc.compress_line(line, cfg)
        bits += b
        unbinned += min(-(-b // 8), cfg.line_bytes)
        binned += bpc.binned_bytes(line, b, cfg)
        zeros += not any(line)
    return bits, unbinned, binned, zeros


# ---------------------------------------------------------------------------
# End to end
# ---------------------------------------------------------------------------


def test_end_to_end_totals_match_direct_calls(synthetic, tmp_path):
    out = tmp_path / "out"
    assert cli.main([str(synthetic), "--out", str(out), "-q", "--chunk-lines", "3"]) == 0
    rows = _read_summary(out / "synth.bpc.summary.csv")

    bits, unbinned, binned, zeros = _direct(synthetic.read_bytes())
    all_ = rows[("all", "all")]
    assert int(all_["lines"]) == 30
    assert int(all_["compressed_bits"]) == bits
    assert int(all_["unbinned_bytes"]) == unbinned
    assert int(all_["binned_bytes"]) == binned
    assert int(all_["zero_lines"]) == zeros == 8
    assert float(all_["ratio_binned"]) == pytest.approx(30 * LINE / binned, rel=1e-3)


def test_groups_split_by_sidecar(synthetic, tmp_path):
    assert cli.main([str(synthetic), "--out", str(tmp_path), "-q"]) == 0
    rows = _read_summary(tmp_path / "synth.bpc.summary.csv")
    data = synthetic.read_bytes()

    assert int(rows[("tag", "zeros")]["lines"]) == 8
    assert int(rows[("tag", "zeros")]["binned_bytes"]) == 0  # zero lines -> 0 B bin
    assert int(rows[("tag", "untagged")]["lines"]) == 2
    assert int(rows[("kind", "weight")]["lines"]) == 16
    assert int(rows[("dtype", "fp16")]["lines"]) == 16

    # Each tag's totals match direct calls on that region's bytes.
    noise = data[16 * LINE : 24 * LINE]
    assert int(rows[("tag", "noise.weight")]["compressed_bits"]) == _direct(noise)[0]

    # Every grouping covers every line exactly once.
    for by in ("tag", "dtype", "kind"):
        assert sum(int(r["lines"]) for (g, _), r in rows.items() if g == by) == 30


def test_no_sidecar_gives_only_the_all_row(synthetic, tmp_path):
    assert cli.main([str(synthetic), "--out", str(tmp_path), "-q", "--no-sidecar"]) == 0
    rows = _read_summary(tmp_path / "synth.bpc.summary.csv")
    assert list(rows) == [("all", "all")]


def test_per_line_csv_matches_summary(synthetic, tmp_path):
    assert cli.main([str(synthetic), "--out", str(tmp_path), "-q", "--per-line"]) == 0
    with open(tmp_path / "synth.bpc.lines.csv", newline="") as f:
        lines = list(csv.DictReader(f))
    rows = _read_summary(tmp_path / "synth.bpc.summary.csv")
    assert len(lines) == 30
    assert [int(r["offset"]) for r in lines] == [i * LINE for i in range(30)]
    assert sum(int(r["size_bits"]) for r in lines) == int(rows[("all", "all")]["compressed_bits"])
    assert lines[0]["tag"] == "zeros" and lines[-1]["tag"] == "untagged"


def test_config_flags_reach_bpc(synthetic, tmp_path):
    args = ["--word-bits", "32", "--no-transform-path", "--bins", "0,16,32,64"]
    assert cli.main([str(synthetic), "--out", str(tmp_path), "-q", *args]) == 0
    row = _read_summary(tmp_path / "synth.bpc.summary.csv")[("all", "all")]
    cfg = replace(bpc.COMPRESSO, word_bits=32, try_no_transform=False, bins=(0, 16, 32, 64))
    bits, _, binned, _ = _direct(synthetic.read_bytes(), cfg)
    assert int(row["compressed_bits"]) == bits
    assert int(row["binned_bytes"]) == binned
    assert (row["word_bits"], row["try_no_transform"], row["bins"]) == (
        "32",
        "False",
        "0,16,32,64",
    )


def test_line_bytes_128(synthetic, tmp_path):
    args = ["--line-bytes", "128", "--bins", "0,16,64,128", "--no-sidecar"]
    assert cli.main([str(synthetic), "--out", str(tmp_path), "-q", *args]) == 0
    row = _read_summary(tmp_path / "synth.bpc.summary.csv")[("all", "all")]
    assert int(row["lines"]) == 15
    cfg = replace(bpc.COMPRESSO, line_bytes=128, bins=(0, 16, 64, 128))
    assert int(row["compressed_bits"]) == _direct(synthetic.read_bytes(), cfg)[0]


def test_limit_lines(synthetic, tmp_path):
    assert cli.main([str(synthetic), "--out", str(tmp_path), "-q", "--limit-lines", "5"]) == 0
    assert int(_read_summary(tmp_path / "synth.bpc.summary.csv")[("all", "all")]["lines"]) == 5


def test_trailing_partial_line_ignored(tmp_path, capsys):
    p = tmp_path / "odd.bin"
    p.write_bytes(bytes(3 * LINE + 10))
    assert cli.main([str(p), "--out", str(tmp_path), "-q"]) == 0
    assert "ignoring 10 trailing bytes" in capsys.readouterr().err
    assert int(_read_summary(tmp_path / "odd.bpc.summary.csv")[("all", "all")]["lines"]) == 3


@pytest.mark.parametrize("size", [0, LINE - 1])
@pytest.mark.parametrize("algo", ["bpc", "stub"])
def test_no_complete_lines_returns_2(tmp_path, size, algo):
    p = tmp_path / "short.bin"
    p.write_bytes(bytes(size))
    assert cli.main([str(p), "--out", str(tmp_path), "-q", "--algo", algo, "--per-line"]) == 2
    assert not (tmp_path / f"short.{algo}.summary.csv").exists()
    assert not (tmp_path / f"short.{algo}.lines.csv").exists()


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "args",
    [
        ["--line-bytes", "128"],  # needs explicit bins
        ["--bins", "0,8,32"],  # largest bin != line size
        ["--algo", "bdi"],  # not implemented yet (#9)
        ["--sidecar", "nope.json"],
    ],
)
def test_bad_input_returns_2(synthetic, tmp_path, args):
    assert cli.main([str(synthetic), "--out", str(tmp_path), "-q", *args]) == 2


@pytest.mark.parametrize(
    "args",
    [
        ["--line-bytes", "0", "--bins", "none"],
        ["--line-bytes", "-64", "--bins", "none"],
        ["--limit-lines", "0"],
        ["--limit-lines", "-1"],
        ["--chunk-lines", "0"],
    ],
)
def test_non_positive_sizes_rejected(synthetic, tmp_path, args):
    with pytest.raises(SystemExit) as e:
        cli.main([str(synthetic), "--out", str(tmp_path), "-q", *args])
    assert e.value.code == 2


def test_unimplemented_algo_leaves_no_lines_csv(synthetic, tmp_path):
    assert cli.main([str(synthetic), "--out", str(tmp_path), "--algo", "stub", "--per-line"]) == 2
    assert not (tmp_path / "synth.stub.lines.csv").exists()


# ---------------------------------------------------------------------------
# dump.py
# ---------------------------------------------------------------------------


def _write_sidecar(tmp_path, regions):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"regions": regions}))
    return p


@pytest.mark.parametrize(
    "regions, msg",
    [
        ([{"offset": 0, "length": 64}], "needs offset, length and tag"),
        ([{"offset": 0, "length": 0, "tag": "a"}], "bad offset/length"),
        ([{"offset": 0, "length": 64, "tag": "a", "kind": "weights"}], "kind must be"),
        (
            [{"offset": 0, "length": 128, "tag": "a"}, {"offset": 64, "length": 64, "tag": "b"}],
            "overlap",
        ),
        ([{"offset": 64, "length": 128, "tag": "a"}], "ends past the dump"),
    ],
)
def test_sidecar_validation(tmp_path, regions, msg):
    with pytest.raises(ValueError, match=msg):
        dump.load_sidecar(_write_sidecar(tmp_path, regions), dump_size=128)


def test_sidecar_lookup_and_extra_keys(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({
        "model": "m", "prompt": "hi",
        "regions": [{"offset": 128, "length": 64, "tag": "b"}, {"offset": 0, "length": 64, "tag": "a"}],
    }))  # fmt: skip
    sc = dump.load_sidecar(p)
    assert [r.tag for r in sc.regions] == ["a", "b"]  # sorted
    assert sc.region_at(0).tag == "a" and sc.region_at(63).tag == "a"
    assert sc.region_at(64) is None  # gap
    assert sc.region_at(191).tag == "b" and sc.region_at(192) is None
    assert sc.region_at(0).dtype == "unknown" and sc.region_at(0).kind == "other"
    assert sc.extra == {"prompt": "hi"}


def test_iter_lines_chunking_matches_plain_read(tmp_path):
    data = os.urandom(100 * LINE + 7)
    p = tmp_path / "r.bin"
    p.write_bytes(data)
    for chunk in (1, 3, 64, 1000):
        got = list(dump.iter_lines(p, LINE, chunk_lines=chunk))
        assert [o for o, _ in got] == [i * LINE for i in range(100)]
        assert b"".join(line for _, line in got) == data[: 100 * LINE]
    assert dump.tail_bytes(p) == 7
