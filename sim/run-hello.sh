#!/usr/bin/env bash
# Run gem5's built-in hello-world. Proves the simulator builds and finishes.
set -euo pipefail

SIM_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PATH="$HOME/.local/bin:$PATH"
GEM5_ROOT="${GEM5_ROOT:-$HOME/gem5}"
GEM5="$GEM5_ROOT/build/X86/gem5.opt"
CONFIG="$GEM5_ROOT/configs/learning_gem5/part1/simple.py"
OUTDIR="$SIM_DIR/runs/hello"

if [[ ! -x "$GEM5" ]]; then
  echo "gem5 is not built at $GEM5"
  echo "Run: bash sim/setup.sh"
  exit 1
fi

if [[ ! -f "$CONFIG" ]]; then
  echo "Missing gem5 hello config: $CONFIG"
  echo "The gem5 checkout at $GEM5_ROOT does not look like the stable branch."
  exit 1
fi

mkdir -p "$OUTDIR"
echo "Running hello-world. Output goes to $OUTDIR"
"$GEM5" -d "$OUTDIR" "$CONFIG"
echo
echo "Hello run finished. Stats: $OUTDIR/stats.txt"
