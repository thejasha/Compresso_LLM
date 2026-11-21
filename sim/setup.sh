#!/usr/bin/env bash
# Clone and build gem5 on this machine. Safe to re-run.
# Laptop (WSL, 7.6 GB): GEM5_JOBS=2 bash sim/setup.sh
# CAE, if it has more memory: GEM5_JOBS=4 bash sim/setup.sh
set -euo pipefail

SIM_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GEM5_ROOT="${GEM5_ROOT:-$SIM_DIR/gem5}"
GEM5_JOBS="${GEM5_JOBS:-2}"
GEM5_BRANCH="${GEM5_BRANCH:-stable}"

missing=()
for cmd in git python3 g++ scons; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    missing+=("$cmd")
  fi
done

if ((${#missing[@]} > 0)); then
  echo "Missing commands: ${missing[*]}"
  echo
  echo "On Ubuntu, install gem5's build tools with:"
  echo "  sudo apt update"
  echo "  sudo apt install -y build-essential git m4 scons zlib1g-dev \\"
  echo "    libprotobuf-dev protobuf-compiler libgoogle-perftools-dev \\"
  echo "    python3-dev python-is-python3 libboost-all-dev pkg-config"
  echo
  echo "On a CAE machine, scons may already be available after:"
  echo "  source /home/vhosts/ece752.ece.wisc.edu/.bashrc"
  echo "If that file is gone, ask CAE help or install the packages above."
  exit 1
fi

if [[ ! -d "$GEM5_ROOT/.git" ]]; then
  echo "Cloning gem5 ($GEM5_BRANCH) into $GEM5_ROOT"
  git clone --depth 1 --branch "$GEM5_BRANCH" https://github.com/gem5/gem5.git "$GEM5_ROOT"
else
  echo "gem5 already present at $GEM5_ROOT"
fi

echo "Building X86 gem5 with $GEM5_JOBS jobs. This often takes about an hour."
cd "$GEM5_ROOT"
scons "build/X86/gem5.opt" -j "$GEM5_JOBS"

echo
echo "Build finished: $GEM5_ROOT/build/X86/gem5.opt"
echo "Next: bash sim/run-hello.sh"
