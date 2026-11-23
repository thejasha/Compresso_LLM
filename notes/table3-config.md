# gem5 config vs Compresso Table III

Source: Choukse, Erez, Alameldeen, *Compresso: Pragmatic Main Memory Compression*, MICRO 2018, Table III (PDF p. 8 / §VI).  
Our capture config: `sim/configs/writeback_se.py` and `data/traces/write_array/trace.json`.

## Side-by-side

| Parameter | Compresso Table III | Our first capture (`write_array`) | Match? |
|---|---|---|---|
| Simulator | zsim (extended) | gem5 26.0 SE mode | Different tool; same role (CPU + caches + DRAM) |
| Core | 3 GHz OOO, 4-wide, ROB 192 | 1 GHz `X86TimingSimpleCPU` (in-order timing) | No — simpler/slower CPU on purpose for a first trace |
| Cores | 1–4 | 1 | OK for single-thread capture |
| L1D | 64 KB | 16 KB | Smaller (forces more writebacks sooner) |
| L1I | (not highlighted in Tab. III summary) | 16 KB | — |
| L2 | 512 KB | 64 KB | Smaller |
| L3 / LLC | 2 MB (1-core) or 8 MB shared (4-core), 16-way | None (L2 is LLC) | No L3 yet |
| Cache line | **64 B** | **64 B** | Yes |
| DRAM | 8 GB DDR4-2666, BL=8, tCL/tRCD/tRP=18 | 32 MiB mapped, `DDR3_1600_8x8` model | Capacity and DRAM gen differ; timing not matched |
| Comp. line bins | 0 / 8 / 32 / 64 B | Not in gem5 (replay later) | N/A for capture |
| Comp. page sizes | Compresso 512 B chunks up to 4 KB | Not in gem5 | N/A for capture |
| Comp/decomp latency | 12 cycles modeled in zsim | Not modeled (depth 2 = offline replay) | Intentional |

## Why our first config is smaller

The first goal is a **correct writeback recording**, not a cycle-accurate match to Table III. Smaller caches and a timing-simple CPU:

- finish in seconds on the laptop
- produce DRAM writebacks from a tiny program (`write_array`)
- keep `snapshot.bin` at 32 MiB instead of multi-GB

The **64 B line size** is the parameter that must match Compresso, because that is the compression granularity and the writeback record size. That already matches.

## What to tighten later (after progress report / on CAE)

When we want traces closer to the paper’s traffic shape:

1. Raise L1D toward **64 KB**, L2 toward **512 KB**, add an **L3 ~2 MB** (or use gem5’s classic three-level setup).
2. Switch the CPU toward an OOO model if build time and run time allow (`O3CPU`), clock nearer **3 GHz**.
3. Use a larger `mem_ranges` and a DDR4-like model if gem5’s DRAM library has a close match; full 8 GB snapshots are optional (trace only the regions we care about).
4. Keep recording **LLC → DRAM** writes only; do not put BPC inside gem5 until depth 3.

None of those changes are required for the progress-report claim: we can already record writebacks and hand them to a Python replay.

## Report wording (short)

> We capture writebacks with gem5 in syscall-emulation mode. Cache lines are 64 B, matching Compresso. Our first runs use a smaller two-level cache and a timing-simple CPU than Table III so traces are cheap to produce; later runs can scale caches and memory toward Table III on CAE machines. Compression latency and page packing are applied offline in the Python model, not inside gem5.
