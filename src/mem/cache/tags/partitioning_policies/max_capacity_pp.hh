/*
 * Copyright (c) 2024 ARM Limited
 * All rights reserved.
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

#ifndef __MEM_CACHE_TAGS_PARTITIONING_POLICIES_MAX_CAPACITY_HH__
#define __MEM_CACHE_TAGS_PARTITIONING_POLICIES_MAX_CAPACITY_HH__

#include <unordered_map>
#include <vector>

#include "base/priority_queue_handled.hh"
#include "debug/PartitionPolicy.hh"
#include "mem/cache/base.hh"
#include "mem/cache/cache_blk.hh"
#include "mem/cache/tags/partitioning_policies/base_pp.hh"
#include "params/BasePartitioningPolicy.hh"
#include "params/DynamicCapacityPartitioningPolicy.hh"
#include "params/MaxCapacityPartitioningPolicy.hh"

namespace gem5
{

namespace partitioning_policy
{

/**
 * A MaxCapacityPartitioningPolicy filters the cache blocks available to a
 * memory requestor (identified via PartitionID) based on count of already
 * allocated blocks. The number of cache blocks a specific memory requestor
 * can have access to is determined by its provided capacities allocation in
 * the [0, 1] range. This policy has no effect on requests with unregistered
 * PartitionIDs.
 *
 * @see BasePartitioningPolicy
 */
class MaxCapacityPartitioningPolicy : public BasePartitioningPolicy
{
  public:
    MaxCapacityPartitioningPolicy
    (const MaxCapacityPartitioningPolicyParams &params);

    void
    filterByPartition(std::vector<ReplaceableEntry *> &entries,
                      const uint64_t partition_id) const override;

    void
    notifyAcquire(const uint64_t partition_id,
                  ReplaceableEntry *entry) override;

    void
    notifyRelease(const uint64_t partition_id,
                  ReplaceableEntry *entry) override;

    /**
    * Set the maximum capacity (as a fraction) for the provided partition
    *
    * param partion_id partition to be configured
    * param cap_frac max capacity for the partition (0 < cap_frac < 1)
    */
    void configurePartition(uint64_t partition_id, double cap_frac);

  protected:
    /**
    * Total number of cache blocks
    */
    const uint64_t totalBlockCount;

    /**
    * Vector of partitionIDs the policy operates on
    */
    const std::vector< uint64_t > partitionIDs;

    /**
    * Vector of capacity fractions to enforce on the policied partitionIDs
    */
    const std::vector< double > capacities;

    /**
    * Map of PartitionIDs and maximum allocatable cache block counts;
    * On evictions full partitions are prioritized.
    */
    std::unordered_map< uint64_t, uint64_t > partitionIdMaxCapacity;

    /**
    * Map of PartitionIDs and currently allocated blck coutns
    */
    std::unordered_map< uint64_t, uint64_t > partitionIdCurCapacity;
};


class DynamicCapacityPartitioningPolicy : public MaxCapacityPartitioningPolicy
{
  public:
    DynamicCapacityPartitioningPolicy
    (const DynamicCapacityPartitioningPolicyParams &params);

    void init() override;

    /**
     * Adjust partition target capacities based on factors such as miss rate
     * or access frequency.
     */
    void computeTargetCapacities();

    /**
     * Compute the difference between a partition's target capacity and its
     * actual capacity.
     *
     * Positive implies there is more actually allocated than targeted.
     * Negative implies there is less actually allocated than targeted.
     */
    int64_t computeDifference(const uint64_t partition_id);

    /**
     * Update computed differences between a partition's target capacity and
     * actual cache occupancy.
     */
    void updateDifferences();

    void
    filterByPartition(std::vector<ReplaceableEntry *> &entries,
                      const uint64_t partition_id) const override;

    void
    notifyAcquire(const uint64_t partition_id,
                  ReplaceableEntry *entry) override;

    void
    notifyRelease(const uint64_t partition_id,
                  ReplaceableEntry *entry) override;

    struct PartitioningStats : public statistics::Group
    {
        PartitioningStats(DynamicCapacityPartitioningPolicy *parent);

        std::string name() const {
          return parent->name() + ".stats";
        }

        DynamicCapacityPartitioningPolicy *parent;

        // Number of changes to the target proportions
        statistics::Scalar targetAdjustments;
        statistics::Scalar targetAdjustmentAttempts;

    };

    PartitioningStats stats;

    /**
     * Statistics specifically for the end of simulation or right before
     * dumping stats.
     *
     * This gives the resulting partitioning as determined by the dynamic
     * cache partitioning scheme.
     */
    struct PartitioningEndStats : public statistics::Group
    {
        PartitioningEndStats(DynamicCapacityPartitioningPolicy *parent);

        /**
         * Due stats not being a SimObject, an init() call must be done from
         * the parent SimObject.
         */
        void initFromParent();

        std::string name() const {
          return parent->name() + ".stats";
        }

        void preDumpStats() override;

        DynamicCapacityPartitioningPolicy *parent;

        // In number of blocks
        statistics::Vector actualBlocks;
        statistics::Vector targetBlocks;

        // Between [0, 1]
        statistics::Vector actualUsage;
        statistics::Vector targetUsage;
    };

    PartitioningEndStats endStats;

  private:
    /**
     * Associativity of cache. Used for sanity checking valid states.
     */
    unsigned int assoc;

    /**
     * Rate in ticks to update the target capacity levels.
     */
    Tick updateRate;

    /**
     * The number of cache blocks that should be changed (marginally) when
     * adjusting partition sizes.
     */
    const uint64_t partitionMargin;

    /**
    * Map of PartitionIDs and currently allocated block counts, per set.
    *
    * Used for sanity checking valid states.
    */
    std::vector<
      std::unordered_map<uint64_t, uint64_t>> partitionIdCurCapacitySets;

    /**
     * Minimum allocatable block count for every partition.
     */
    const uint64_t partitionMinCapacity;

    /**
    * Map of PartitionIDs and target allocatable cache block counts;
    * On evictions full partitions are prioritized.
    */
    std::unordered_map< uint64_t, uint64_t > partitionIdTargetCapacity;

    /**
     * Total number of blocks in the target partition scheme.
     *
     * Used for sanity checking valid states.
     */
    uint64_t sumOfTargetCapacities;

    /**
     * Max heap of partitions in terms of the difference between their target
     * capacity and the actual occupancy of the partition.
     *
     * The top of the heap is the partition with the most excess blocks
     * compared to the targeted amount.
     */
    HandledPriorityQueue<
      uint64_t, int64_t, std::less<int64_t>> highestDifference;
    /**
     * Min heap of partitions in terms of the difference between their target
     * capacity and the actual occupancy of the partition.
     *
     * The top of the heap is the partition with the most missing blocks
     * compared to the targeted amount.
     */
    HandledPriorityQueue<
      uint64_t,int64_t, std::greater<int64_t>> lowestDifference;

    /**
     * Process the changes that have been made to statistics by updating cache
     * partitioning if needed. Stats are then reset until the next update
     * interval arrives.
     */
    void processStatUpdate();

    /**
     * A refresh after the next statistics interval has been scheduled.
     */
    bool statRefreshScheduled;

    class StatRefreshEvent : public Event
    {
      private:
        // Pointer to the related partitioning policy object.
        DynamicCapacityPartitioningPolicy *pp;

      public:
        StatRefreshEvent(
          DynamicCapacityPartitioningPolicy *pp
        ) : Event(Default_Pri, AutoDelete),
          pp(pp)
        { }

        void process() override {
          pp->processStatUpdate();
        }
    };

    /// DEBUG

    std::string printTargetCapacities();
};

} // namespace partitioning_policy

} // namespace gem5

#endif // __MEM_CACHE_TAGS_PARTITIONING_POLICIES_MAX_CAPACITY_HH__
