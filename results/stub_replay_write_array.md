# Stub replay: `write_array`

Fake compressor only (not real BPC). Proves the trace can drive a
control vs Compresso-style comparison.

- writebacks file: `data/traces/write_array/writebacks.bin`
- records: **152**
- unique lines: **152**
- same-line rewrites: **0**

| Mode | Extra trips (overflows) | Lines touched |
|---|---:|---:|
| Control (naive) | 0 | 152 |
| Compresso stub | 0 | 152 |

This trace has **no same-line rewrites**, so overflows stay 0 in both
modes. That still validates the file pipeline. A later workload that
rewrites the same addresses (or a longer run of `write_array`) is what
makes control vs Compresso diverge.

Replace `fake_size` with the real compressor when the group model is ready.
