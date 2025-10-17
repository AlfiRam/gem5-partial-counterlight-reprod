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

#ifndef __MEM_CACHE_TAGS_PARTITIONING_MANAGER_HH__
#define __MEM_CACHE_TAGS_PARTITIONING_MANAGER_HH__

#include "mem/mtree/abstract_tree.hh"
#include "mem/packet.hh"
#include "params/DataLocationPartitionManager.hh"
#include "params/IntegrityPartitionManager.hh"
#include "params/PartitionManager.hh"
#include "sim/sim_object.hh"

namespace gem5
{

class ReplaceableEntry;

namespace partitioning_policy
{

class BasePartitioningPolicy;

class PartitionManager : public SimObject
{
  public:
    PARAMS(PartitionManager);
    PartitionManager(const Params &p);

    /**
    * PartitionManager interface to retrieve PartitionID from a packet;
    * This base implementation returns zero by default.
    *
    * @param pkt pointer to packet (PacketPtr)
    * @return packet PartitionID.
    */
    virtual uint64_t
    readPacketPartitionID(PacketPtr pkt) const
    {
        return 0;
    };

    virtual std::string
    getPartitionName(uint64_t partition_id) const
    {
        return std::string("unnamed");
    }

    /**
     * Return the maximum number of partitions expected, given this partition
     * manager.
     */
    virtual uint64_t
    getMaxExpectedPartitions() const
    {
        return 1;
    }

    /**
    * Notify of acquisition of ownership of a cache line
    * @param partition_id PartitionID of the upstream memory request
    * @param entry The cache line associated with the new ownership
    */
    void notifyAcquire(uint64_t partition_id, ReplaceableEntry *entry);

    void notifyRelease(uint64_t partition_id, ReplaceableEntry *entry);

    void filterByPartition(std::vector<ReplaceableEntry *> &entries,
        const uint64_t partition_id) const;

  protected:
    /** Partitioning policies */
    std::vector<partitioning_policy::BasePartitioningPolicy *>
        partitioningPolicies;
};


/**
 * Partition IDs based on type of metadata (counter, MAC, etc.).
 */
class IntegrityPartitionManager : public PartitionManager
{
  public:
    PARAMS(IntegrityPartitionManager);
    IntegrityPartitionManager(const Params &p);

    uint64_t readPacketPartitionID(PacketPtr pkt) const override
    {
      assert(pkt->isMetadataRequest());

      return pkt->getMetadataType();
    }

    uint64_t
    getMaxExpectedPartitions() const override
    {
      return AbstractIntegrityTree::TREE_NODE_TYPE_COUNT;
    }
};


/**
 * Partition IDs based on provided address ranges.
 */
class DataLocationPartitionManager : public PartitionManager
{
  public:
    PARAMS(DataLocationPartitionManager);
    DataLocationPartitionManager(const Params &p);

    void init() override;

    AddrRangeList dramFullRanges;
    AddrRangeList dramOsRanges;
    AddrRangeList dramIntegrityRanges;
    AddrRangeList cxlFullRanges;
    AddrRangeList cxlOsRanges;
    AddrRangeList cxlIntegrityRanges;

    static const uint16_t PARTITION_COUNT = 5;

    const std::string PARTITION_NAMES[PARTITION_COUNT] = {
      "LocalOs",
      "LocalMetadata",
      "RemoteOs",
      "RemoteMetadata",
      "Other",
    };

    static const uint16_t PARTITION_ID_LOCAL_OS = 0;
    static const uint16_t PARTITION_ID_LOCAL_METADATA = 1;
    static const uint16_t PARTITION_ID_REMOTE_OS = 2;
    static const uint16_t PARTITION_ID_REMOTE_METADATA = 3;
    static const uint16_t PARTITION_ID_OTHER = 4;

    uint64_t readPacketPartitionID(PacketPtr pkt) const override;

    std::string getPartitionName(uint64_t partition_id) const override;

    uint64_t
    getMaxExpectedPartitions() const override
    {
      return PARTITION_COUNT;
    }
};

} // namespace partitioning_policy

} // namespace gem5

#endif // __MEM_CACHE_TAGS_PARTITIONING_MANAGER_HH__
