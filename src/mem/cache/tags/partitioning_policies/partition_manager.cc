/*
 * Copyright (c) 2024 Arm Limited
 * All rights reserved
 *
 * The license below extends only to copyright in the software and shall
 * not be construed as granting a license to any other intellectual
 * property including but not limited to intellectual property relating
 * to a hardware implementation of the functionality of the software
 * licensed hereunder.  You may use the software subject to the license
 * terms below provided that you ensure that this notice is replicated
 * unmodified and in its entirety in all distributions of the software,
 * modified or unmodified, in source code or in binary form.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are
 * met: redistributions of source code must retain the above copyright
 * notice, this list of conditions and the following disclaimer;
 * redistributions in binary form must reproduce the above copyright
 * notice, this list of conditions and the following disclaimer in the
 * documentation and/or other materials provided with the distribution;
 * neither the name of the copyright holders nor the names of its
 * contributors may be used to endorse or promote products derived from
 * this software without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
 * "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
 * LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
 * A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
 * OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
 * SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
 * LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
 * DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
 * THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
 * (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
 * OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 */

#include "mem/cache/tags/partitioning_policies/partition_manager.hh"

#include "base/addr_range_list.hh"
#include "debug/PartitionManager.hh"
#include "mem/cache/tags/partitioning_policies/base_pp.hh"

namespace gem5
{

namespace partitioning_policy
{

PartitionManager::PartitionManager(const Params &p)
  : SimObject(p),
    cache(nullptr),
    partitioningPolicies(p.partitioning_policies)
{
    for (auto pp : partitioningPolicies) {
        pp->setPartitionManager(this);
    }
}

void
PartitionManager::init()
{
}

void
PartitionManager::notifyAcquire(uint64_t partition_id, ReplaceableEntry *entry)
{
    // Notify partitioning policies of acquisition of ownership
    for (auto & partitioning_policy : partitioningPolicies) {
        // get partitionId from Packet
        partitioning_policy->notifyAcquire(partition_id, entry);
    }
}

void
PartitionManager::notifyRelease(uint64_t partition_id, ReplaceableEntry *entry)
{
    // Notify partitioning policies of release of ownership
    for (auto partitioning_policy : partitioningPolicies) {
        partitioning_policy->notifyRelease(partition_id, entry);
    }
}

void
PartitionManager::filterByPartition(
    std::vector<ReplaceableEntry *> &entries,
    const uint64_t partition_id) const
{
    // Filter entries based on PartitionID
    for (auto partitioning_policy : partitioningPolicies) {
        partitioning_policy->filterByPartition(entries, partition_id);
    }
}

IntegrityPartitionManager::IntegrityPartitionManager(const Params &p)
  : PartitionManager(p)
{}

DataLocationPartitionManager::DataLocationPartitionManager(const Params &p)
  : PartitionManager(p),
    dramFullRanges(p.dram_full_ranges.begin(), p.dram_full_ranges.end()),
    dramOsRanges(p.dram_os_ranges.begin(), p.dram_os_ranges.end()),
    cxlFullRanges(p.cxl_full_ranges.begin(), p.cxl_full_ranges.end()),
    cxlOsRanges(p.cxl_os_ranges.begin(), p.cxl_os_ranges.end())
{
    // Compute integrity memory ranges.
    auto dramOsRangeIt = dramOsRanges.begin();
    for (auto dramFullRangeIt = dramFullRanges.begin();
        dramFullRangeIt != dramFullRanges.end();
        dramFullRangeIt++)
    {
        if (dramOsRangeIt->end() >= dramFullRangeIt->end()) {
            // The OS range ends at the end of this range or later.
            // The integrity range may start at the next range in the list.
            dramOsRangeIt++;
            continue;
        }

        // We can use (at least some of) this range for integrity.
        if (dramOsRangeIt == dramOsRanges.end()) {
            // The entire range can be used for integrity.
            dramIntegrityRanges.emplace_back(
                AddrRange(dramFullRangeIt->start(), dramFullRangeIt->end()));
        } else {
            // This range can be partially used for integrity.
            dramIntegrityRanges.emplace_back(
                AddrRange(dramOsRangeIt->end(), dramFullRangeIt->end()));
            dramOsRangeIt++;
        }
    }

    auto cxlOsRangeIt = cxlOsRanges.begin();
    for (auto cxlFullRangeIt = cxlFullRanges.begin();
        cxlFullRangeIt != cxlFullRanges.end();
        cxlFullRangeIt++)
    {
        if (cxlOsRangeIt->end() >= cxlFullRangeIt->end()) {
            // The OS range ends at the end of this range or later.
            // The integrity range may start at the next range in the list.
            cxlOsRangeIt++;
            continue;
        }

        // We can use (at least some of) this range for integrity.
        if (cxlOsRangeIt == cxlOsRanges.end()) {
            // The entire range can be used for integrity.
            cxlIntegrityRanges.emplace_back(
                AddrRange(cxlFullRangeIt->start(), cxlFullRangeIt->end()));
        } else {
            // This range can be partially used for integrity.
            cxlIntegrityRanges.emplace_back(
                AddrRange(cxlOsRangeIt->end(), cxlFullRangeIt->end()));
            cxlOsRangeIt++;
        }
    }
}

void
DataLocationPartitionManager::init() {
    PartitionManager::init();
}

uint64_t
DataLocationPartitionManager::readPacketPartitionID(PacketPtr pkt) const
{
    if (rangeListContains(dramOsRanges, pkt->getAddr())) {
        return PARTITION_ID_LOCAL_OS;
    } else if (rangeListContains(dramIntegrityRanges, pkt->getAddr())) {
        return PARTITION_ID_LOCAL_METADATA;
    } else if (rangeListContains(cxlOsRanges, pkt->getAddr())) {
        return PARTITION_ID_REMOTE_OS;
    } else if (rangeListContains(cxlIntegrityRanges, pkt->getAddr())) {
        return PARTITION_ID_REMOTE_METADATA;
    } else {
        return PARTITION_ID_OTHER;
    }
}

std::string
DataLocationPartitionManager::getPartitionName(uint64_t partition_id) const
{
    if (partition_id < PARTITION_COUNT) {
        return PARTITION_NAMES[partition_id];
    } else {
        return std::string("unnamed");
    }
}

} // namespace partitioning_policy

} // namespace gem5
