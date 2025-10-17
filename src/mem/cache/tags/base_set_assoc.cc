/*
 * Copyright (c) 2012-2014, 2023-2024 ARM Limited
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
 * Copyright (c) 2003-2005,2014 The Regents of The University of Michigan
 * All rights reserved.
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

/**
 * @file
 * Definitions of a conventional tag store.
 */

#include "mem/cache/tags/base_set_assoc.hh"

#include <string>

#include "base/cprintf.hh"
#include "base/intmath.hh"

namespace gem5
{

BaseSetAssoc::BaseSetAssoc(const Params &p)
    :BaseTags(p), allocAssoc(p.assoc), blks(p.size / p.block_size),
     sequentialAccess(p.sequential_access),
     replacementPolicy(p.replacement_policy),
     enableWestStats(p.enable_west_stats)
{
    // There must be a indexing policy
    fatal_if(!p.indexing_policy, "An indexing policy is required");

    // Check parameters
    if (blkSize < 4 || !isPowerOf2(blkSize)) {
        fatal("Block size must be at least 4 and a power of 2");
    }

    westStats = nullptr;
    if (enableWestStats) {
        bool useLruPolicy = dynamic_cast<replacement_policy::LRU*>(
                replacementPolicy) != nullptr;
        fatal_if(!useLruPolicy, "LRU replacement policy is required for WEST");

        westStats = new WestTagStats(*this);
    }
}

void
BaseSetAssoc::tagsInit()
{
    // Initialize all blocks
    for (unsigned blk_index = 0; blk_index < numBlocks; blk_index++) {
        // Locate next cache block
        CacheBlk* blk = &blks[blk_index];

        // Link block to indexing policy
        indexingPolicy->setEntry(blk, blk_index);

        // Associate a data chunk to the block
        blk->data = &dataBlks[blkSize*blk_index];

        // Associate a replacement data entry to the block
        blk->replacementData = replacementPolicy->instantiateEntry();

        // This is not used as of now but we set it for security
        blk->registerTagExtractor(genTagExtractor(indexingPolicy));
    }
}

void
BaseSetAssoc::invalidate(CacheBlk *blk)
{
    // Notify partitioning policies of release of ownership
    if (partitionManager) {
        partitionManager->notifyRelease(blk->getPartitionId(), blk);
    }

    BaseTags::invalidate(blk);

    // Decrease the number of tags in use
    stats.tagsInUse--;

    // Invalidate replacement data
    replacementPolicy->invalidate(blk->replacementData);
}

void
BaseSetAssoc::moveBlock(CacheBlk *src_blk, CacheBlk *dest_blk)
{
    BaseTags::moveBlock(src_blk, dest_blk);

    // Since the blocks were using different replacement data pointers,
    // we must touch the replacement data of the new entry, and invalidate
    // the one that is being moved.
    replacementPolicy->invalidate(src_blk->replacementData);
    replacementPolicy->reset(dest_blk->replacementData);
}

BaseSetAssoc::WestTagStats::WestTagStats(BaseSetAssoc &_tags)
    : statistics::Group(&_tags),
    tags(_tags),
    _name(_tags.name() + ".westStats"),
    recentSetCount(8),

    ADD_STAT(setStackDistance, statistics::units::Count::get(),
            "The number of times a data block in a certain set and stack "
            "position is accessed."),
    ADD_STAT(setReuse, statistics::units::Count::get(),
            "The number of times an access is to a set in a certain position "
            "of the most-recently visited sets."),
    ADD_STAT(writeCount, statistics::units::Count::get(),
            "Number of writes for each set and stack position."),
    ADD_STAT(readCount, statistics::units::Count::get(),
            "Number of reads for each set and stack position."),
    ADD_STAT(setAccessDistribution, statistics::units::Count::get(),
            "The number of accesses to each set.")
{
}

void
BaseSetAssoc::WestTagStats::regStats()
{
    using namespace statistics;

    statistics::Group::regStats();

    // One additional element for set accesses beyond the number tracked.
    setStackDistance
        .init(tags.indexingPolicy->numSets, tags.indexingPolicy->assoc + 1);

    setReuse
        .init(recentSetCount + 1);

    writeCount
        .init(tags.indexingPolicy->numSets, tags.indexingPolicy->assoc + 1);

    readCount
        .init(tags.indexingPolicy->numSets, tags.indexingPolicy->assoc + 1);

    setAccessDistribution
        .init(tags.indexingPolicy->numSets);
}


void
BaseSetAssoc::WestTagStats::updateRecentSets(uint32_t set)
{
    // Check to see if this set is already in the list.
    for (auto it = recentSets.begin(); it != recentSets.end(); it++) {
        if (*it == set) {
            // This set is already in the list. Move it to the front of the
            // list (most recent).
            recentSets.erase(it);
            recentSets.push_front(set);
            return;
        }
    }

    // This set is not in the list of recent sets.

    // Make space if needed.
    if (recentSets.size() == recentSetCount) {
        recentSets.pop_back();
    }

    // Add this set as the most recent set.
    recentSets.push_front(set);

    // Print for debugging.
    std::ostringstream str;
    ccprintf(str, "[");
    for (auto it = recentSets.begin(); it != recentSets.end(); it++) {
        ccprintf(str, "%llu, ", *it);
    }
    ccprintf(str, "]");
    DPRINTF(WestStats, "%s: recentSets: %s\n", __func__, str.str());
}


uint32_t
BaseSetAssoc::WestTagStats::getSetReuseDistance(uint32_t set)
{
    int i = 0;
    for (auto it = recentSets.begin(); it != recentSets.end(); it++) {
        if (*it == set) {
            return i;
        }
        i++;
    }

    return recentSetCount;
}

} // namespace gem5
