# gem5 on either computer

These scripts are the hardware side of the project. They are the same on this laptop and on a CAE Linux machine. gem5 itself is not in git. `setup.sh` downloads and builds it on the machine you are sitting at.

Progress for reports: [`notes/hardware.md`](../notes/hardware.md).

## Commands

```bash
bash sim/setup.sh          # clone/build gem5 once
bash sim/run-hello.sh      # sanity check
bash sim/apply-writeback-hook.sh   # add DRAM write recorder into local gem5
bash sim/run-writebacks.sh # write-heavy program -> data/traces/write_array/
python3 sim/read_writebacks.py data/traces/write_array/writebacks.bin
```

`run-writebacks.sh` applies the hook, rebuilds gem5 if needed, runs `write_array`, and writes:

- `snapshot.bin` — memory when the first DRAM write happens
- `writebacks.bin` — 80 B records: tick, 64 B-aligned phys addr, 64 B data
- `trace.json` — config / workload metadata

Those files stay under `data/` and are gitignored.

## Pull and run

```bash
git clone https://github.com/thejasha/Compresso_LLM.git
cd Compresso_LLM
bash sim/setup.sh
bash sim/run-hello.sh
```

`setup.sh` needs git, python3, g++, and scons. If any are missing it prints the Ubuntu install command and stops. The build uses 2 jobs so it fits in the laptop's 7.6 GB of WSL memory. On a CAE machine with more memory:

```bash
GEM5_JOBS=4 bash sim/setup.sh
```

A finished hello run prints `Hello world` and writes `sim/runs/hello/stats.txt`. That folder is not committed.

## Useful overrides

| Variable | Default | Use |
|---|---|---|
| `GEM5_JOBS` | `2` | Compile jobs. Raise it on CAE if the machine has the memory. |
| `GEM5_ROOT` | `$HOME/gem5` | Where the gem5 source lives. This stays on the Linux disk, including under WSL, so the build is not on the Windows drive. |
| `GEM5_BRANCH` | `stable` | gem5 branch to clone. |

Use the same `GEM5_ROOT` for `setup.sh` and `run-hello.sh`.

## CAE

```bash
ssh <netid>@best-tux.cae.wisc.edu
git clone https://github.com/thejasha/Compresso_LLM.git
cd Compresso_LLM
bash sim/setup.sh
bash sim/run-hello.sh
```

Older ECE 752 setups loaded a local scons with `source /home/vhosts/ece752.ece.wisc.edu/.bashrc`. Try that if `scons` is not on the path. The long recordings belong on these machines. The hello run can stay on the laptop.
