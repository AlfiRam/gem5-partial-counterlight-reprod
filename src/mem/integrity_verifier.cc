/*
 * Copyright (c) 2018, 2020 ARM Limited
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

#include "mem/integrity_verifier.hh"

#include "base/addr_range_list.hh"
#include "cpu/utils.hh"
#include "debug/AbstractIntegrityVerifier.hh"
#include "debug/AbstractIntegrityVerifierInit.hh"
#include "debug/AbstractIntegrityVerifierReqs.hh"
#include "debug/AbstractIntegrityVerifierResps.hh"
#include "debug/IntegrityNodeLocationMap.hh"
#include "mem/mtree/timing_bmt.hh"
#include "mem/mtree/timing_tree.hh"

namespace gem5
{

AbstractIntegrityVerifier::AbstractIntegrityVerifier(
    const Params &p
)
    : ClockedObject(p),
      integrityTreeType(p.integrity_tree_type),
      _requestorId(p.system->getRequestorId(this)),
      integrityHashingLatency(Cycles(p.integrity_hashing_latency)),
      xorLatency(Cycles(p.xor_latency)),
      readPathMode(p.read_path_mode),
      parityDecodeLatency(Cycles(p.parity_decode_latency)),
      system(p.system),
      dramFullRanges(p.dram_full_ranges.begin(), p.dram_full_ranges.end()),
      dramOsRanges(p.dram_os_ranges.begin(), p.dram_os_ranges.end()),
      requestPort(name() + "-mem_side_port", *this),
      responsePort(name() + "-cpu_side_port", *this),
      metadataRequestPort(name() + "-metadata_req_port", *this),
      metadataResponsePort(name() + "-metadata_resp_port", *this),
      reqQueue(*this, requestPort),
      respQueue(*this, responsePort),
      snoopRespQueue(*this, requestPort),
      metadataReqQueue(*this, metadataRequestPort),
      metadataRespQueue(*this, metadataResponsePort),
      metadataSnoopRespQueue(*this, metadataRequestPort),
      unifiedUpstreamCache(p.unified_upstream_cache),
      stats(this)
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

    // Create convienence range list for all integrity data
    for (auto range : dramIntegrityRanges) {
        integrityRanges.emplace_back(range);
    }

    switch (integrityTreeType) {
        case enums::IntegrityTreeType::TimingTree:
        integrityTree = new TimingTree(
            (unsigned int)p.integrity_tree_arity,
            rangeListSize(dramOsRanges)
        );
        break;

        case enums::IntegrityTreeType::TimingBmt:
        integrityTree = new TimingBmt(
            (unsigned int)p.integrity_tree_arity,
            rangeListSize(dramOsRanges)
        );
        break;

        default:
        panic("Invalid integrity tree type.");
    }

    DPRINTF(AbstractIntegrityVerifierInit,
        "%s: dramFullRanges: %s\n",
        __func__, rangeListToString(dramFullRanges));
    DPRINTF(AbstractIntegrityVerifierInit,
        "%s: dramOsRanges: %s\n",
        __func__, rangeListToString(dramOsRanges));
    DPRINTF(AbstractIntegrityVerifierInit,
        "%s: dramIntegrityRanges: %s\n",
        __func__, rangeListToString(dramIntegrityRanges));
}

AbstractIntegrityVerifier::~AbstractIntegrityVerifier()
{
    delete integrityTree;
}

void
AbstractIntegrityVerifier::init()
{
    if (!responsePort.isConnected() || !requestPort.isConnected())
        fatal("Integrity verifier is not connected on both sides.\n");

    if (unifiedUpstreamCache) {
        if (!metadataRequestPort.isConnected())
            fatal("Metadata cache is not connected to integrity verifier.\n");
        if (metadataResponsePort.isConnected())
            fatal("Metadata response port should not be connected to "
                  "integrity verifier if upstream cache is used as metadata "
                  "cache.\n");
    } else {
        if (!metadataResponsePort.isConnected() ||
            !metadataRequestPort.isConnected())
            fatal("Metadata cache is not connected to integrity verifier.\n");
    }


    if (!hasValidRanges()) {
        fatal("The integrity verifier has not been provided a valid "
              "combination of address ranges, based on the given integrity "
              "allocation mode.\n");
    }

    if (!treeSizeValid()) {
        fatal("The integrity tree size is larger than the amount of memory "
              "available for the tree.\n"
              "Integrity structure size: %lld\n"
              "DRAM integrity size: %lld\n",
              integrityTree->statStructureSize(),
              rangeListSize(dramIntegrityRanges));
    }
}


bool
AbstractIntegrityVerifier::hasValidRanges()
{
    return dramIntegrityRanges.size() > 0;
}

bool
AbstractIntegrityVerifier::treeSizeValid()
{
    DPRINTF(AbstractIntegrityVerifier, "%s: Integrity structure size: %lld\n",
        __func__, integrityTree->statStructureSize());

    DPRINTF(AbstractIntegrityVerifier,
        "%s: DRAM size: %lld\n",
        __func__, rangeListSize(dramIntegrityRanges));

    return integrityTree->statStructureSize() <=
            rangeListSize(dramIntegrityRanges);
}

bool
AbstractIntegrityVerifier::needsVerification(PacketPtr pkt)
{
    assert(hasValidRanges());

    auto addr = pkt->getAddr();

    return (
        (pkt->isRead() || pkt->isWrite()) &&
        (rangeListContains(dramOsRanges, addr) ||
        rangeListContains(dramIntegrityRanges, addr))
    );
}



Port &
AbstractIntegrityVerifier::getPort(const std::string &if_name, PortID idx)
{
    if (if_name == "mem_side_port") {
        return requestPort;
    } else if (if_name == "cpu_side_port") {
        return responsePort;
    } else if (if_name == "metadata_req_port") {
        return metadataRequestPort;
    } else if (if_name == "metadata_resp_port") {
        return metadataResponsePort;
    } else {
        return ClockedObject::getPort(if_name, idx);
    }
}

bool
AbstractIntegrityVerifier::trySatisfyFunctional(PacketPtr pkt)
{
    return responsePort.trySatisfyFunctional(pkt) ||
        requestPort.trySatisfyFunctional(pkt);
}




AbstractIntegrityVerifier::ResponsePort::
ResponsePort(const std::string &_name, AbstractIntegrityVerifier &_parent)
    : QueuedResponsePort(_name, _parent.respQueue),
      parent(_parent)
{
}

Tick
AbstractIntegrityVerifier::ResponsePort::recvAtomic(PacketPtr pkt)
{
    const Tick delay = parent.delayReq(pkt) + parent.delayResp(pkt);

    return delay + parent.requestPort.sendAtomic(pkt);
}

bool
AbstractIntegrityVerifier::ResponsePort::recvTimingReq(PacketPtr pkt)
{
    return parent.processReq(pkt);
}

void
AbstractIntegrityVerifier::ResponsePort::recvFunctional(PacketPtr pkt)
{
    if (parent.trySatisfyFunctional(pkt)) {
        pkt->makeResponse();
    } else {
        parent.requestPort.sendFunctional(pkt);
    }
}

bool
AbstractIntegrityVerifier::ResponsePort::recvTimingSnoopResp(PacketPtr pkt)
{
    const Tick when = curTick() + parent.delaySnoopResp(pkt);

    parent.requestPort.schedTimingSnoopResp(pkt, when);

    return true;
}

bool
AbstractIntegrityVerifier::processReq(PacketPtr pkt)
{
    DPRINTF(AbstractIntegrityVerifierReqs,
        "%s: Recv req %s (pkt addr %p, req addr %p)\n",
        __func__, pkt->print(), pkt, pkt->req);

    // We want to just bypass immediately if this is an express snoop.
    if (pkt->isExpressSnoop()) {
        return requestPort.sendTimingReq(pkt);
    }

    // If this is a metadata request, treat this as such.
    if (unifiedUpstreamCache && (
            pkt->isMetadataRequest() ||
            rangeListContains(dramIntegrityRanges, pkt->getAddr()))
        )
    {
        return processMetadataReq(pkt);
    }

    // Metadata reqeusts should not arrive here if not using a unified
    // upstream cache.
    if (!unifiedUpstreamCache) {
        assert(!pkt->isMetadataRequest());
        assert(!rangeListContains(integrityRanges, pkt->getAddr()));
    }

    markReqReceived(pkt);

    sanityCheckPacketLookup();

    // Don't do anything special for memory requests that are not actually
    // for memory.
    if (needsVerification(pkt) && pkt->isWrite()) {
        // Writebacks must be verified first before they can be forwarded to
        // memory. This will be handled now.
        return handlePacket(pkt);
    }

    // Config 2b — BmtStripped. Pre-issue the Counter-level metadata request
    // in parallel with the data DRAM read (Counter-light §IV-C Fig. 9).
    //
    // Register the data packet at macNode (not counterNode) because the
    // existing attemptXor pipeline asks getParentNode(dataPkt), which for
    // a data packet returns addressToBlockIndex(addr) = macNode. Matching
    // that wait-point lets the existing stall/resume logic work unchanged.
    //
    // The Counter response arrives keyed by counterNode, so we also stash
    // the counterNode -> req association in bmtStrippedCounterWaiters and
    // tag the issued Counter's req in bmtStrippedCounterReqs. Phase 3b.2
    // (processMetadataResp) uses these to bridge from counterNode back to
    // the waiting data packet's macNode when firing notifyParentReceived.
    //
    // All three bookkeeping inserts happen BEFORE schedMetadataReq: a
    // synchronous cache-hit response could re-enter processMetadataResp
    // immediately, and the maps must already be populated.
    //
    // Writes stay on the FullBmt path handled above — they never reach
    // this branch.
    if (readPathMode == enums::ReadPathMode::BmtStripped &&
        pkt->isRead() &&
        !pkt->isMetadataRequest() &&
        needsVerification(pkt))
    {
        size_t macNode =
            integrityTree->addressToBlockIndex(pkt->getAddr());
        size_t counterNode = integrityTree->parentBlockIndex(macNode);

        DPRINTF(AbstractIntegrityVerifier,
            "%s: BmtStripped parallel Counter pre-issue for pkt %s "
            "(MAC node %llu, Counter node %llu)\n",
            __func__, pkt->print(), macNode, counterNode);

        addToOutstandingMetadataRequests(macNode, pkt);

        PacketPtr md_pkt = generateMetadataRequest(counterNode);
        bmtStrippedCounterWaiters.emplace(counterNode, pkt->req);
        bmtStrippedCounterReqs.insert(md_pkt->req);

        schedMetadataReq(md_pkt);
        // Fall through: schedReq(pkt) below still fires the data DRAM read
        // in parallel with the Counter metadata fetch.
    }

    // If this is a read request, we will handle verification for this once it
    // becomes a response. For now, it can simply be forwarded to memory.
    // If this is something else (e.g., CleanEvict), we will similarly forward
    // this to memory.

    schedReq(pkt);

    return true;
}



AbstractIntegrityVerifier::RequestPort::RequestPort(
    const std::string &_name, AbstractIntegrityVerifier &_parent)
    : QueuedRequestPort(_name, _parent.reqQueue, _parent.snoopRespQueue),
      parent(_parent)
{
}


bool
AbstractIntegrityVerifier::RequestPort::recvTimingResp(PacketPtr pkt)
{
    return parent.processResp(pkt);
}

void
AbstractIntegrityVerifier::RequestPort::recvFunctionalSnoop(PacketPtr pkt)
{
    if (parent.trySatisfyFunctional(pkt)) {
        pkt->makeResponse();
    } else {
        parent.responsePort.sendFunctionalSnoop(pkt);
    }
}

Tick
AbstractIntegrityVerifier::RequestPort::recvAtomicSnoop(PacketPtr pkt)
{
    const Tick delay = parent.delaySnoopResp(pkt);

    return delay + parent.responsePort.sendAtomicSnoop(pkt);
}

void
AbstractIntegrityVerifier::RequestPort::recvTimingSnoopReq(PacketPtr pkt)
{
    parent.responsePort.sendTimingSnoopReq(pkt);
}

bool
AbstractIntegrityVerifier::processResp(PacketPtr pkt)
{
    markRespReceived(pkt);

    sanityCheckPacketLookup();

    DPRINTF(AbstractIntegrityVerifierResps,
        "%s: Recv resp %s (pkt addr %p, req addr %p)\n",
        __func__, pkt->print(), pkt, pkt->req);

    // Don't do anything special for memory requests that are not actually
    // for memory.
    if (needsVerification(pkt)) {
        // Read responses must be verified first before they can be used.
        if (pkt->isRead()) {
            return handlePacket(pkt);
        }

        // If this is a write response or something else (e.g., UpgradeResp),
        // drop to the default behavior below.
    }

    // This packet should not be for integrity data.
    assert(!rangeListContains(dramIntegrityRanges, pkt->getAddr()));

    schedResp(pkt);

    return true;
}






AbstractIntegrityVerifier::MetadataResponsePort::MetadataResponsePort(
    const std::string &_name, AbstractIntegrityVerifier &_parent)
        : QueuedResponsePort(_name, _parent.metadataRespQueue),
        parent(_parent)
{
}

bool
AbstractIntegrityVerifier::MetadataResponsePort::recvTimingReq(PacketPtr pkt)
{
    return parent.processMetadataReq(pkt);
}

bool
AbstractIntegrityVerifier::processMetadataReq(PacketPtr pkt)
{
    DPRINTF(AbstractIntegrityVerifierReqs,
        "%s: Recv metadata req %s (pkt addr %p, req addr %p)\n",
        __func__, pkt->print(), pkt, pkt->req);

    markMetadataReqReceived(pkt);

    sanityCheckPacketLookup();

    // We are expecting a request from the metadata cache here for integrity
    // data.

    assert(rangeListContains(dramIntegrityRanges, pkt->getAddr()));

    updatePacketLookup(pkt);

    // Pass the request to memory.
    schedReq(pkt);

    return true;
}





AbstractIntegrityVerifier::MetadataRequestPort::MetadataRequestPort(
    const std::string &_name, AbstractIntegrityVerifier &_parent)
        : QueuedRequestPort(
            _name,
            _parent.metadataReqQueue,
            _parent.metadataSnoopRespQueue
        ),
        parent(_parent)
{
}

bool
AbstractIntegrityVerifier::MetadataRequestPort::recvTimingResp(PacketPtr pkt)
{
    return parent.processMetadataResp(pkt);
}

bool
AbstractIntegrityVerifier::processMetadataResp(PacketPtr pkt)
{
    // We are expecting a response from the metadata cache for metadata.
    // The data has already been verified (before even being inserted into
    // the cache).

    assert(pkt->isMetadataRequest());
    assert(rangeListContains(dramIntegrityRanges, pkt->getAddr()));
    // BmtStripped-originated Counter responses satisfy this invariant via
    // bmtStrippedCounterReqs instead: the waiter is registered at macNode
    // (not counterNode), so outstandingMetadataRequests.find(counterNode)
    // legitimately returns end(). 3b.2 below bridges from counterNode back
    // to macNode when firing notifyParentReceived.
    // CounterLightMacBmt pre-issues MAC requests that register the waiting
    // data packet out-of-band in counterLightMacBmtMacPending rather than in
    // outstandingMetadataRequests at macNode, so widen the assertion to
    // tolerate those responses too.
    assert(outstandingMetadataRequests.find(pkt->getMetadataNode()) !=
               outstandingMetadataRequests.end() ||
           bmtStrippedCounterReqs.find(pkt->req) !=
               bmtStrippedCounterReqs.end() ||
           counterLightMacBmtMacReqs.find(pkt->req) !=
               counterLightMacBmtMacReqs.end());

    DPRINTF(AbstractIntegrityVerifierResps,
        "%s: Recv metadata resp %s (pkt addr %p, req addr %p)\n",
        __func__, pkt->print(), pkt, pkt->req);

    updatePacketLookup(pkt);

    sanityCheckPacketLookup();

    // For every packet that was waiting for this node, notify them that their
    // parent node is verified and here.
    auto range = outstandingMetadataRequests.equal_range(
        pkt->getMetadataNode());
    std::vector<PacketPtr> waitingPkts;
    // Find the packet(s) that is/are associated with this request.
    for (auto it = range.first; it != range.second; ++it) {
        assert(it->second != nullptr);
        PacketPtr packet = packetLookup.find(it->second)->second;
        waitingPkts.push_back(packet);
    }

    for (auto waitingPkt : waitingPkts) {
        notifyParentReceived(waitingPkt, pkt->getMetadataNode());
    }

    // Phase 3b.2 — BmtStripped bridge. When a Counter response we pre-issued
    // in 3a arrives, the existing equal_range(counterNode) above didn't find
    // our waiters (they're registered at macNode, not counterNode). Drain the
    // counterNode -> RequestPtr bridge map and fire notifyParentReceived at
    // macNode for each waiter — this removes the macNode entry and kicks
    // attemptXor through the existing pipeline.
    //
    // Two hazards to guard:
    //   (1) Counter-arrives-before-data race: the data packet is still a
    //       request packet in-flight to DRAM, with no hash scheduled. Calling
    //       notifyParentReceived would kick attemptXor, which can't
    //       distinguish "hash never scheduled" from "hash done" and would
    //       schedule XOR on a still-in-flight request packet (same bug class
    //       as the original Phase 3 diagnosis). Guard: only call
    //       notifyParentReceived if the data response has arrived (hash is
    //       scheduled/in-progress OR packet is in
    //       outstandingIntegrityVerification). Otherwise just remove the
    //       macNode dependency and let the later handlePacket flow resume.
    //   (2) Pathologically-late Counter arrival: the data packet has already
    //       completed and been drained from packetLookup. packetLookup.find
    //       returns end(); dereferencing would crash. Guard: skip with a
    //       DPRINTF; don't assert.
    if (readPathMode == enums::ReadPathMode::BmtStripped &&
        bmtStrippedCounterReqs.find(pkt->req) !=
            bmtStrippedCounterReqs.end())
    {
        uint64_t counterNode = pkt->getMetadataNode();
        auto bmt_range = bmtStrippedCounterWaiters.equal_range(counterNode);
        std::vector<RequestPtr> waitingReqs;
        for (auto it = bmt_range.first; it != bmt_range.second; ++it) {
            waitingReqs.push_back(it->second);
        }
        bmtStrippedCounterWaiters.erase(counterNode);
        bmtStrippedCounterReqs.erase(pkt->req);

        for (auto req : waitingReqs) {
            auto pl_it = packetLookup.find(req);
            if (pl_it == packetLookup.end()) {
                DPRINTF(AbstractIntegrityVerifier,
                    "%s: BmtStripped late Counter arrival (counterNode "
                    "%llu): data packet for req %p already completed and "
                    "left packetLookup. Skipping.\n",
                    __func__, counterNode, req.get());
                continue;
            }
            PacketPtr dataPkt = pl_it->second;
            uint64_t macNode =
                integrityTree->addressToBlockIndex(dataPkt->getAddr());

            bool dataResponseArrived =
                outstandingIntegrityHashes.count(dataPkt->req) > 0 ||
                outstandingIntegrityVerification.count(dataPkt) > 0;
            if (dataResponseArrived) {
                DPRINTF(AbstractIntegrityVerifier,
                    "%s: BmtStripped bridge notify for pkt %s "
                    "(counterNode %llu -> macNode %llu)\n",
                    __func__, dataPkt->print(), counterNode, macNode);
                notifyParentReceived(dataPkt, macNode);
            } else {
                DPRINTF(AbstractIntegrityVerifier,
                    "%s: BmtStripped bridge (early Counter) for pkt %s "
                    "(counterNode %llu): data response not yet arrived; "
                    "clearing macNode %llu dependency without attemptXor\n",
                    __func__, dataPkt->print(), counterNode, macNode);
                removeFromOutstandingMetadataRequests(macNode, dataPkt);
            }
        }
    }

    // Phase 3.6 — CounterLightMacBmt MAC bridge. A data read under
    // CounterLightMacBmt has two independent dependencies: the BMT walk at
    // treeLeafNode (tracked via outstandingMetadataRequests, handled above
    // like CounterLightBmt) AND a separate MAC-block fetch tracked here.
    // When the pre-issued MAC response arrives we (a) unconditionally clear
    // counterLightMacBmtMacPending for every waiter — that is the stall bit
    // attemptXor checks — and (b) kick attemptXor only if the data response
    // has already arrived. Hazards (mirror the BmtStripped bridge):
    //   (1) MAC-before-data: data packet still in flight to DRAM, no hash
    //       scheduled. Calling attemptXor would misread "hash never
    //       scheduled" as "hash done". Guard: only call attemptXor when the
    //       data packet is in outstandingIntegrityHashes or
    //       outstandingIntegrityVerification. The MAC-pending bit is still
    //       cleared, so the later hash-completion attemptXor will pass the
    //       new MAC check.
    //   (2) Pathologically-late MAC arrival: data packet already drained
    //       from packetLookup. Skip with a DPRINTF — in a well-formed run
    //       this cannot happen (attemptXor would have stalled until MAC
    //       pending cleared), but the guard is defense-in-depth.
    if (readPathMode == enums::ReadPathMode::CounterLightMacBmt &&
        counterLightMacBmtMacReqs.find(pkt->req) !=
            counterLightMacBmtMacReqs.end())
    {
        uint64_t macNode = pkt->getMetadataNode();
        auto mac_range = counterLightMacBmtMacWaiters.equal_range(macNode);
        std::vector<RequestPtr> waitingReqs;
        for (auto it = mac_range.first; it != mac_range.second; ++it) {
            waitingReqs.push_back(it->second);
        }
        counterLightMacBmtMacWaiters.erase(macNode);
        counterLightMacBmtMacReqs.erase(pkt->req);

        for (auto req : waitingReqs) {
            // Clear the stall bit unconditionally — attemptXor's MAC check
            // is a set-membership test on this req.
            counterLightMacBmtMacPending.erase(req);

            auto pl_it = packetLookup.find(req);
            if (pl_it == packetLookup.end()) {
                DPRINTF(AbstractIntegrityVerifier,
                    "%s: CounterLightMacBmt late MAC arrival (macNode "
                    "%llu): data packet for req %p already completed and "
                    "left packetLookup. Skipping.\n",
                    __func__, macNode, req.get());
                continue;
            }
            PacketPtr dataPkt = pl_it->second;

            bool dataResponseArrived =
                outstandingIntegrityHashes.count(dataPkt->req) > 0 ||
                outstandingIntegrityVerification.count(dataPkt) > 0;
            if (dataResponseArrived) {
                DPRINTF(AbstractIntegrityVerifier,
                    "%s: CounterLightMacBmt MAC bridge attemptXor for pkt "
                    "%s (macNode %llu)\n",
                    __func__, dataPkt->print(), macNode);
                attemptXor(dataPkt);
            } else {
                DPRINTF(AbstractIntegrityVerifier,
                    "%s: CounterLightMacBmt MAC bridge (early MAC) for pkt "
                    "%s (macNode %llu): data response not yet arrived; "
                    "MAC-pending cleared, deferring attemptXor to "
                    "hash-completion path\n",
                    __func__, dataPkt->print(), macNode);
            }
        }
    }

    removeFromPacketLookup(pkt);

    delete pkt;

    return true;
}







size_t
AbstractIntegrityVerifier::getParentNode(PacketPtr pkt)
{
    if (pkt->isMetadataRequest()) {
        // This function should not be called if this is already the root
        // metadata node.
        assert(pkt->getMetadataNode() != 0);

        return integrityTree->parentBlockIndex(pkt->getMetadataNode());
    }

    // Config 4 / 5 — CounterLightBmt & CounterLightMacBmt redirect. For read
    // data packets, the "parent" the pipeline keys on is TreeLeaf (MAC +
    // Counter are skipped for the walk; counter rides in parity). The data
    // packet is registered on treeLeafNode by the matching handlePacket
    // branch; attemptXor, hasOutstandingMetadataRequest, and
    // parentNodeIsPendingEviction all call getParentNode(pkt) to look up the
    // same node, so they must agree. Triple-guarded on mode + isRead() +
    // !isMetadataRequest() so metadata and write packets never land here.
    // CounterLightMacBmt adds a separate MAC-fetch dependency, tracked
    // out-of-band via counterLightMacBmtMacPending — so the redirected
    // treeLeafNode remains the single "parent" the generic pipeline sees.
    if ((readPathMode == enums::ReadPathMode::CounterLightBmt ||
         readPathMode == enums::ReadPathMode::CounterLightMacBmt) &&
        pkt->isRead() &&
        !pkt->isMetadataRequest())
    {
        size_t macNode = integrityTree->addressToBlockIndex(pkt->getAddr());
        size_t counterNode = integrityTree->parentBlockIndex(macNode);
        return integrityTree->parentBlockIndex(counterNode);
    }

    return integrityTree->addressToBlockIndex(pkt->getAddr());
}


bool
AbstractIntegrityVerifier::parentNodeIsSecureRoot(PacketPtr pkt)
{
    return (pkt->isMetadataRequest() && pkt->getMetadataNode() == 0);
}


bool
AbstractIntegrityVerifier::parentNodeIsPendingEviction(PacketPtr pkt)
{
    if (parentNodeIsSecureRoot(pkt)) {
        return false;
    }

    auto parentNode = getParentNode(pkt);
    return (pendingMetadataEvictions.find(parentNode) !=
            pendingMetadataEvictions.end());
}


Addr
AbstractIntegrityVerifier::getIntegrityNodeLocation(size_t node)
{
    Addr addr;

    // All integrity data is in DRAM.
    auto offset = integrityTree->simulatedBlockOffset(node);
    for (auto range : dramIntegrityRanges) {
        if (offset > range.size()) {
            // This should be in a following range in the list.
            // We will "eat" the offset amount corresponding to the range
            // being skipped over.
            offset -= range.size();
            continue;
        }
        addr = range.start() + offset;
        break;
    }

    DPRINTF(IntegrityNodeLocationMap,
        "%s: Request for node %llu <-- Creating request for 0x%x\n",
        __func__, node, addr);

    return addr;
}

PacketPtr
AbstractIntegrityVerifier::generateMetadataRequest(PacketPtr pkt)
{
    size_t parentNode = getParentNode(pkt);

    return generateMetadataRequest(parentNode);
}

PacketPtr
AbstractIntegrityVerifier::generateMetadataRequest(size_t node)
{
    uint64_t reqAddr;
    assert(hasValidRanges());
    reqAddr = getIntegrityNodeLocation(node);

    // Create the metadata request and packet.
    RequestPtr req = std::make_shared<Request>(
        reqAddr,
        64, // Size
        0, // No flags
        _requestorId
    );
    DPRINTF(AbstractIntegrityVerifier,
        "%s: Allocated request %p\n",
        __func__, req);
    PacketPtr metadataRequestPkt = Packet::createRead(req);
    uint8_t* pkt_data = new uint8_t[req->getSize()];
    metadataRequestPkt->dataDynamic(pkt_data);
    // Set the flag that this is a metadata request.
    metadataRequestPkt->setMetadataRequest();
    switch (integrityTree->getNodeType(node))
    {
        case AbstractIntegrityTree::TreeNodeType::TreeNode:
            metadataRequestPkt->setMetadataType(0);
            break;
        case AbstractIntegrityTree::TreeNodeType::Counter:
            metadataRequestPkt->setMetadataType(1);
            break;
        case AbstractIntegrityTree::TreeNodeType::MAC:
            metadataRequestPkt->setMetadataType(2);
            break;
        default:
            fatal("Unknown metadata type.");
    }

    // Indicate the integrity tree node that will be accessed.
    metadataRequestPkt->setMetadataNode(node);

    return metadataRequestPkt;
}

void
AbstractIntegrityVerifier::saveRetryVerify(PacketPtr pkt)
{
    schedule(new RetryVerifyEvent(this, pkt), clockEdge(Cycles(10)));
}

void
AbstractIntegrityVerifier::saveRetryReq(PacketPtr pkt)
{
    schedule(new RetryReqEvent(this, pkt), clockEdge(Cycles(10)));
}

bool
AbstractIntegrityVerifier::handlePacket(PacketPtr pkt)
{
    DPRINTF(AbstractIntegrityVerifier,
            "%s: Handling verification of packet %s\n",
            __func__, pkt->print());

    // TODO May need to adjust this
    if (outstandingIntegrityVerification.size() > maxEncQueueSize) {
        DPRINTF(AbstractIntegrityVerifier,
            "%s: Rejecting %s due to encryption queue full. Retrying "
            "later.\n",
            __func__, pkt->print());

        return false;
    }

    // We aren't ready for this packet. Don't accept it until the parent node
    // is fully evicted.
    if (parentNodeIsPendingEviction(pkt)) {
        DPRINTF(AbstractIntegrityVerifier,
            "%s: Rejecting %s due to parent pending eviction. Retrying "
            "later.\n",
            __func__, pkt->print());
        saveRetryVerify(pkt);
        return true;
    }

    if (!pkt->isMetadataRequest() &&
        pkt->isRequest() &&
        addrInOIV(pkt->getAddr()))
    {
        DPRINTF(AbstractIntegrityVerifier,
            "%s: Rejecting %s due to prior request with the same address "
            "being served. Retrying later.\n",
            __func__, pkt->print());
        saveRetryVerify(pkt);
        return true;
    }

    // Config 3 — CounterLight (ISCA 2024). For data read responses, skip all
    // read-side metadata traffic. Charge parityDecodeLatency (§IV-D, decoding
    // the counter from ECC parity bits) + integrityHashingLatency (reused as
    // the per-block MAC-check cost — same role it plays for the data packet
    // in FullBmt; adding a separate macCheckLatency would double-charge).
    // Writes are excluded by isRead() and fall through to the Full-BMT path.
    if (readPathMode == enums::ReadPathMode::CounterLight &&
        !pkt->isMetadataRequest() &&
        pkt->isRead() &&
        pkt->isResponse())
    {
        DPRINTF(AbstractIntegrityVerifier,
            "%s: CounterLight short-circuit for pkt %s (parity-decode + "
            "MAC-check, no metadata fetch)\n",
            __func__, pkt->print());
        schedule(
            new HashCompletionEvent(this, pkt),
            clockEdge(parityDecodeLatency + integrityHashingLatency)
        );
        assert(outstandingIntegrityHashes.find(pkt->req) ==
                outstandingIntegrityHashes.end());
        assert(outstandingIntegrityVerification.find(pkt) ==
                outstandingIntegrityVerification.end());
        outstandingIntegrityHashes.insert(pkt->req);
        outstandingIntegrityVerification.insert(pkt);
        assert(packetLookup[pkt->req] == pkt);
        // No metadata request, no parent dependency. XOR fires from
        // completeIntegrityHash → attemptXor → completeXor →
        // completeIntegrityVerification → schedResp.
        return true;
    }

    // Config 4 — CounterLightBmt. Layers the full BMT walk back on top of the
    // CounterLight read path to price the cost of adding replay protection to
    // Counter-light. Same parity-decode + MAC-check hash timing as
    // CounterLight (no MAC/Counter DRAM fetch — counter rides in parity), but
    // we register the data packet on the TreeLeaf node and kick off a walk
    // starting there. MAC and Counter levels are skipped; the walk proceeds
    // TreeLeaf → ... → TreeRoot through the normal metadata response path
    // (when a TreeLeaf response re-enters handlePacket, pkt->isMetadataRequest
    // is true and getParentNode returns parentBlockIndex as usual).
    //
    // The data packet's parent-node abstraction (getParentNode) is redirected
    // to treeLeafNode for this mode below, so attemptXor /
    // hasOutstandingMetadataRequest / parentNodeIsPendingEviction all see the
    // same node we registered on here. Writes fall through to Full-BMT.
    if (readPathMode == enums::ReadPathMode::CounterLightBmt &&
        !pkt->isMetadataRequest() &&
        pkt->isRead() &&
        pkt->isResponse())
    {
        DPRINTF(AbstractIntegrityVerifier,
            "%s: CounterLightBmt hash + TreeLeaf walk for pkt %s\n",
            __func__, pkt->print());
        schedule(
            new HashCompletionEvent(this, pkt),
            clockEdge(parityDecodeLatency + integrityHashingLatency)
        );
        assert(outstandingIntegrityHashes.find(pkt->req) ==
                outstandingIntegrityHashes.end());
        assert(outstandingIntegrityVerification.find(pkt) ==
                outstandingIntegrityVerification.end());
        outstandingIntegrityHashes.insert(pkt->req);
        outstandingIntegrityVerification.insert(pkt);
        assert(packetLookup[pkt->req] == pkt);

        size_t macNode = integrityTree->addressToBlockIndex(pkt->getAddr());
        size_t counterNode = integrityTree->parentBlockIndex(macNode);
        size_t treeLeafNode = integrityTree->parentBlockIndex(counterNode);

        // Batch against any in-flight request for the same TreeLeaf (H6).
        bool needsRequest =
            outstandingMetadataRequests.find(treeLeafNode) ==
            outstandingMetadataRequests.end();
        addToOutstandingMetadataRequests(treeLeafNode, pkt);
        if (needsRequest) {
            DPRINTF(AbstractIntegrityVerifier,
                "%s: CounterLightBmt issuing TreeLeaf request for node "
                "%llu (pkt %s)\n",
                __func__, treeLeafNode, pkt->print());
            PacketPtr md_pkt = generateMetadataRequest(treeLeafNode);
            schedMetadataReq(md_pkt);
        } else {
            DPRINTF(AbstractIntegrityVerifier,
                "%s: CounterLightBmt batching on outstanding TreeLeaf "
                "node %llu (pkt %s)\n",
                __func__, treeLeafNode, pkt->print());
        }
        return true;
    }

    // Config 5 — CounterLightMacBmt. Hypothetical hybrid: counter rides in
    // parity (CounterLight-style, no Counter fetch) but MAC is stored in a
    // separate DRAM block (FullBmt-style MAC fetch) AND the counter's
    // integrity is backstopped by a BMT walk from TreeLeaf (CounterLightBmt-
    // style). Two independent dependencies must complete before XOR:
    //   (1) TreeLeaf walk — registered at treeLeafNode via the widened
    //       getParentNode redirect; released through notifyParentReceived on
    //       the generic metadata-response path.
    //   (2) MAC fetch — tracked out-of-band via
    //       counterLightMacBmtMacPending; released through the MAC bridge
    //       in processMetadataResp, which clears the pending bit and kicks
    //       attemptXor.
    // Insert order of the three bookkeeping containers matters (H5,
    // synchronous cache-hit re-entry): pending bit → waiters map → reqs set,
    // all BEFORE schedMetadataReq so a same-tick re-entry into
    // processMetadataResp finds a consistent view.
    if (readPathMode == enums::ReadPathMode::CounterLightMacBmt &&
        !pkt->isMetadataRequest() &&
        pkt->isRead() &&
        pkt->isResponse())
    {
        DPRINTF(AbstractIntegrityVerifier,
            "%s: CounterLightMacBmt hash + TreeLeaf walk + MAC fetch for "
            "pkt %s\n",
            __func__, pkt->print());
        schedule(
            new HashCompletionEvent(this, pkt),
            clockEdge(parityDecodeLatency + integrityHashingLatency)
        );
        assert(outstandingIntegrityHashes.find(pkt->req) ==
                outstandingIntegrityHashes.end());
        assert(outstandingIntegrityVerification.find(pkt) ==
                outstandingIntegrityVerification.end());
        outstandingIntegrityHashes.insert(pkt->req);
        outstandingIntegrityVerification.insert(pkt);
        assert(packetLookup[pkt->req] == pkt);

        size_t macNode = integrityTree->addressToBlockIndex(pkt->getAddr());
        size_t counterNode = integrityTree->parentBlockIndex(macNode);
        size_t treeLeafNode = integrityTree->parentBlockIndex(counterNode);

        // --- (1) BMT walk dependency (treeLeafNode). Identical shape to
        //         the CounterLightBmt branch above; see H6/H7/H10/H11. ---
        bool needsTreeRequest =
            outstandingMetadataRequests.find(treeLeafNode) ==
            outstandingMetadataRequests.end();
        addToOutstandingMetadataRequests(treeLeafNode, pkt);
        if (needsTreeRequest) {
            DPRINTF(AbstractIntegrityVerifier,
                "%s: CounterLightMacBmt issuing TreeLeaf request for node "
                "%llu (pkt %s)\n",
                __func__, treeLeafNode, pkt->print());
            PacketPtr tree_pkt = generateMetadataRequest(treeLeafNode);
            schedMetadataReq(tree_pkt);
        } else {
            DPRINTF(AbstractIntegrityVerifier,
                "%s: CounterLightMacBmt batching on outstanding TreeLeaf "
                "node %llu (pkt %s)\n",
                __func__, treeLeafNode, pkt->print());
        }

        // --- (2) MAC fetch dependency (macNode). Pre-issue bookkeeping in
        //         insert-order required by H5; inserts MUST precede
        //         schedMetadataReq. ---
        counterLightMacBmtMacPending.insert(pkt->req);
        bool needsMacRequest =
            counterLightMacBmtMacWaiters.find(macNode) ==
            counterLightMacBmtMacWaiters.end();
        counterLightMacBmtMacWaiters.emplace(macNode, pkt->req);
        if (needsMacRequest) {
            DPRINTF(AbstractIntegrityVerifier,
                "%s: CounterLightMacBmt issuing MAC request for node "
                "%llu (pkt %s)\n",
                __func__, macNode, pkt->print());
            PacketPtr mac_pkt = generateMetadataRequest(macNode);
            counterLightMacBmtMacReqs.insert(mac_pkt->req);
            schedMetadataReq(mac_pkt);
        } else {
            DPRINTF(AbstractIntegrityVerifier,
                "%s: CounterLightMacBmt batching on outstanding MAC "
                "node %llu (pkt %s)\n",
                __func__, macNode, pkt->print());
        }
        return true;
    }

    // We are either getting a read response from memory or a writeback request
    // from the LLC. Integrity metadata (at least in the cache) should be
    // updated for this data's parent node first before being allowed to be
    // sent to the CPU (for read responses) or to be written to memory (for
    // write requests).

    // Kick off hashing. Add to a pending hashing list. Schedule an event
    // when the hashing completes. Keep in mind we are essentially holding
    // hostage the memory packet until all verification is complete.
    DPRINTF(AbstractIntegrityVerifier, "%s: Scheduling hash for pkt %s\n",
        __func__, pkt->print());
    schedule(
        new HashCompletionEvent(this, pkt),
        clockEdge(integrityHashingLatency)
    );
    // This packet should not already be in the process of being verified.
    assert(outstandingIntegrityHashes.find(pkt->req) ==
            outstandingIntegrityHashes.end());
    assert(outstandingIntegrityVerification.find(pkt) ==
            outstandingIntegrityVerification.end());
    outstandingIntegrityHashes.insert(pkt->req);
    outstandingIntegrityVerification.insert(pkt);
    assert(packetLookup[pkt->req] == pkt);


    // Config 2b — BmtStripped (3b.1). Two walk-termination paths:
    //
    //   (a) Data packet: its hash has been scheduled above. The macNode
    //       dependency was registered in processReq (3a), so attemptXor
    //       will stall until 3b.2 fires notifyParentReceived(macNode).
    //       Skip the MAC-level request that FullBmt would issue below.
    //
    //   (b) Counter metadata packet we pre-issued in 3a, returning from
    //       DRAM on a cache miss. Its own hash is scheduled; getParentNode
    //       for metadata returns parentBlockIndex (TreeLeaf), which we
    //       never register, so attemptXor proceeds and the Counter flows
    //       through completeIntegrityVerification -> schedMetadataResp
    //       back to the metadata cache. No TreeLeaf request issued.
    //
    // Any other metadata packet (FullBmt-path write walks, etc.) falls
    // through to the normal Full-BMT logic.
    if (readPathMode == enums::ReadPathMode::BmtStripped) {
        if (!pkt->isMetadataRequest()) {
            DPRINTF(AbstractIntegrityVerifier,
                "%s: BmtStripped data-packet short-circuit for pkt %s "
                "(macNode dependency pre-registered in processReq; "
                "awaiting Counter response via 3b.2)\n",
                __func__, pkt->print());
            return true;
        }
        if (bmtStrippedCounterReqs.find(pkt->req) !=
            bmtStrippedCounterReqs.end())
        {
            DPRINTF(AbstractIntegrityVerifier,
                "%s: BmtStripped Counter walk-termination for pkt %s "
                "(3a-originated; no TreeLeaf request)\n",
                __func__, pkt->print());
            return true;
        }
    }

    // Config 5 — CounterLightMacBmt defensive MAC walk-termination arm.
    // processMetadataResp should handle the MAC response entirely (drain +
    // delete, no handlePacket call), so this arm is expected to be
    // unreachable. But the existing BmtStripped branch has a symmetric
    // Counter-termination that demonstrably IS reached under some pipeline
    // configurations, so we mirror the defense: if a MAC-fetch we
    // pre-issued ever arrives here, don't walk up to Counter — terminate.
    if (readPathMode == enums::ReadPathMode::CounterLightMacBmt &&
        counterLightMacBmtMacReqs.find(pkt->req) !=
            counterLightMacBmtMacReqs.end())
    {
        DPRINTF(AbstractIntegrityVerifier,
            "%s: CounterLightMacBmt MAC walk-termination for pkt %s "
            "(pre-issued MAC fetch; no Counter request)\n",
            __func__, pkt->print());
        return true;
    }

    // Check for the parent node in the metadata cache.
    size_t parentNode;
    if (!parentNodeIsSecureRoot(pkt)) {
        parentNode = getParentNode(pkt);
        DPRINTF(AbstractIntegrityVerifier,
            "%s: Parent metadata node for pkt %s is %llu\n",
            __func__, pkt->print(), parentNode);
    } else {
        DPRINTF(AbstractIntegrityVerifier,
            "%s: Parent metadata node for pkt %s is secure root\n",
            __func__, pkt->print());
        // No need to make a metadata request. Consider it instantly fulfilled.
        return true;
    }

    // If there is already an outstanding request for this parent node, we can
    // batch this with the existing request.
    bool needsRequest = outstandingMetadataRequests.find(parentNode) ==
                        outstandingMetadataRequests.end();

    addToOutstandingMetadataRequests(parentNode, pkt);
    if (needsRequest) {
        // A request has not yet been sent. We will craft a request packet for
        // metadata to memory to get the parent node. Then we schedule the
        // metadata request.
        DPRINTF(AbstractIntegrityVerifier,
                "%s: pkt %s will generate a metadata request for parent "
                "%llu\n",
                __func__, pkt->print(), parentNode);
        PacketPtr metadataRequestPkt = generateMetadataRequest(pkt);
        schedMetadataReq(metadataRequestPkt);
    } else {
        DPRINTF(AbstractIntegrityVerifier,
            "%s: pkt %s does not need to create a metadata request. Parent "
            "%llu is already requested. Batching.\n",
            __func__, pkt->print(), parentNode);
    }

    // We will hold on to the original packet until the time comes to forward
    // this to the destination.
    return true;
}


void
AbstractIntegrityVerifier::completeIntegrityHash(PacketPtr pkt)
{
    // Take this request off the pending hash list.
    assert(outstandingIntegrityHashes.find(pkt->req) !=
           outstandingIntegrityHashes.end());
    outstandingIntegrityHashes.erase(pkt->req);

    DPRINTF(AbstractIntegrityVerifier, "%s: Completed hash of pkt %s\n",
        __func__, pkt->print());

    // Attempt verification (we will call a separate function since
    // we don't know if the hashing or potential parent node retrieval will
    // complete first)
    attemptXor(pkt);
}



void
AbstractIntegrityVerifier::notifyParentReceived(
    PacketPtr pkt,
    uint64_t node_completed
)
{
    assert(hasOutstandingMetadataRequest(node_completed, pkt));
    removeFromOutstandingMetadataRequests(node_completed, pkt);
    DPRINTF(AbstractIntegrityVerifier, "%s: Got parent %llu of pkt %s\n",
        __func__, node_completed, pkt->print());

    // The parent of the node requested by `pkt` is received and verified.
    // We are now able to attempt verification.
    attemptXor(pkt);
}


bool
AbstractIntegrityVerifier::attemptXor(PacketPtr pkt)
{
    // Check if both the hash generation is finished and the corresponding
    // parent node is available. If not, keep waiting. This function will
    // be called again for the second of the two that finish.
    if (outstandingIntegrityHashes.find(pkt->req) !=
        outstandingIntegrityHashes.end()) {
        // We are not done generating the hash. We are not ready to verify.
        DPRINTF(AbstractIntegrityVerifier, "%s: Not ready to verify pkt %s, "
            "hash incomplete\n",
            __func__, pkt->print());
        return false;
    } else if (hasOutstandingMetadataRequest(pkt)) {
        // The parent node is not yet available. We are not ready to verify.
        DPRINTF(AbstractIntegrityVerifier, "%s: Not ready to verify pkt %s, "
            "parent unavailable\n",
            __func__, pkt->print());
        return false;
    } else if (readPathMode == enums::ReadPathMode::CounterLightMacBmt &&
               pkt->isRead() &&
               !pkt->isMetadataRequest() &&
               counterLightMacBmtMacPending.find(pkt->req) !=
                   counterLightMacBmtMacPending.end()) {
        // Config 5 — CounterLightMacBmt second dependency. The BMT walk at
        // treeLeafNode is already covered by hasOutstandingMetadataRequest
        // above; the MAC fetch is tracked separately and stalls XOR until
        // the MAC response arrives and the bridge in processMetadataResp
        // clears this set. Triple-guarded on mode + isRead() +
        // !isMetadataRequest() so writes and metadata packets never hit
        // this check — other modes are unaffected.
        DPRINTF(AbstractIntegrityVerifier, "%s: Not ready to verify pkt %s, "
            "CounterLightMacBmt MAC still pending\n",
            __func__, pkt->print());
        return false;
    }

    // We are ready.
    DPRINTF(AbstractIntegrityVerifier, "%s: Scheduling XOR for pkt %s\n",
        __func__, pkt->print());
    schedule(
        new XorCompletionEvent(this, pkt),
        clockEdge(xorLatency)
    );
    assert(outstandingXors.find(pkt->req) ==
           outstandingXors.end());
    outstandingXors.insert(pkt->req);

    return true;
}



void
AbstractIntegrityVerifier::completeXor(PacketPtr pkt)
{
    // Take this request off the pending XOR list.
    assert(outstandingXors.find(pkt->req) !=
           outstandingXors.end());
    outstandingXors.erase(pkt->req);

    // We now assume that the decryption/encryption needed for this packet is
    // complete, and it can move on to its destination.
    completeIntegrityVerification(pkt);
}



void
AbstractIntegrityVerifier::completeIntegrityVerification(PacketPtr pkt)
{
    outstandingIntegrityVerification.erase(pkt);
    DPRINTF(AbstractIntegrityVerifier,
            "%s: Verified pkt %s\n", __func__, pkt->print());

    if (pkt->isMetadataRequest()) {
        if (pkt->isRead()) {
            assert(pkt->isResponse());
            // Forward the packet to the metadata cache to store, which
            // notifies the requests that were waiting for this.
            schedMetadataResp(pkt);
        } else {
            // This is probably a dirty writeback.
            fatal("Unimplemented metadata writes");
            assert(pkt->isWrite());
            assert(pkt->isRequest());
            // TODO Update the parent in metadata cache...

            // Forward the packet to memory

            schedReq(pkt);
        }
        return;
    }

    // The rest of this is for handling data packets.
    assert(!pkt->isMetadataRequest());

    if (pkt->isRead()) {
        // Handling finishing integrity verification for read responses.
        // This means we can now forward the data to the CPU to be used.
        // This packet can now be properly returned up to the CPU to complete.
        schedResp(pkt);
    } else if (pkt->isWrite()) {
        // Handling finishing integrity verification for write requests.
        // This means we can now update the metadata cache and forward the data
        // to memory for storage.
        auto parentNode = getParentNode(pkt);
        // TODO Create write request for parent node in cache
        // metadataCache->modify(parentNode);
        DPRINTF(AbstractIntegrityVerifier,
            "%s: Modifying cache line %lu in metadata cache\n",
            __func__, parentNode);
        // This packet can now be properly forwarded to memory to complete.
        schedReq(pkt);
    }
}


void
AbstractIntegrityVerifier::markReqReceived(PacketPtr pkt)
{
    assert(!pkt->isMetadataRequest() &&
           !rangeListContains(integrityRanges, pkt->getAddr()));

    DPRINTF(AbstractIntegrityVerifier,
        "%s: Recv req %s (pkt addr %p, req addr %p)\n",
        __func__, pkt->print(), pkt, pkt->req);

    // Associate this packet with its request. This should only be removed
    // from packet lookup once the packet will no longer be expected to be
    // handled here anymore (either when sent to memory if it doesn't need
    // a response, or when returned to the CPU if it did need a response).
    addToPacketLookup(pkt);

    // Account for the ordering of this packet with respect to forwarding to
    // memory.
    requestQueue.push(pkt->req);

    // Account for the ordering of this packet with respect to responding to
    // the CPU.
    if (pkt->needsResponse()) {
        responseQueue.push(pkt->req);
    }
}


void
AbstractIntegrityVerifier::markMetadataReqReceived(PacketPtr pkt)
{
    assert(pkt->isMetadataRequest() ||
        rangeListContains(integrityRanges, pkt->getAddr()));

    DPRINTF(AbstractIntegrityVerifier,
        "%s: Recv metadata req %s (pkt addr %p, req addr %p)\n",
        __func__, pkt->print(), pkt, pkt->req);

    if (!pkt->isMetadataRequest()) {
        // Associate this packet with its request. This should only be removed
        // from packet lookup once the packet will no longer be expected to be
        // handled here anymore (either when sent to memory if it doesn't need
        // a response, or when returned to the CPU if it did need a response).
        addToPacketLookup(pkt);
    } else {
        // Packet lookup should already be accounted for if we created the
        // request ourselves.
        assert(packetLookup.find(pkt->req) != packetLookup.end());
    }


    // Account for the ordering of this packet with respect to forwarding to
    // memory.
    metadataRequestQueue.push(pkt->req);
}


void
AbstractIntegrityVerifier::markRespReceived(PacketPtr pkt)
{
    DPRINTF(AbstractIntegrityVerifier,
        "%s: Recv resp %s (pkt addr %p, req addr %p)\n",
        __func__, pkt->print(), pkt, pkt->req);

    // Update the request's association with its corresponding packet.
    // Sometimes, the packet pointer will change while the request remains
    // the same.
    updatePacketLookup(pkt);

    // Mark the response as returned.
    markReqEnd(pkt);
}


void
AbstractIntegrityVerifier::schedReq(PacketPtr pkt)
{
    // Mark this packet as ready to request.
    requestReady.insert(pkt->req);

    // There should be something in the request queue, or otherwise we are
    // attempting to send a request we know nothing about.
    if (pkt->isMetadataRequest() ||
        rangeListContains(integrityRanges, pkt->getAddr()))
    {
        assert(!metadataRequestQueue.empty());
    } else {
        assert(!requestQueue.empty());
    }

    // If this is a data request, this should already be added to
    // `packetLookup`.
    assert(packetLookup.find(pkt->req) != packetLookup.end());

    // Check if there's anything we can take off the queue now.
    // There are two queues: one for data and one for metadata.
    while (!requestQueue.empty()) {
        auto front = requestQueue.front();

        bool isReady = requestReady.find(front) != requestReady.end();
        if (isReady) {
            // This request is now the front of the queue and has been
            // determined ready to send. Let's send it off!
            sendReqToMem(packetLookup[front]);

            requestReady.erase(front);
            requestQueue.pop();
        } else {
            // The request at the front of the queue is not ready to send.
            // Stop.
            break;
        }
    }
    while (!metadataRequestQueue.empty()) {
        auto front = metadataRequestQueue.front();

        bool isReady = requestReady.find(front) != requestReady.end();
        if (isReady) {
            // This request is now the front of the queue and has been
            // determined ready to send. Let's send it off!
            sendReqToMem(packetLookup[front]);

            requestReady.erase(front);
            metadataRequestQueue.pop();
        } else {
            // The request at the front of the queue is not ready to send.
            // Stop.
            break;
        }
    }
}

void
AbstractIntegrityVerifier::schedResp(PacketPtr pkt)
{
    assert(!pkt->isMetadataRequest());

    // Mark this packet as ready to respond.
    responseReady.insert(pkt->req);

    // There should be something in the response queue, or otherwise we are
    // attempting to respond to a packet we know nothing about.
    assert(!responseQueue.empty());

    // This should already be added to `packetLookup`.
    assert(packetLookup.find(pkt->req) != packetLookup.end());

    // Check if there's anything we can take off the queue now.
    while (!responseQueue.empty()) {
        auto front = responseQueue.front();

        bool isReady = responseReady.find(front) != responseReady.end();
        if (isReady) {
            // This response is now the front of the queue and has been
            // determined ready to send. Let's send it off!
            sendRespToCpu(packetLookup[front]);

            responseReady.erase(front);
            responseQueue.pop();
        } else {
            // The response at the front of the queue is not ready to send.
            // Stop.
            break;
        }
    }
}


void
AbstractIntegrityVerifier::schedMetadataReq(PacketPtr pkt)
{
    // Similar to schedReq(), but sending to the metadata cache.
    sendReqToMetadataCache(pkt);
}

void
AbstractIntegrityVerifier::schedMetadataResp(PacketPtr pkt)
{
    // Similar to schedResp(), but sending to the metadata cache.
    sendRespToMetadataCache(pkt);
}


void
AbstractIntegrityVerifier::sendReqToMem(PacketPtr pkt)
{
    // Requests should already be added to packetLookup.
    assert(packetLookup[pkt->req] == pkt);

    // Verify requests are going to places that make sense.
    if (pkt->isMetadataRequest()) {
        // This is integrity metadata.
        assert(rangeListContains(dramIntegrityRanges, pkt->getAddr()));
    } else if (needsVerification(pkt)) {
        // This is application data.
        assert(rangeListContains(dramOsRanges, pkt->getAddr()));
    }

    DPRINTF(AbstractIntegrityVerifier, "%s: Scheduling req %s to memory\n",
        __func__, pkt->print());
    requestPort.schedTimingReq(pkt, clockEdge(Cycles(1)));

    if (!pkt->needsResponse()) {
        // Packets that aren't getting a response should not be tracked for
        // response timing, and are ready to discard.
        removeFromPacketLookup(pkt);
        return;
    }

    markReqStart(pkt);
}


void
AbstractIntegrityVerifier::sendRespToCpu(PacketPtr pkt)
{
    DPRINTF(AbstractIntegrityVerifier, "%s: Scheduling resp %s to CPU\n",
        __func__, pkt->print());
    responsePort.schedTimingResp(pkt, clockEdge(Cycles(1)));

    removeFromPacketLookup(pkt);
}


void
AbstractIntegrityVerifier::sendReqToMetadataCache(PacketPtr pkt)
{
    assert(pkt->isMetadataRequest());
    assert(pkt->needsResponse());
    assert(rangeListContains(dramIntegrityRanges, pkt->getAddr()));

    addToPacketLookup(pkt);

    DPRINTF(AbstractIntegrityVerifier,
        "%s: Scheduling req %s to metadata cache\n",
        __func__, pkt->print());
    metadataRequestPort.schedTimingReq(pkt, clockEdge(Cycles(1)));
}

void
AbstractIntegrityVerifier::sendRespToMetadataCache(PacketPtr pkt)
{
    assert(pkt->isMetadataRequest() ||
           rangeListContains(integrityRanges, pkt->getAddr()));

    // Use the standard response port if we have a unified upstream cache and
    // metadata cache.
    if (!unifiedUpstreamCache) {
        DPRINTF(AbstractIntegrityVerifier,
            "%s: Scheduling resp %s to metadata cache\n",
            __func__, pkt->print());
        metadataResponsePort.schedTimingResp(pkt, clockEdge(Cycles(1)));
    } else {
        DPRINTF(AbstractIntegrityVerifier,
            "%s: Scheduling metadata resp %s to upstream (metadata cache)\n",
            __func__, pkt->print());
        responsePort.schedTimingResp(pkt, clockEdge(Cycles(1)));
    }

    // Requests made by the cache itself should not be tracked anymore.
    if (!pkt->isMetadataRequest()) {
        removeFromPacketLookup(pkt);
    }
}


void
AbstractIntegrityVerifier::markReqStart(PacketPtr pkt)
{
    assert(pkt->needsResponse());

    // This request should not already have been marked as sent.
    assert(arrivalTime.find(pkt->req) == arrivalTime.end());

    // Take a note of the memory region being used.
    if (needsVerification(pkt)) {
        // NOTE: Uses hard-coded cache line size.
        for (Addr addr = pkt->getAddr();
            addr < pkt->getAddr() + pkt->getSize();
            addr += 64)
        {
            stats.accessedCacheLines.emplace(addrBlockAlign(addr, 64));
        }
    }

    arrivalTime[pkt->req] = curTick();

    DPRINTF(AbstractIntegrityVerifier,
        "%s: arrivalTime increased. size: %d\n",
        __func__, arrivalTime.size());
}


void
AbstractIntegrityVerifier::markReqEnd(PacketPtr pkt)
{
    // This request should have been entered prior.
    assert(arrivalTime.find(pkt->req) != arrivalTime.end());

    if (needsVerification(pkt)) {
        stats.requestsHandled++;
        stats.bytesHandled += pkt->getSize();
        stats.totalRequestingTime += curTick() - arrivalTime[pkt->req];
        if (pkt->isMetadataRequest()) {
            // Metadata request
            stats.metadataReqHandled++;
            stats.metadataBytesHandled += pkt->getSize();
            stats.totalMetadataReqTime += curTick() - arrivalTime[pkt->req];

            assert(rangeListContains(dramFullRanges, pkt->getAddr()));
            stats.reqHandledDramIntegrity++;
            stats.bytesHandledDramIntegrity += pkt->getSize();
            stats.totalReqTimeDramIntegrity +=
                curTick() - arrivalTime[pkt->req];
        } else {
            // Non-metadata request.
            stats.dataReqHandled++;
            stats.dataBytesHandled += pkt->getSize();
            stats.totalDataReqTime += curTick() - arrivalTime[pkt->req];

            assert(rangeListContains(dramFullRanges, pkt->getAddr()));
            stats.reqHandledDramOs++;
            stats.bytesHandledDramOs += pkt->getSize();
            stats.totalReqTimeDramOs +=
                curTick() - arrivalTime[pkt->req];
        }

        assert(rangeListContains(dramFullRanges, pkt->getAddr()));
        stats.reqHandledDram++;
        stats.bytesHandledDram += pkt->getSize();
        stats.totalReqTimeDram +=
            curTick() - arrivalTime[pkt->req];
    }

    arrivalTime.erase(pkt->req);
    DPRINTF(AbstractIntegrityVerifier,
        "%s: arrivalTime decreased. size: %d\n",
        __func__, arrivalTime.size());
}


void
AbstractIntegrityVerifier::addToPacketLookup(PacketPtr pkt)
{
    assert(packetLookup.find(pkt->req) == packetLookup.end());
    packetLookup.emplace(pkt->req, pkt);
    DPRINTF(AbstractIntegrityVerifier,
        "%s: packetLookup increased. size: %d\n",
        __func__, packetLookup.size());
    DPRINTF(AbstractIntegrityVerifier,
        "%s: Associating req 0x%x (%p) with pkt %s (%p)\n",
        __func__,
        pkt->req->hasPaddr() ? pkt->req->getPaddr() : 9999999,
        pkt->req,
        pkt->print(),
        pkt);
}

void
AbstractIntegrityVerifier::updatePacketLookup(PacketPtr pkt)
{
    assert(packetLookup.find(pkt->req) != packetLookup.end());

    packetLookup[pkt->req] = pkt;

    DPRINTF(AbstractIntegrityVerifier,
        "%s: packetLookup updated. size: %d\n",
        __func__, packetLookup.size());
    DPRINTF(AbstractIntegrityVerifier,
        "%s: Associating req 0x%x (%p) with new pkt %s (%p)\n",
        __func__,
        pkt->req->hasPaddr() ? pkt->req->getPaddr() : 9999999,
        pkt->req,
        pkt->print(),
        pkt);
}

void
AbstractIntegrityVerifier::removeFromPacketLookup(PacketPtr pkt)
{
    assert(packetLookup.find(pkt->req) != packetLookup.end());
    // Ensure that the packet surrounding the request has not somehow changed.
    assert(packetLookup[pkt->req] == pkt);
    DPRINTF(AbstractIntegrityVerifier,
        "%s: Un-associating req 0x%x (%p) with pkt %s (%p)\n",
        __func__,
        pkt->req->hasPaddr() ? pkt->req->getPaddr() : 9999999,
        pkt->req,
        pkt->print(),
        pkt);
    packetLookup.erase(pkt->req);
    DPRINTF(AbstractIntegrityVerifier,
        "%s: packetLookup decreased. size: %d\n",
        __func__, packetLookup.size());
}

void
AbstractIntegrityVerifier::addToOutstandingMetadataRequests(
    uint64_t node,
    PacketPtr pkt
)
{
    assert(pkt != nullptr);

    // Is this node already being required by another request?
    bool batching = outstandingMetadataRequests.find(node) !=
                    outstandingMetadataRequests.end();

    // Associate (parent) node `node` with the causing request `req`.
    outstandingMetadataRequests.insert({node, pkt->req});
    DPRINTF(AbstractIntegrityVerifier,
        "%s: outstandingMetadataRequests updated. "
        "Noting %llu is needed by %s\n",
        __func__, node, pkt->print());

    if (batching) {
        DPRINTF(AbstractIntegrityVerifier,
            "%s: %d is already being requested, batching. "
            "outstandingMetadataRequests size: %d\n",
            __func__, node, outstandingMetadataRequests.size());
    } else {
        DPRINTF(AbstractIntegrityVerifier,
            "%s: outstandingMetadataRequests increased. size: %d\n",
            __func__, outstandingMetadataRequests.size());
    }
}

void
AbstractIntegrityVerifier::removeFromOutstandingMetadataRequests(
    uint64_t node,
    PacketPtr pkt
)
{
    bool removed = false;
    RequestPtr req = pkt ? pkt->req : nullptr;

    for (auto it = outstandingMetadataRequests.begin();
         it != outstandingMetadataRequests.end();) {
        if (it->first == node && it->second == req) {
            assert(!removed);
            it = outstandingMetadataRequests.erase(it);
            DPRINTF(AbstractIntegrityVerifier,
                "%s: outstandingMetadataRequests decreased. size: %d\n",
                __func__, outstandingMetadataRequests.size());
            removed = true;
        } else {
            it++;
        }
    }

    assert(removed);
}


bool
AbstractIntegrityVerifier::hasOutstandingMetadataRequest(
    PacketPtr pkt
)
{
    // If the parent node is the secure root, assume there is never an
    // outstanding request.
    if (parentNodeIsSecureRoot(pkt)) {
        return false;
    }

    // Use the packet's parent node as the default
    uint64_t parentNode = getParentNode(pkt);

    return hasOutstandingMetadataRequest(parentNode, pkt);
}


bool
AbstractIntegrityVerifier::hasOutstandingMetadataRequest(
    uint64_t node,
    PacketPtr pkt
)
{
    auto range = outstandingMetadataRequests.equal_range(node);
    for (auto it = range.first; it != range.second; ++it) {
        // Find the packet that is associated with this request.
        if (it->second == nullptr) {
            // Skip placeholders (not to be handled here).
            continue;
        }
        PacketPtr packet = packetLookup.find(it->second)->second;
        uint64_t outstandingNode = it->first;
        if (packet == pkt && outstandingNode == node) {
            return true;
        }
    }

    return false;
}


bool
AbstractIntegrityVerifier::addrInOIV(Addr addr)
{
    for (auto it : outstandingIntegrityVerification) {
        if (it->getAddr() == addr) {
            return true;
        }
    }

    return false;
}

void
AbstractIntegrityVerifier::sanityCheckPacketLookup()
{
    bool warned = false;

    // Packets shouldn't be sitting in here for an extremely long time.
    for (auto it : packetLookup) {
        RequestPtr req = it.first;
        PacketPtr pkt = it.second;
        if (curTick() - req->time() > Tick(500000000)) {
            warn("Request for 0x%x (%p), declared at tick %llu and "
                 "associated with pkt %s (%p), has been in packetLookup for "
                 "too long. Investigate further.",
                 req->getPaddr(), req, req->time(),
                 pkt->print(), pkt);
            warned = true;
        }
    }

    // Show other stats
    if (warned) {
        warn("packetLookup size: %d", packetLookup.size());
        warn("arrivalTime size: %d", arrivalTime.size());
        warn("outstandingMetadataRequests: %d",
            outstandingMetadataRequests.size());
        warn("outstandingMetadataEvictions: %d",
            outstandingMetadataEvictions.size());
        warn("outstandingIntegrityVerification: %d",
            outstandingIntegrityVerification.size());
    }
}


AbstractIntegrityVerifier::IntegrityVerifierStats::IntegrityVerifierStats(
    AbstractIntegrityVerifier *parent
) : statistics::Group(parent, "integrity_verifier"),
    parent(parent),

    ADD_STAT(memoryFootprint, statistics::units::Byte::get(),
            "Sum of data regions accessed"),
    ADD_STAT(dataUsedDram, statistics::units::Byte::get(),
            "Sum of DRAM data regions accessed"),
    ADD_STAT(dataUsedDramOs, statistics::units::Byte::get(),
            "Sum of DRAM application data regions accessed"),
    ADD_STAT(dataUsedDramIntegrity, statistics::units::Byte::get(),
            "Sum of DRAM integrity data regions accessed"),
    ADD_STAT(dataUsedOs, statistics::units::Byte::get(),
            "Sum of application data regions accessed"),
    ADD_STAT(dataUsedIntegrity, statistics::units::Byte::get(),
            "Sum of integrity data regions accessed"),

    ADD_STAT(requestsHandled, statistics::units::Count::get(),
            "Total number of requests handled"),
    ADD_STAT(bytesHandled, statistics::units::Byte::get(),
            "Total number of bytes handled for requests"),
    ADD_STAT(metadataReqHandled, statistics::units::Count::get(),
            "Total number of metadata requests handled"),
    ADD_STAT(metadataBytesHandled, statistics::units::Byte::get(),
            "Total number of bytes handled for metadata requests"),
    ADD_STAT(dataReqHandled, statistics::units::Count::get(),
            "Total number of data requests handled"),
    ADD_STAT(dataBytesHandled, statistics::units::Byte::get(),
            "Total number of bytes handled for data requests"),

    ADD_STAT(reqHandledDram, statistics::units::Count::get(),
            "Total number of requests to memory in DRAM"),
    ADD_STAT(reqHandledDramOs, statistics::units::Count::get(),
            "Total number of requests to (non-integrity) memory in DRAM"),
    ADD_STAT(reqHandledDramIntegrity, statistics::units::Count::get(),
            "Total number of requests to integrity memory in DRAM"),

    ADD_STAT(bytesHandledDram, statistics::units::Byte::get(),
            "Total number of bytes to memory in DRAM"),
    ADD_STAT(bytesHandledDramOs, statistics::units::Byte::get(),
            "Total number of bytes to (non-integrity) memory in DRAM"),
    ADD_STAT(bytesHandledDramIntegrity, statistics::units::Byte::get(),
            "Total number of bytes to integrity memory in DRAM"),

    ADD_STAT(totalRequestingTime, statistics::units::Tick::get(),
            "Total amount of time where a request is out then in"),
    ADD_STAT(totalMetadataReqTime, statistics::units::Tick::get(),
            "Total amount of time where a metadata request is out then in"),
    ADD_STAT(totalDataReqTime, statistics::units::Tick::get(),
            "Total amount of time where a data request is out then in"),

    ADD_STAT(totalReqTimeDram, statistics::units::Tick::get(),
            "Total amount of time where a data request is out then in, "
            "for memory in DRAM"),
    ADD_STAT(totalReqTimeDramOs, statistics::units::Tick::get(),
            "Total amount of time where a data request is out then in, "
            "for (non-integrity) memory in DRAM"),
    ADD_STAT(totalReqTimeDramIntegrity, statistics::units::Tick::get(),
            "Total amount of time where a data request is out then in, "
            "for integrity memory in DRAM"),

    ADD_STAT(avgReqLatency, statistics::units::Tick::get(),
            "Average request latency from leaving to entering "
            "IntegrityVerifier"),
    ADD_STAT(avgMetadataReqLatency, statistics::units::Tick::get(),
            "Average metadata request latency from leaving to entering "
            "IntegrityVerifier"),
    ADD_STAT(avgDataReqLatency, statistics::units::Tick::get(),
            "Average data request latency from leaving to entering "
            "IntegrityVerifier"),

    ADD_STAT(avgReqTimeDram, statistics::units::Tick::get(),
            "Average data request latency from leaving to entering "
            "IntegrityVerifier, for memory in DRAM"),
    ADD_STAT(avgReqTimeDramOs, statistics::units::Tick::get(),
            "Average data request latency from leaving to entering "
            "IntegrityVerifier, for (non-integrity) memory in DRAM"),
    ADD_STAT(avgReqTimeDramIntegrity, statistics::units::Tick::get(),
            "Average data request latency from leaving to entering "
            "IntegrityVerifier, for integrity memory in DRAM")
{
    avgReqLatency = totalRequestingTime / requestsHandled;
    avgMetadataReqLatency = totalMetadataReqTime / metadataReqHandled;
    avgDataReqLatency = totalDataReqTime / dataReqHandled;

    avgReqTimeDram = totalReqTimeDram / reqHandledDram;
    avgReqTimeDramOs = totalReqTimeDramOs / reqHandledDramOs;
    avgReqTimeDramIntegrity =
        totalReqTimeDramIntegrity / reqHandledDramIntegrity;
}

void
AbstractIntegrityVerifier::IntegrityVerifierStats::preDumpStats()
{
    DPRINTF(AbstractIntegrityVerifier,
        "Computing stats due to a dump callback\n");

    statistics::Group::preDumpStats();

    // TODO Hardcoded cache line size
    Addr cacheLineSize = 64;

    memoryFootprint = accessedCacheLines.size() * cacheLineSize;

    // Compute total amount of data used in all memory regions.

    dataUsedDram = 0;
    dataUsedDramOs = 0;
    dataUsedDramIntegrity = 0;
    dataUsedOs = 0;
    dataUsedIntegrity = 0;

    for (auto line : accessedCacheLines) {
        assert(rangeListContains(parent->dramFullRanges, line));
        dataUsedDram += cacheLineSize;

        if (rangeListContains(parent->dramOsRanges, line)) {
            dataUsedDramOs += cacheLineSize;
            dataUsedOs += cacheLineSize;
        } else {
            assert(rangeListContains(parent->dramIntegrityRanges, line));
            dataUsedDramIntegrity += cacheLineSize;
            dataUsedIntegrity += cacheLineSize;
        }
    }
}


std::string
AbstractIntegrityVerifier::printArrivalTime()
{
    std::ostringstream str;

    ccprintf(str, "arrivalTime size: %d\n", arrivalTime.size());
    for (auto it : arrivalTime) {
        RequestPtr req = it.first;
        Tick arrival = it.second;

        auto search = packetLookup.find(req);
        if (search != packetLookup.end()) {
            // We have the original packet for this.
            PacketPtr pkt = search->second;
            ccprintf(str, "pkt %s (%p)\t%llu\n", pkt->print(), pkt, arrival);
        } else {
            // No original packet.
            ccprintf(str, "req 0x%x (%p)\t%llu\n",
                req->hasPaddr() ? req->getPaddr() : 999999,
                req,
                arrival);
        }
    }

    return str.str();
}


void
AbstractIntegrityVerifier::fullDebugOutput()
{
    cprintf("==============================\n");
    cprintf("INTEGRITY VERIFIER:\n");
    cprintf("outstandingIntegrityVerification (size %d):\n",
        outstandingIntegrityVerification.size());
    for (auto it : outstandingIntegrityVerification) {
        cprintf("- %s (%p)\n", it->print(), it);
    }

    cprintf("outstandingIntegrityHashes (size %d):\n",
        outstandingIntegrityHashes.size());
    for (auto it : outstandingIntegrityHashes) {
        if (packetLookup.find(it) != packetLookup.end()) {
            PacketPtr pkt = packetLookup[it];
            cprintf("- %s (%p)  <-- req for 0x%x (%p)\n",
                pkt->print(), pkt, it->getPaddr(), it);
        } else {
            cprintf("- (unknown packet) <-- req for 0x%x (%p)\n",
                it->getPaddr(), it);
        }
    }

    cprintf("outstandingXors (size %d):\n",
        outstandingXors.size());
    for (auto it : outstandingXors) {
        if (packetLookup.find(it) != packetLookup.end()) {
            PacketPtr pkt = packetLookup[it];
            cprintf("- %s (%p)  <-- req for 0x%x (%p)\n",
                pkt->print(), pkt, it->getPaddr(), it);
        } else {
            cprintf("- (unknown packet) <-- req for 0x%x (%p)\n",
                it->getPaddr(), it);
        }
    }

    cprintf("outstandingMetadataRequests (size %d):\n",
        outstandingMetadataRequests.size());
    for (auto it : outstandingMetadataRequests) {
        if (packetLookup.find(it.second) != packetLookup.end()) {
            PacketPtr pkt = packetLookup[it.second];
            cprintf("- Node %llu requested by pkt %s (%p)   "
                "(req for 0x%x, allocated @ %p)\n",
                it.first, pkt->print(), pkt,
                it.second->getPaddr(), it.second);
        } else if (it.second == nullptr) {
            cprintf("- Node %llu requested by an eviction\n",
                it.first);
        } else {
            cprintf("- Node %llu requested by (unknown packet)   "
                "(req for 0x%x allocated @ %p)\n",
                it.first,
                it.second->getPaddr(), it.second);
        }

    }

    cprintf("outstandingMetadataEvictions (size %d):\n",
        outstandingMetadataEvictions.size());
    for (auto it : outstandingMetadataEvictions) {
        if (packetLookup.find(it.second.second) != packetLookup.end()) {
            PacketPtr pkt = packetLookup[it.second.second];
            cprintf("- Node %llu, parent of to-evict child %llu to be "
                "replaced by %s\n",
                it.first, it.second.first,
                pkt->print());
        } else {
            cprintf("- Node %llu, parent of to-evict child %llu to be "
                "replaced by (unknown - req for 0x%x, allocated @ %p)\n",
                it.first, it.second.first,
                it.second.second->getPaddr(), it.second.second);
        }
    }

    cprintf("responseReady (size %d):\n",
        responseReady.size());
    for (auto it : responseReady) {
        if (packetLookup.find(it) != packetLookup.end()) {
            PacketPtr pkt = packetLookup[it];
            cprintf("- %s (%p)  <-- req for 0x%x (%p)\n",
                pkt->print(), pkt, it->getPaddr(), it);
        } else {
            cprintf("- (unknown packet) <-- req for 0x%x (%p)\n",
                it->getPaddr(), it);
        }
    }

    cprintf("responseQueue (size %d):\n", responseQueue.size());
    cprintf("   front: ");
    if (!responseQueue.empty()) {
        auto front = responseQueue.front();

        if (packetLookup.find(front) != packetLookup.end()) {
            PacketPtr pkt = packetLookup[front];
            cprintf("%s (%p)  <-- req for 0x%x (%p)\n",
                pkt->print(), pkt, front->getPaddr(), front);
        } else {
            cprintf("(unknown packet) <-- req for 0x%x (%p)\n",
                front->getPaddr(), front);
        }
    }
    else {
        cprintf("(empty)\n");
    }

    cprintf("requestReady (size %d):\n",
        requestReady.size());
    for (auto it : requestReady) {
        if (packetLookup.find(it) != packetLookup.end()) {
            PacketPtr pkt = packetLookup[it];
            cprintf("- %s (%p)  <-- req for 0x%x (%p)\n",
                pkt->print(), pkt, it->getPaddr(), it);
        } else {
            cprintf("- (unknown packet) <-- req for 0x%x (%p)\n",
                it->getPaddr(), it);
        }
    }

    cprintf("requestQueue (size %d):\n", requestQueue.size());
    cprintf("   front: ");
    if (!requestQueue.empty()) {
        auto front = requestQueue.front();

        if (packetLookup.find(front) != packetLookup.end()) {
            PacketPtr pkt = packetLookup[front];
            cprintf("%s (%p)  <-- req for 0x%x (%p)\n",
                pkt->print(), pkt, front->getPaddr(), front);
        } else {
            cprintf("(unknown packet) <-- req for 0x%x (%p)\n",
                front->getPaddr(), front);
        }
    }
    else {
        cprintf("(empty)\n");
    }

    cprintf("metadataRequestQueue (size %d):\n", metadataRequestQueue.size());
    cprintf("   front: ");
    if (!metadataRequestQueue.empty()) {
        auto front = metadataRequestQueue.front();

        if (packetLookup.find(front) != packetLookup.end()) {
            PacketPtr pkt = packetLookup[front];
            cprintf("%s (%p)  <-- req for 0x%x (%p)\n",
                pkt->print(), pkt, front->getPaddr(), front);
        } else {
            cprintf("(unknown packet) <-- req for 0x%x (%p)\n",
                front->getPaddr(), front);
        }
    }
    else {
        cprintf("(empty)\n");
    }

    cprintf("arrivalTime (size %d):\n", arrivalTime.size());
    cprintf("%s", printArrivalTime());

    cprintf("packetLookup (size %d):\n", packetLookup.size());
    for (auto it : packetLookup) {
        cprintf("- req for 0x%x (%p) --> %s (%p)\n",
            it.first->getPaddr(), it.first,
            it.second->print(), it.second);
    }

    cprintf("==============================\n");
}



IntegrityVerifier::IntegrityVerifier(const Params &p)
    : AbstractIntegrityVerifier(p),
      readReqDelay(p.read_req),
      readRespDelay(p.read_resp),
      writeReqDelay(p.write_req),
      writeRespDelay(p.write_resp)
{
}

Tick
IntegrityVerifier::delayReq(PacketPtr pkt)
{
    if (pkt->isRead()) {
        return readReqDelay;
    } else if (pkt->isWrite()) {
        return writeReqDelay;
    } else {
        return 0;
    }
}

Tick
IntegrityVerifier::delayResp(PacketPtr pkt)
{
    if (pkt->isRead()) {
        return readRespDelay;
    } else if (pkt->isWrite()) {
        return writeRespDelay;
    } else {
        return 0;
    }
}

} // namespace gem5
