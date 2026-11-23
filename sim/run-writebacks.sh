#!/usr/bin/env bash
# Build the write_array workload, run it in gem5, write a Compresso trace.
set -euo pipefail

SIM_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SIM_DIR/.." && pwd)"
export PATH="$HOME/.local/bin:$PATH"
export GEM5_ROOT="${GEM5_ROOT:-$HOME/gem5}"
GEM5="$GEM5_ROOT/build/X86/gem5.opt"
TRACE_NAME="${TRACE_NAME:-write_array}"
OUT_DIR="${OUT_DIR:-$REPO_DIR/data/traces/$TRACE_NAME}"
GEM5_JOBS="${GEM5_JOBS:-2}"

if [[ ! -x "$GEM5" ]]; then
  echo "gem5 is not built at $GEM5"
  echo "Run: bash sim/setup.sh"
  exit 1
fi

echo "Applying writeback hook (idempotent)..."
bash "$SIM_DIR/apply-writeback-hook.sh"

# Rebuild so the hook is linked. Incremental if already applied once.
echo "Rebuilding gem5 (jobs=$GEM5_JOBS)..."
(
  cd "$GEM5_ROOT"
  scons build/X86/gem5.opt -j "$GEM5_JOBS"
)

echo "Compiling write_array for x86-64 (static)..."
mkdir -p "$SIM_DIR/workloads"
gcc -O2 -static -o "$SIM_DIR/workloads/write_array" "$SIM_DIR/workloads/write_array.c"

mkdir -p "$OUT_DIR"
rm -f "$OUT_DIR/snapshot.bin" "$OUT_DIR/writebacks.bin" "$OUT_DIR/trace.json"
export COMPRESSO_SNAPSHOT_FILE="$OUT_DIR/snapshot.bin"
export COMPRESSO_WB_FILE="$OUT_DIR/writebacks.bin"

RUN_DIR="$SIM_DIR/runs/$TRACE_NAME"
mkdir -p "$RUN_DIR"

echo "Running gem5 writeback capture -> $OUT_DIR"
"$GEM5" -d "$RUN_DIR" \
  "$SIM_DIR/configs/writeback_se.py" \
  "$SIM_DIR/workloads/write_array"

python3 - <<PY
import json, os, platform, pathlib
out = pathlib.Path(os.environ["COMPRESSO_SNAPSHOT_FILE"]).parent
wb = out / "writebacks.bin"
snap = out / "snapshot.bin"
meta = {
    "simulator": "gem5",
    "simulator_version": "26.0.0.0",
    "gem5_root": os.environ.get("GEM5_ROOT"),
    "host": platform.node(),
    "workload": "write_array",
    "workload_source": "sim/workloads/write_array.c",
    "config": "sim/configs/writeback_se.py",
    "cpu": "X86TimingSimpleCPU",
    "clock": "1GHz",
    "l1i": "16KiB",
    "l1d": "16KiB",
    "l2": "64KiB",
    "cache_line_bytes": 64,
    "mem": "DDR3_1600_8x8",
    "mem_range": "32MiB",
    "snapshot_file": "snapshot.bin",
    "writebacks_file": "writebacks.bin",
    "writeback_record_bytes": 80,
    "writeback_fields": ["u64 tick", "u64 phys_addr", "64 B data"],
    "note": "tick is gem5 curTick(), not a CPU cycle counter",
    "snapshot_bytes": snap.stat().st_size if snap.exists() else 0,
    "writeback_bytes": wb.stat().st_size if wb.exists() else 0,
    "writeback_records": (wb.stat().st_size // 80) if wb.exists() else 0,
}
(out / "trace.json").write_text(json.dumps(meta, indent=2) + "\n")
print(f"Wrote {out / 'trace.json'}")
print(f"snapshot_bytes={meta['snapshot_bytes']} writeback_records={meta['writeback_records']}")
PY

echo
python3 "$SIM_DIR/read_writebacks.py" "$OUT_DIR/writebacks.bin" || true
echo
echo "Trace directory: $OUT_DIR"
