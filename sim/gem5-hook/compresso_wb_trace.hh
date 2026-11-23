/*
 * Compresso writeback / snapshot helpers for AbstractMemory.
 * Applied into a local gem5 tree by sim/apply-writeback-hook.sh.
 */
#ifndef __MEM_COMPRESSO_WB_TRACE_HH__
#define __MEM_COMPRESSO_WB_TRACE_HH__

#include "mem/packet.hh"

namespace gem5
{
namespace memory
{

class AbstractMemory;

/** Dump the DRAM backing store once (memory at trace start). */
void compressoMaybeDumpSnapshot(AbstractMemory *mem);

/** After a write lands in backing store, append 64 B line records. */
void compressoLogWrite(AbstractMemory *mem, PacketPtr pkt);

} // namespace memory
} // namespace gem5

#endif // __MEM_COMPRESSO_WB_TRACE_HH__
