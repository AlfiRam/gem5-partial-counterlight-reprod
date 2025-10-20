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

#include "mem/cache/tags/partitioning_policies/max_capacity_pp.hh"

#include <algorithm>
#include <string>

#include "base/logging.hh"
#include "base/trace.hh"
#include "debug/DynamicPartitionPolicy.hh"
#include "debug/DynamicPartitionPolicyComputeTargets.hh"
#include "mem/cache/tags/partitioning_policies/partition_manager.hh"
#include "params/MaxCapacityPartitioningPolicy.hh"

namespace gem5
{

namespace partitioning_policy
{

MaxCapacityPartitioningPolicy::MaxCapacityPartitioningPolicy
    (const MaxCapacityPartitioningPolicyParams &params):
    BasePartitioningPolicy(params),
    totalBlockCount(params.cache_size / params.blk_size),
    partitionIDs(params.partition_ids),
    capacities(params.capacities)
{
    // check if ids and capacities vectors are the same length
    if (this->partitionIDs.size() != this->capacities.size()) {
        fatal("MaxCapacity Partitioning Policy configuration invalid: ids and "
            "capacities arrays are not equal lengths");
    }

    // check allocations and create map
    for (auto i = 0; i < this->partitionIDs.size(); i++) {
        const uint64_t partition_id = this->partitionIDs[i];
        const double cap_frac = capacities[i];

        // Configure partition
        configurePartition(partition_id, cap_frac);
    }
}

void
MaxCapacityPartitioningPolicy::configurePartition(uint64_t partition_id,
                                                  double cap_frac)
{
    // check Capacity Fraction (cap_frac) is actually a fraction in [0,1]
    panic_if(!(cap_frac >= 0 && cap_frac <= 1),
             "MaxCapacity Partitioning Policy for PartitionID %d has "
             "Capacity Fraction %f outside of [0,1] range", partition_id,
             cap_frac);

    const uint64_t allocated_block_cnt = cap_frac * totalBlockCount;
    partitionIdMaxCapacity.emplace(partition_id, allocated_block_cnt);

    DPRINTF(PartitionPolicy, "Configured MaxCapacity Partitioning Policy "
        "for PartitionID: %d to use portion of size %f (%d cache blocks "
        "of %d total)\n", partition_id, cap_frac, allocated_block_cnt,
        totalBlockCount);
}

void
MaxCapacityPartitioningPolicy::filterByPartition(
    std::vector<ReplaceableEntry *> &entries,
    const uint64_t id) const
{
    if (// No entries to filter
        entries.empty() ||
        // This partition_id is not policed
        partitionIdMaxCapacity.find(id) == partitionIdMaxCapacity.end() ||
        // This partition_id has not yet used the cache
        partitionIdCurCapacity.find(id) == partitionIdCurCapacity.end() ||
        // The partition_id usage is below the maximum
        partitionIdCurCapacity.at(id) < partitionIdMaxCapacity.at(id))
        return;

    // Limit reached, restrict allocation only to blocks owned by
    // the Partition ID
    entries.erase(std::remove_if(entries.begin(), entries.end(),
        [id](ReplaceableEntry *entry) {
            CacheBlk *blk = static_cast<CacheBlk *>(entry);
            return blk->getPartitionId() != id;
        }), entries.end());
}

void
MaxCapacityPartitioningPolicy::notifyAcquire(
    const uint64_t partition_id,
    ReplaceableEntry *entry)
{
    // sanity check current allocation does not exceed its configured maximum
    assert(partitionIdCurCapacity[partition_id] <=
        partitionIdMaxCapacity[partition_id]);

    partitionIdCurCapacity[partition_id] += 1;
}

void
MaxCapacityPartitioningPolicy::notifyRelease(
    const uint64_t partition_id,
    ReplaceableEntry *entry)
{
    // sanity check current allocation will not cause underflow
    assert(partitionIdCurCapacity[partition_id] > 0);

    partitionIdCurCapacity[partition_id] -= 1;
}


DynamicCapacityPartitioningPolicy::DynamicCapacityPartitioningPolicy
    (const DynamicCapacityPartitioningPolicyParams &params) :
    MaxCapacityPartitioningPolicy(params),
    stats(this),
    endStats(this),
    assoc(params.assoc),
    updateRate(params.update_rate),
    partitionMargin(0.01 * totalBlockCount),
    partitionIdCurCapacitySets(params.cache_size / assoc / params.blk_size),
    partitionMinCapacity(partitionMargin),
    sumOfTargetCapacities(0),
    statRefreshScheduled(false)
{
    for (auto i = 0; i < this->partitionIDs.size(); i++) {
        // Start by splitting the target evenly per partition.
        const uint64_t partition_id = this->partitionIDs[i];

        const uint64_t allocated_block_cnt = (1.0f / partitionIDs.size()) *
                                                totalBlockCount;
        assert(allocated_block_cnt >= partitionMinCapacity);
        partitionIdCurCapacity.emplace(partition_id, 0);
        partitionIdTargetCapacity.emplace(partition_id, allocated_block_cnt);
        sumOfTargetCapacities += allocated_block_cnt;


        // Set initial differences
        highestDifference.push(partition_id, computeDifference(partition_id));
        lowestDifference.push(partition_id, computeDifference(partition_id));
    }

    DPRINTF(DynamicPartitionPolicy,
            "%s: Initial target capacities: %s\n",
            __func__, printTargetCapacities());
    DPRINTF(DynamicPartitionPolicy,
            "%s: Partition margin: %lu\n",
            __func__, partitionMargin);
    DPRINTF(DynamicPartitionPolicy,
            "%s: Number of sets computed: %lu\n",
            __func__, partitionIdCurCapacitySets.size());
    DPRINTF(DynamicPartitionPolicy,
            "%s: Highest difference: partition: %lu, difference: %ld\n",
            __func__, highestDifference.top().handle,
            highestDifference.top().value);
    DPRINTF(DynamicPartitionPolicy,
            "%s: Lowest difference: partition: %lu, difference: %ld\n",
            __func__, lowestDifference.top().handle,
            lowestDifference.top().value);
}

void
DynamicCapacityPartitioningPolicy::init()
{
    endStats.initFromParent();
}

void
DynamicCapacityPartitioningPolicy::processStatUpdate()
{
    DPRINTF(DynamicPartitionPolicy,
            "%s: Updating stats.\n",
            __func__);

    statRefreshScheduled = false;

    // Act based on stats
    stats.targetAdjustmentAttempts++;
    computeTargetCapacities();

    // Reset stats for the next interval
    for (size_t i = 0; i < cache->stats.partitionInterval.size(); i++) {
        cache->stats.partitionInterval[i]->resetStats();
    }

    // Schedule the next update
    assert(!statRefreshScheduled);

    schedule(
        new StatRefreshEvent(this),
        curTick() + updateRate
    );
    DPRINTF(DynamicPartitionPolicy,
            "%s: Next stat update has been scheduled for %lu.\n",
            __func__, curTick() + updateRate);
    statRefreshScheduled = true;
}


void
DynamicCapacityPartitioningPolicy::computeTargetCapacities()
{
    double highestMissRate;
    uint64_t highestMissRatePartition;
    double lowestMissRate;
    uint64_t lowestMissRatePartition;
    double fewestAccess;
    uint64_t fewestAccessPartition;
    double secondFewestAccess;
    uint64_t secondFewestAccessPartition;
    bool validFewestAccess;
    bool validSecondFewestAccess;

    HandledPriorityQueue<uint64_t, double,
        std::less<double>> highestMissRates;
    HandledPriorityQueue<uint64_t, double,
        std::greater<double>> lowestMissRates;
    HandledPriorityQueue<uint64_t, double,
        std::greater<double>> fewestAccesses;

    // Compute the highest and lowest miss rates.
    auto pi = cache->stats.partitionInterval;
    for (size_t i = 0; i < pm->getMaxExpectedPartitions(); i++) {
        double mr = pi[i]->missRate.total();
        double misses = pi[i]->misses.value();
        double hits = pi[i]->hits.value();
        DPRINTF(DynamicPartitionPolicyComputeTargets,
                "%s: Miss rate of partition %lu = %0.2lf\n",
                __func__, i, mr);
        // Consider NaN values like a perfect miss rate.
        // We aren't using those lines so that can be a candidate for reducing
        // target allocation.
        if (std::isnan(mr)) {
            mr = 0.0;
        }

        if (std::isnan(misses)) {
            misses = 0.0;
        }
        if (std::isnan(hits)) {
            hits = 0.0;
        }

        // Only consider a partition's miss rate if it has some access
        if (misses + hits > 100) {
            highestMissRates.push(i, mr);
            lowestMissRates.push(i, mr);
        }
        fewestAccesses.push(i, misses + hits);
    }

    if (highestMissRates.empty() || lowestMissRates.empty()) {
        return;
    }

    highestMissRate = highestMissRates.top().value;
    highestMissRatePartition = highestMissRates.top().handle;
    lowestMissRate = lowestMissRates.top().value;
    lowestMissRatePartition = lowestMissRates.top().handle;

    if (fewestAccesses.empty()) {
        validFewestAccess = false;
    } else {
        validFewestAccess = true;
        fewestAccess = fewestAccesses.top().value;
        fewestAccessPartition = fewestAccesses.top().handle;
        fewestAccesses.pop();
    }

    if (fewestAccesses.empty()) {
        validSecondFewestAccess = false;
    } else {
        validSecondFewestAccess = true;
        secondFewestAccess = fewestAccesses.top().value;
        secondFewestAccessPartition = fewestAccesses.top().handle;
    }

    // Add target capacity to the highest-missing partition and subtract from
    // the lowest-missing partition.
    DPRINTF(DynamicPartitionPolicyComputeTargets,
            "%s: sumOfTargetCapacities: %lu, totalBlockCount %lu\n",
            __func__, sumOfTargetCapacities, totalBlockCount);
    assert(pm);
    auto partitions = pm->getMaxExpectedPartitions();
    if (lowestMissRatePartition != highestMissRatePartition &&
        (highestMissRate - lowestMissRate) > 0.1 &&
        partitionIdTargetCapacity[highestMissRatePartition] <
            (totalBlockCount - (partitionMargin * partitions)) &&
        partitionIdTargetCapacity[lowestMissRatePartition] >
            (partitionMargin * 1))
    {
        DPRINTF(DynamicPartitionPolicyComputeTargets,
                "%s: Choosing to reduce allocation of partition %lu with "
                "miss rate %0.2lf in favor of partition %lu with "
                "miss rate %0.2lf\n",
                __func__, highestMissRatePartition,
                highestMissRate, lowestMissRatePartition,
                lowestMissRate);
        partitionIdTargetCapacity[highestMissRatePartition] += partitionMargin;
        sumOfTargetCapacities += partitionMargin;

        partitionIdTargetCapacity[lowestMissRatePartition] -= partitionMargin;
        sumOfTargetCapacities -= partitionMargin;

        stats.targetAdjustments++;

    } else if (validFewestAccess &&
               fewestAccess < 100 &&
               highestMissRatePartition != fewestAccessPartition &&
               partitionIdTargetCapacity[highestMissRatePartition] <
                    (totalBlockCount - (partitionMargin * partitions)) &&
               partitionIdTargetCapacity[fewestAccessPartition] >
                    (partitionMargin * 1))
    {
        // If we could instead choose the partition with fewest acccesses, try
        // this instead.

        DPRINTF(DynamicPartitionPolicyComputeTargets,
                "%s: Choosing to reduce allocation of partition %lu with "
                "miss rate %0.2lf in favor of partition %lu with %0.0lf "
                "accesses\n",
                __func__, highestMissRatePartition, highestMissRate,
                fewestAccessPartition, fewestAccess);

        partitionIdTargetCapacity[highestMissRatePartition] += partitionMargin;
        sumOfTargetCapacities += partitionMargin;

        partitionIdTargetCapacity[fewestAccessPartition] -= partitionMargin;
        sumOfTargetCapacities -= partitionMargin;

        stats.targetAdjustments++;
    } else if (validSecondFewestAccess &&
               secondFewestAccess < 100 &&
               highestMissRatePartition != secondFewestAccessPartition &&
               partitionIdTargetCapacity[highestMissRatePartition] <
                (totalBlockCount - (partitionMargin * partitions)) &&
               partitionIdTargetCapacity[secondFewestAccessPartition] >
                (partitionMargin * 1))
    {
        // If we could instead choose the partition with second fewest
        // acccesses, try this instead.

        DPRINTF(DynamicPartitionPolicyComputeTargets,
                "%s: Choosing to reduce allocation of partition %lu with "
                "miss rate %0.2lf in favor of partition %lu with %0.0lf "
                "(second fewest) accesses\n",
                __func__, highestMissRatePartition, highestMissRate,
                secondFewestAccessPartition, secondFewestAccess);

        partitionIdTargetCapacity[highestMissRatePartition]
                                                        += partitionMargin;
        sumOfTargetCapacities += partitionMargin;

        partitionIdTargetCapacity[secondFewestAccessPartition]
                                                        -= partitionMargin;
        sumOfTargetCapacities -= partitionMargin;

        stats.targetAdjustments++;
    }
    DPRINTF(DynamicPartitionPolicyComputeTargets,
            "%s: sumOfTargetCapacities: %lu, totalBlockCount %lu\n",
            __func__, sumOfTargetCapacities, totalBlockCount);
    assert(sumOfTargetCapacities <= totalBlockCount);

    DPRINTF(DynamicPartitionPolicyComputeTargets,
            "%s: Updated target capacities: %s\n",
            __func__, printTargetCapacities());

}


int64_t
DynamicCapacityPartitioningPolicy::computeDifference(const uint64_t id)
{
    assert(partitionIdTargetCapacity.find(id) !=
           partitionIdTargetCapacity.end());
    assert(partitionIdCurCapacity.find(id) != partitionIdCurCapacity.end());

    return partitionIdCurCapacity.at(id) - partitionIdTargetCapacity.at(id);
}


void
DynamicCapacityPartitioningPolicy::updateDifferences()
{
    // Update data for all partitions.
    assert(pm);
    for (size_t i = 0; i < pm->getMaxExpectedPartitions(); i++) {
        if (!highestDifference.contains(i)){
            continue;
        }
        highestDifference.modify(i, computeDifference(i));
        lowestDifference.modify(i, computeDifference(i));
    }
}


void
DynamicCapacityPartitioningPolicy::filterByPartition(
    std::vector<ReplaceableEntry *> &entries,
    const uint64_t id) const
{
    if (// No entries to filter
        entries.empty() ||
        // This partition_id is not policed
        partitionIdTargetCapacity.find(id) ==
            partitionIdTargetCapacity.end() ||
        // This partition_id has not yet used the cache
        partitionIdCurCapacity.find(id) == partitionIdCurCapacity.end() ||
        // The partition_id usage is within margin (+/- 2%)
        (partitionIdCurCapacity.at(id) >=
            partitionIdTargetCapacity.at(id) - (2 * partitionMargin) &&
        partitionIdCurCapacity.at(id) <=
            partitionIdTargetCapacity.at(id) + (2 * partitionMargin)))
        return;

    auto set = entries[0]->getSet();

    // This partition is having a new element added. What element is getting
    // potentially evicted depends on how far off the actual cache occupancy
    // is from the target occupancy.
    if (partitionIdCurCapacity.at(id) >= partitionIdTargetCapacity.at(id)) {
        // This partition has more than we want. Ideally, try to keep this
        // down.

        // Check how many blocks of this partition are in this set.
        auto searchInSet = partitionIdCurCapacitySets.at(set).find(id);
        auto numberInSet =
            (searchInSet == partitionIdCurCapacitySets.at(set).end())
                ? 0 : searchInSet->second;

        // There are no blocks of this partition in this set. In this case,
        // just pick something randomly.
        if (numberInSet == 0) {
            return;
        }

        // There are blocks, so let's only try to evict one from this
        // partition.
        entries.erase(std::remove_if(entries.begin(), entries.end(),
            [id](ReplaceableEntry *entry) {
                CacheBlk *blk = static_cast<CacheBlk *>(entry);
                return blk->getPartitionId() != id;
            }), entries.end());
    } else {
        // This partition has less blocks occupied than targeted. Ideally, try
        // to bring this number up. We will take away from the partition that
        // has the largest excess.

        auto highestDiff = highestDifference.top();
        if (highestDiff.value > 0) {
            auto bigId = highestDiff.handle;

            auto searchInSet = partitionIdCurCapacitySets.at(set).find(bigId);
            auto numberInSet =
                (searchInSet == partitionIdCurCapacitySets.at(set).end())
                    ? 0 : searchInSet->second;

            // The partition to take away from does not have much in this set.
            // In this case, just pick something.
            if (numberInSet == 0) {
                entries.erase(std::remove_if(entries.begin(), entries.end(),
                    [id](ReplaceableEntry *entry) {
                        CacheBlk *blk = static_cast<CacheBlk *>(entry);
                        return blk->getPartitionId() == id;
                    }), entries.end());
                return;
            }

            // Take away from the largest-difference partition.
            entries.erase(std::remove_if(entries.begin(), entries.end(),
                [bigId](ReplaceableEntry *entry) {
                    CacheBlk *blk = static_cast<CacheBlk *>(entry);
                    return blk->getPartitionId() != bigId;
                }), entries.end());
            return;
        }
    }
}

void
DynamicCapacityPartitioningPolicy::notifyAcquire(
    const uint64_t partition_id,
    ReplaceableEntry *entry)
{
    partitionIdCurCapacity[partition_id] += 1;

    // Mark that this partition has one more entry for this set.
    auto set = entry->getSet();
    assert(partitionIdCurCapacitySets[set][partition_id] < assoc);
    partitionIdCurCapacitySets[set][partition_id] += 1;

    // Update differences
    updateDifferences();

    DPRINTF(DynamicPartitionPolicy,
            "%s: Current target capacities: %s\n",
            __func__, printTargetCapacities());
    DPRINTF(DynamicPartitionPolicy,
            "%s: Highest difference: partition: %lu, difference: %ld\n",
            __func__, highestDifference.top().handle,
            highestDifference.top().value);
    DPRINTF(DynamicPartitionPolicy,
            "%s: Lowest difference: partition: %lu, difference: %ld\n",
            __func__, lowestDifference.top().handle,
            lowestDifference.top().value);

    if (!statRefreshScheduled) {
        schedule(
            new StatRefreshEvent(this),
            curTick() + updateRate
        );
        statRefreshScheduled = true;
    }
}

void
DynamicCapacityPartitioningPolicy::notifyRelease(
    const uint64_t partition_id,
    ReplaceableEntry *entry)
{
    // sanity check current allocation will not cause underflow
    assert(partitionIdCurCapacity[partition_id] > 0);

    partitionIdCurCapacity[partition_id] -= 1;

    // Mark that this partition has one less entry for this set.
    auto set = entry->getSet();
    assert(partitionIdCurCapacitySets[set][partition_id] > 0);
    partitionIdCurCapacitySets[set][partition_id] -= 1;

    // Update differences
    updateDifferences();

    DPRINTF(DynamicPartitionPolicy,
            "%s: Current target capacities: %s\n",
            __func__, printTargetCapacities());
    DPRINTF(DynamicPartitionPolicy,
            "%s: Highest difference: partition: %lu, difference: %ld\n",
            __func__, highestDifference.top().handle,
            highestDifference.top().value);
    DPRINTF(DynamicPartitionPolicy,
            "%s: Lowest difference: partition: %lu, difference: %ld\n",
            __func__, lowestDifference.top().handle,
            lowestDifference.top().value);
}

std::string
DynamicCapacityPartitioningPolicy::printTargetCapacities()
{
    std::ostringstream str;

    ccprintf(str, "\n[");
    for (auto it : partitionIdTargetCapacity) {
        ccprintf(str,
                 "\n\t(partition: %lu, target: %7lu (%0.2lf), "
                 "actual: %7lu (%0.2lf), difference: %7lu, accesses: %8.0lf, "
                 "miss rate: %0.3lf, cum. miss rate: %0.3lf), ",
                 it.first, it.second,
                 (it.second / (double) totalBlockCount),
                 partitionIdCurCapacity[it.first],
                 (partitionIdCurCapacity[it.first] /
                        (double) totalBlockCount),
                 computeDifference(it.first),
                 (cache) ? cache->stats.partitionInterval[it.first]
                                        ->accesses.total() : 0.0,
                 (cache) ? cache->stats.partitionInterval[it.first]
                                        ->missRate.total() : 9.0,
                 (cache) ? cache->stats.partition[it.first]
                                        ->missRate.total() : 9.0);
    }
    ccprintf(str, "\n]");

    return str.str();
}

DynamicCapacityPartitioningPolicy::PartitioningStats::PartitioningStats
    (DynamicCapacityPartitioningPolicy *parent)
    : statistics::Group(parent, "partitioning"), parent(parent),

    ADD_STAT(targetAdjustments, statistics::units::Count::get(),
             "Number of adjustments to target proportions"),
    ADD_STAT(targetAdjustmentAttempts, statistics::units::Count::get(),
             "Number of adjustments to target proportions attempted")
{
}


DynamicCapacityPartitioningPolicy::PartitioningEndStats::PartitioningEndStats
    (DynamicCapacityPartitioningPolicy *parent)
    : statistics::Group(parent, "partitioning_end"), parent(parent),

    ADD_STAT(actualBlocks, statistics::units::Count::get(),
             "actual blocks"),
    ADD_STAT(targetBlocks, statistics::units::Count::get(),
             "target blocks"),
    ADD_STAT(actualUsage, statistics::units::Tick::get(),
             "actual usage"),
    ADD_STAT(targetUsage, statistics::units::Tick::get(),
            "target usage")
{
}

void
DynamicCapacityPartitioningPolicy::PartitioningEndStats::initFromParent()
{
    // Pointers should not be null.
    assert(parent);
    assert(parent->pm);

    auto partitions = parent->pm->getMaxExpectedPartitions();
    actualBlocks
        .init(partitions)
        .precision(0);
    targetBlocks
        .init(partitions)
        .precision(0);
    actualUsage
        .init(partitions)
        .precision(3);
    targetUsage
        .init(partitions)
        .precision(3);

    for (int i = 0; i < partitions; i++) {
        actualBlocks.subname(i, parent->pm->getPartitionName(i));
        targetBlocks.subname(i, parent->pm->getPartitionName(i));
        actualUsage.subname(i, parent->pm->getPartitionName(i));
        targetUsage.subname(i, parent->pm->getPartitionName(i));
    }
}

void
DynamicCapacityPartitioningPolicy::PartitioningEndStats::preDumpStats()
{
    for (int i = 0; i < 4; i++) {
        actualBlocks[i] = parent->partitionIdCurCapacity.at(i);
        targetBlocks[i] = parent->partitionIdTargetCapacity.at(i);
        actualUsage[i] = parent->partitionIdCurCapacity.at(i) /
                            (double) parent->totalBlockCount;
        targetUsage[i] = parent->partitionIdTargetCapacity.at(i) /
                            (double) parent->totalBlockCount;
    }
}


} // namespace partitioning_policy

} // namespace gem5
