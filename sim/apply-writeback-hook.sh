#!/usr/bin/env bash
# Copy Compresso writeback helpers into a local gem5 tree and hook AbstractMemory.
# Safe to re-run. Rebuild gem5 after this (sim/setup.sh or scons).
set -euo pipefail

SIM_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK_DIR="$SIM_DIR/gem5-hook"
GEM5_ROOT="${GEM5_ROOT:-$HOME/gem5}"
ABS_CC="$GEM5_ROOT/src/mem/abstract_mem.cc"
SCONS="$GEM5_ROOT/src/mem/SConscript"

if [[ ! -f "$ABS_CC" ]]; then
  echo "gem5 not found at $GEM5_ROOT (missing src/mem/abstract_mem.cc)"
  echo "Run: bash sim/setup.sh"
  exit 1
fi

cp "$HOOK_DIR/compresso_wb_trace.hh" "$GEM5_ROOT/src/mem/compresso_wb_trace.hh"
cp "$HOOK_DIR/compresso_wb_trace.cc" "$GEM5_ROOT/src/mem/compresso_wb_trace.cc"

python3 - "$SCONS" <<'PY'
import pathlib, sys
path = pathlib.Path(sys.argv[1])
text = path.read_text()
needle = "Source('abstract_mem.cc')\n"
insert = needle + "Source('compresso_wb_trace.cc')\n"
if "Source('compresso_wb_trace.cc')" in text:
    print("SConscript: compresso_wb_trace.cc already listed")
elif needle not in text:
    raise SystemExit("could not find Source('abstract_mem.cc') in SConscript")
else:
    path.write_text(text.replace(needle, insert, 1))
    print("SConscript: added compresso_wb_trace.cc")
PY

python3 - "$ABS_CC" <<'PY'
import pathlib, sys
path = pathlib.Path(sys.argv[1])
text = path.read_text()
begin = "COMPRESSO_WB_TRACE_BEGIN"
end = "COMPRESSO_WB_TRACE_END"

# Refresh include block.
while f"// {begin}" in text and f"// {end}" in text:
    # Only strip include blocks that mention compresso_wb_trace.hh
    a = text.index(f"// {begin}")
    b = text.index(f"// {end}", a) + len(f"// {end}")
    block = text[a:b]
    if "compresso_wb_trace.hh" in block or "compressoMaybeDumpSnapshot" in block or "compressoLogWrite" in block:
        if b < len(text) and text[b] == "\n":
            b += 1
        text = text[:a] + text[b:]
    else:
        break

include_block = f'// {begin}\n#include "mem/compresso_wb_trace.hh"\n// {end}\n'
needle = '#include "mem/abstract_mem.hh"\n'
if needle not in text:
    raise SystemExit('missing #include "mem/abstract_mem.hh"')
if "compresso_wb_trace.hh" not in text:
    text = text.replace(needle, needle + include_block, 1)
    print("abstract_mem.cc: added include")
else:
    print("abstract_mem.cc: include present")

old_write = """    } else if (pkt->isWrite()) {
        if (writeOK(pkt)) {
            if (accessBackingMemory) {
                uint8_t *host_addr = toHostAddr(pkt->getAddr());
                pkt->writeData(host_addr);
                DPRINTF(MemoryAccess, "%s write due to %s\\n",
                        __func__, pkt->print());
            }
"""

new_write = f"""    }} else if (pkt->isWrite()) {{
        if (writeOK(pkt)) {{
            if (accessBackingMemory) {{
                // {begin}
                compressoMaybeDumpSnapshot(this);
                // {end}
                uint8_t *host_addr = toHostAddr(pkt->getAddr());
                pkt->writeData(host_addr);
                // {begin}
                compressoLogWrite(this, pkt);
                // {end}
                DPRINTF(MemoryAccess, "%s write due to %s\\n",
                        __func__, pkt->print());
            }}
"""

if "compressoLogWrite(this, pkt)" in text:
    print("abstract_mem.cc: write path already hooked")
elif old_write not in text:
    raise SystemExit("could not find AbstractMemory write path to hook")
else:
    text = text.replace(old_write, new_write, 1)
    print("abstract_mem.cc: hooked write path")

path.write_text(text)
print(f"Updated {path}")
PY

echo
echo "Hook installed in $GEM5_ROOT"
echo "Rebuild with: cd \"$GEM5_ROOT\" && export PATH=\"\$HOME/.local/bin:\$PATH\" && scons build/X86/gem5.opt -j\"\${GEM5_JOBS:-2}\""
