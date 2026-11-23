# Hardware track (gem5)

Progress log for the gem5 / writeback side of Compresso_LLM.
Use this for the progress report and final report. Keep `notes/local.md` for private notes; this file is committed.

**Owner:** Jack (simulator / hardware)  
**Branch:** `sim/gem5-hello`  
**Deadline:** December 15, 2026

## What this track contributes

Group mates can compress a **snapshot** of LLM memory and report compression ratio (capacity).
A snapshot has no updates, so it cannot show Compresso's other claim: when compressed data is rewritten and no longer fits, a plain design adds about **63%** more memory traffic, and Compresso's bookkeeping cuts that to about **15%**.

This track records each LLC writeback from gem5 (time, address, new 64 B). Replaying that recording through a control (naive compression) and through Compresso produces the **extra-traffic** comparison. That is the hardware result.

## Experiment shape

| | |
|---|---|
| **Do first** | Small write-heavy C program in gem5. Not LLM yet. No group-mate compressor required. |
| **Inputs** | Program binary, gem5 config, later: Compresso compress/overflow rules from the group |
| **gem5 outputs** | `snapshot.bin`, `writebacks.bin`, `trace.json` under `data/traces/NAME/` |
| **Replay outputs** | Overflow counts, extra memory trips (control vs Compresso), optional capacity over time |
| **Result shown** | On this workload's real updates, does Compresso cut extra memory traffic vs naive compression? |

LLM dumps stay with the LLM / capacity track. Full llama.cpp inside gem5 is usually too slow; use a small program now, and only later an LLM-like or short LLM-related run if time allows.

## Plan (depth 2)

**Before progress report (half we own alone)**

1. Writeback recorder: emit the three trace files from a small gem5 run
2. Tiny Python reader that parses `writebacks.bin`
3. Short note: gem5 config vs Compresso Table III
4. Optional: stub replay (fake compressed sizes) to test the pipeline

**After progress report / when group mates are ready**

5. Longer gem5 run
6. Replay control vs Compresso for real traffic numbers (needs their dynamic model)
7. LLM-related workload only if feasible
8. Depth 3/4 (compression inside gem5 / timing) only if time remains before Dec 15

## Done

- [x] Chose direction: depth 2 on gem5 (traces + later replay). Not full in-simulator Compresso first.
- [x] Agreed hardware contribution: writeback traces for the extra-traffic number.
- [x] Agreed first workloads are non-LLM; LLM data is not required for the first half.
- [x] Agreed progress report waits until the first writeback recording exists.
- [x] `sim/setup.sh`, `sim/run-hello.sh`, `sim/README.md` — same commands on laptop WSL or CAE.
- [x] gem5 ignored by git (`sim/gem5/`, `sim/runs/`); default build at `$HOME/gem5`.
- [x] Built gem5 stable **26.0.0.0** on the laptop (`~/gem5`).
- [x] Hello-world ran successfully (Nov 21, 2026): printed `Hello world!`; stats in `sim/runs/hello/` (local only).
- [x] Branch `sim/gem5-hello` published; top-level `README.md` left unchanged.

## Todo

### Before progress report

- [ ] Small write-heavy test program for gem5 (SE mode)
- [ ] Record LLC writebacks → `data/traces/NAME/{snapshot.bin,writebacks.bin,trace.json}`
- [ ] Python reader for `writebacks.bin` (document the 80 B record layout)
- [ ] Document gem5 config vs Compresso Table III
- [ ] Optional stub replay to prove the file pipeline end-to-end

### After progress report

- [ ] Longer / more realistic gem5 run (CAE as needed)
- [ ] Control vs Compresso traffic replay using group mates' compressor
- [ ] LLM-related recording if feasible
- [ ] Depth 3/4 only if Dec 15 still has slack

## Trace format (agreed with the group)

Directory: `data/traces/NAME/`

| File | Contents |
|---|---|
| `snapshot.bin` | Raw memory at trace start (64 B lines), same idea as LLM dumps |
| `writebacks.bin` | Little-endian records: `u64 cycle`, `u64 phys_addr` (64 B aligned), `64 B data` (80 B each) |
| `trace.json` | Simulator, version, config, workload, instruction count, optional address tags |

## Machines

| Machine | Role |
|---|---|
| Laptop WSL | Build gem5 (`GEM5_JOBS=2`), hello-world, first small traces |
| CAE (`best-tux.cae.wisc.edu`) | Faster rebuild (`GEM5_JOBS=4` if memory allows), longer runs |

```bash
bash sim/setup.sh
bash sim/run-hello.sh
```

## Report bullets (keep current)

**Progress report (target once first recording exists)**

- Hardware goal: writeback traces for Compresso traffic, not only capacity
- gem5 builds and hello-world works on the laptop
- Scripts in `sim/` for laptop and CAE
- Next / in progress: first writeback trace from a small program

**Final report (fill as results appear)**

- Method: one gem5 recording, two replays (naive vs Compresso)
- Workloads used (small program first; any LLM-related later)
- Extra-traffic and capacity numbers vs control
- Limits: what we did not put inside gem5; what waited on the Python model

## Log

| Date | Note |
|---|---|
| 2026-11-21 | Direction, `sim/` scripts, gem5 build, hello-world OK, branch `sim/gem5-hello` |
| 2026-11-22 | Clarified control vs Compresso; first half without LLM / without group compressor; this note created |
