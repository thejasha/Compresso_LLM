/*
 * Record DRAM writes for Compresso_LLM.
 *
 * Env:
 *   COMPRESSO_SNAPSHOT_FILE  path for snapshot.bin (raw bytes)
 *   COMPRESSO_WB_FILE        path for writebacks.bin (80 B records)
 *
 * Record layout (little-endian): u64 tick, u64 phys_addr (64 B aligned), 64 B data.
 */

#include "mem/compresso_wb_trace.hh"

#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <mutex>

#include "base/intmath.hh"
#include "base/logging.hh"
#include "mem/abstract_mem.hh"
#include "sim/cur_tick.hh"

namespace gem5
{
namespace memory
{
namespace
{

constexpr std::size_t kLineBytes = 64;
constexpr std::size_t kRecordBytes = 8 + 8 + kLineBytes;

std::mutex g_mu;
bool g_snapshot_done = false;

const char *
snapshotPath()
{
    return std::getenv("COMPRESSO_SNAPSHOT_FILE");
}

const char *
writebackPath()
{
    return std::getenv("COMPRESSO_WB_FILE");
}

} // namespace

void
compressoMaybeDumpSnapshot(AbstractMemory *mem)
{
    const char *path = snapshotPath();
    if (!path || g_snapshot_done) {
        return;
    }

    std::lock_guard<std::mutex> lock(g_mu);
    if (g_snapshot_done) {
        return;
    }

    const Addr start = mem->getAddrRange().start();
    const Addr size = mem->size();
    uint8_t *host = mem->toHostAddr(start);

    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    if (!out) {
        warn("Compresso: could not open snapshot file %s\n", path);
        g_snapshot_done = true;
        return;
    }
    out.write(reinterpret_cast<const char *>(host),
              static_cast<std::streamsize>(size));
    out.close();
    inform("Compresso: wrote snapshot (%llu bytes) to %s\n",
           (unsigned long long)size, path);
    g_snapshot_done = true;
}

void
compressoLogWrite(AbstractMemory *mem, PacketPtr pkt)
{
    const char *path = writebackPath();
    if (!path || !pkt || !pkt->isWrite()) {
        return;
    }

    const Addr pkt_start = pkt->getAddr();
    const unsigned pkt_size = pkt->getSize();
    if (pkt_size == 0) {
        return;
    }

    const Addr line_start = roundDown(pkt_start, kLineBytes);
    const Addr pkt_end = pkt_start + pkt_size;
    const Addr line_end = roundUp(pkt_end, kLineBytes);

    std::lock_guard<std::mutex> lock(g_mu);
    std::ofstream out(path, std::ios::binary | std::ios::app);
    if (!out) {
        warn("Compresso: could not open writeback file %s\n", path);
        return;
    }

    const uint64_t tick = static_cast<uint64_t>(curTick());
    uint8_t record[kRecordBytes];

    for (Addr addr = line_start; addr < line_end; addr += kLineBytes) {
        uint8_t *host = mem->toHostAddr(addr);
        std::memcpy(record, &tick, 8);
        const uint64_t phys = static_cast<uint64_t>(addr);
        std::memcpy(record + 8, &phys, 8);
        std::memcpy(record + 16, host, kLineBytes);
        out.write(reinterpret_cast<const char *>(record),
                  static_cast<std::streamsize>(kRecordBytes));
    }
}

} // namespace memory
} // namespace gem5
