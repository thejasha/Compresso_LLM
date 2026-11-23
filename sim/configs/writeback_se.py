"""SE-mode system with L1+L2 that runs a binary for writeback capture.

Requires the Compresso writeback hook in gem5 (sim/apply-writeback-hook.sh).
Set COMPRESSO_WB_FILE and COMPRESSO_SNAPSHOT_FILE before launching gem5.
"""

import os
import sys

import m5
from m5.objects import (
    AddrRange,
    DDR3_1600_8x8,
    L2XBar,
    MemCtrl,
    Process,
    Root,
    SEWorkload,
    SrcClockDomain,
    System,
    SystemXBar,
    VoltageDomain,
    X86TimingSimpleCPU,
)

GEM5_ROOT = os.environ.get("GEM5_ROOT", os.path.expanduser("~/gem5"))
m5.util.addToPath(os.path.join(GEM5_ROOT, "configs"))

# Local caches.py sits next to this script.
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

from caches import L1DCache, L1ICache, L2Cache  # noqa: E402
from common import SimpleOpts  # noqa: E402

this_dir = os.path.dirname(os.path.realpath(__file__))
default_binary = os.path.join(this_dir, "..", "workloads", "write_array")

SimpleOpts.add_option("binary", nargs="?", default=default_binary)
args = SimpleOpts.parse_args()

system = System()
system.clk_domain = SrcClockDomain()
system.clk_domain.clock = "1GHz"
system.clk_domain.voltage_domain = VoltageDomain()

system.mem_mode = "timing"
# Keep the physical map small so snapshot.bin stays a few MiB.
system.mem_ranges = [AddrRange("32MiB")]

system.cpu = X86TimingSimpleCPU()
system.cpu.icache = L1ICache(args)
system.cpu.dcache = L1DCache(args)
system.cpu.icache.connectCPU(system.cpu)
system.cpu.dcache.connectCPU(system.cpu)

system.l2bus = L2XBar()
system.cpu.icache.connectBus(system.l2bus)
system.cpu.dcache.connectBus(system.l2bus)

system.l2cache = L2Cache(args)
system.l2cache.connectCPUSideBus(system.l2bus)

system.membus = SystemXBar()
system.l2cache.connectMemSideBus(system.membus)

system.cpu.createInterruptController()
system.cpu.interrupts[0].pio = system.membus.mem_side_ports
system.cpu.interrupts[0].int_requestor = system.membus.cpu_side_ports
system.cpu.interrupts[0].int_responder = system.membus.mem_side_ports
system.system_port = system.membus.cpu_side_ports

system.mem_ctrl = MemCtrl()
system.mem_ctrl.dram = DDR3_1600_8x8()
system.mem_ctrl.dram.range = system.mem_ranges[0]
system.mem_ctrl.port = system.membus.mem_side_ports

system.workload = SEWorkload.init_compatible(args.binary)
process = Process()
process.cmd = [args.binary]
system.cpu.workload = process
system.cpu.createThreads()

root = Root(full_system=False, system=system)
m5.instantiate()

print("Beginning writeback simulation!")
exit_event = m5.simulate()
print(f"Exiting @ tick {m5.curTick()} because {exit_event.getCause()}")
