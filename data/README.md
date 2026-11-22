# Dump format

This is the contract between the data producers (LLM dumps, #4; simulator
snapshots, #5) and the Compresso tools (`python -m compresso.cli`, the page
model and everything after it). If you produce dumps, follow this exactly; if
you need to change it, change this file first and tell the team.

Dumps are large and **never committed**: everything in `data/` except this
README is gitignored. Put them under `data/dumps/` (LLM) or `data/traces/`
(simulator).

## Files

Each dump is a pair with the same name:

| File | Required | Contents |
|---|---|---|
| `NAME.bin` | yes | Raw memory bytes, exactly as they sit in memory |
| `NAME.json` | no, but strongly recommended | Sidecar describing what is where in `NAME.bin` |

### `NAME.bin`

- Raw bytes, no header. Byte order is whatever the machine uses (x86 / ARM: little-endian).
- Read as consecutive **64-byte lines** (the default `--line-bytes`). Line *i* is bytes `[64*i, 64*i + 64)`.
- Size should be a multiple of 64. Trailing bytes that don't make a whole line are ignored (with a warning).
- Group 64 lines into a 4 KB page in the page model (#2), so a size that is a multiple of 4096 is best.

### `NAME.json` (sidecar)

```json
{
  "source": "collect_llm_dumps.py v0.1, torch 2.x, transformers 4.x",
  "model": "Qwen2.5-1.5B",
  "regions": [
    {"offset": 0,       "length": 6291456, "tag": "layers.0.attn.q_proj.weight", "dtype": "bf16", "kind": "weight"},
    {"offset": 6291456, "length": 262144,  "tag": "layers.0.attn.k_cache",       "dtype": "bf16", "kind": "kv"}
  ]
}
```

Top-level keys:

| Key | Type | Meaning |
|---|---|---|
| `source` | string | What produced the dump (script, versions, simulator) |
| `model` | string | Model name, or workload name for simulator dumps |
| `regions` | list | Byte ranges with known contents (see below). Can be empty. |

Any other top-level keys (prompt, dump point, sequence length, ...) are allowed and kept, so add whatever helps describe the run.

Each region:

| Key | Required | Type | Meaning |
|---|---|---|---|
| `offset` | yes | int | Start byte in `NAME.bin` |
| `length` | yes | int | Length in bytes, > 0 |
| `tag` | yes | string | Exact name, e.g. the tensor name (`layers.0.attn.k_cache`) |
| `dtype` | no (default `unknown`) | string | Element type. Use these spellings: `fp32`, `fp16`, `bf16`, `int8`, `uint8`, `int4`, `q4_k`, `q8_0`, `mixed`, `unknown` |
| `kind` | no (default `other`) | string | One of `weight`, `kv`, `activation`, `other` |

Rules:
- Regions must not overlap and must end inside the dump.
- Regions should start on a 64-byte boundary. If one doesn't, the tool warns, and a line that straddles two regions counts toward the region it starts in.
- Bytes not covered by any region are reported as group `untagged`.
- `dtype` and `kind` are what the parameter sweep (#8) splits results by, so get them right.

## Running the tool

```bash
make run DUMP=data/dumps/NAME.bin
```

```bash
make run DUMP=data/dumps/NAME.bin ARGS="--word-bits 32 --per-line"
```

Or directly: `python -m compresso.cli data/dumps/NAME.bin --help` for all flags. The sidecar `NAME.json` is picked up automatically.

Outputs go to `results/`:

| File | Contents |
|---|---|
| `NAME.ALGO.summary.csv` | One row for the whole dump (`group_by=all`), plus one per `kind`, `dtype` and `tag` when there is a sidecar |
| `NAME.ALGO.lines.csv` | With `--per-line` only: `offset, size_bits, binned_bytes, tag` for every line (large) |

Summary columns:

| Column | Meaning |
|---|---|
| `lines`, `zero_lines`, `zero_line_pct` | Line counts; all-zero lines |
| `orig_bytes` | `lines × line_bytes` |
| `compressed_bits` | Sum of the compressor's output sizes |
| `unbinned_bytes` | Sum of `ceil(bits / 8)`, capped at the line size (a line that grows is stored raw) |
| `binned_bytes` | Sum after rounding each line up to a size bin (`0/8/32/64` by default) |
| `ratio_unbinned`, `ratio_binned` | `orig_bytes` divided by the above |
| `bin_hist` | `bin:count` pairs, e.g. `0:120;8:40;32:7;64:3` |

Page-level ratios (512 B page packing plus metadata) come from the page model, #2.
