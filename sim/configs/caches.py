"""L1/L2 caches for the writeback SE config (from learning_gem5 part1)."""

from m5.objects import Cache

from common import SimpleOpts


class L1Cache(Cache):
    assoc = 2
    tag_latency = 2
    data_latency = 2
    response_latency = 2
    mshrs = 4
    tgts_per_mshr = 20

    def connectBus(self, bus):
        self.mem_side = bus.cpu_side_ports

    def connectCPU(self, cpu):
        raise NotImplementedError


class L1ICache(L1Cache):
    size = "16KiB"
    SimpleOpts.add_option("--l1i_size", help=f"L1I size. Default: {size}")

    def __init__(self, opts=None):
        super().__init__()
        if opts and getattr(opts, "l1i_size", None):
            self.size = opts.l1i_size

    def connectCPU(self, cpu):
        self.cpu_side = cpu.icache_port


class L1DCache(L1Cache):
    size = "16KiB"
    SimpleOpts.add_option("--l1d_size", help=f"L1D size. Default: {size}")

    def __init__(self, opts=None):
        super().__init__()
        if opts and getattr(opts, "l1d_size", None):
            self.size = opts.l1d_size

    def connectCPU(self, cpu):
        self.cpu_side = cpu.dcache_port


class L2Cache(Cache):
    size = "64KiB"
    assoc = 8
    tag_latency = 20
    data_latency = 20
    response_latency = 20
    mshrs = 20
    tgts_per_mshr = 12
    SimpleOpts.add_option("--l2_size", help=f"L2 size. Default: {size}")

    def __init__(self, opts=None):
        super().__init__()
        if opts and getattr(opts, "l2_size", None):
            self.size = opts.l2_size

    def connectCPUSideBus(self, bus):
        self.cpu_side = bus.mem_side_ports

    def connectMemSideBus(self, bus):
        self.mem_side = bus.cpu_side_ports
