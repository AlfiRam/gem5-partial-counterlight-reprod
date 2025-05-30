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

#include "debug/AbstractIntegrityVerifier.hh"

namespace gem5
{

AbstractIntegrityVerifier::AbstractIntegrityVerifier(
    const AbstractIntegrityVerifierParams &p
)
    : ClockedObject(p),
      system(p.system),
      metadataCacheSize(p.metadata_cache_size),
      requestPort(name() + "-mem_side_port", *this),
      responsePort(name() + "-cpu_side_port", *this),
      reqQueue(*this, requestPort),
      respQueue(*this, responsePort),
      snoopRespQueue(*this, requestPort),
      integrityTree(TimingTree(4, system->memSize())),
      metadataCache(SimpleMetadataCache(metadataCacheSize)),
      hasRequestorId(false),
      _requestorId(0)
{
}

void
AbstractIntegrityVerifier::init()
{
    if (!responsePort.isConnected() || !requestPort.isConnected())
        fatal("Integrity verifier is not connected on both sides.\n");
}


Port &
AbstractIntegrityVerifier::getPort(const std::string &if_name, PortID idx)
{
    if (if_name == "mem_side_port") {
        return requestPort;
    } else if (if_name == "cpu_side_port") {
        return responsePort;
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

AbstractIntegrityVerifier::RequestPort::RequestPort(
    const std::string &_name, AbstractIntegrityVerifier &_parent)
    : QueuedRequestPort(_name, _parent.reqQueue, _parent.snoopRespQueue),
      parent(_parent)
{
}


bool
AbstractIntegrityVerifier::RequestPort::recvTimingResp(PacketPtr pkt)
{
    DPRINTF(AbstractIntegrityVerifier, "%s: Recv resp %s\n",
        __func__, pkt->print());

    // Read data must be verified first before it can be used.
    // Don't do anything special for memory requests that are not actually
    // for memory.
    if (pkt->getAddr() < parent.system->memSize()) {
        if (pkt->isRead()) {
            return parent.handlePacket(pkt);
        }
        else if (pkt->isWrite()) {
            // Mark write response packet as returned.
            assert(parent.packetLookup.find(pkt->req) !=
                   parent.packetLookup.end());
            parent.packetLookup.erase(pkt->req);
            parent.markReqEnd(pkt);
        }
        // If this is something else (e.g., UpgradeResp), drop to the default
        // behavior below.
    }

    // technically the packet only reaches us after the header delay,
    // and typically we also need to deserialise any payload
    const Tick receive_delay = pkt->headerDelay + pkt->payloadDelay;
    pkt->headerDelay = pkt->payloadDelay = 0;

    assert(parent.packetLookup.find(pkt->req) == parent.packetLookup.end());
    assert(!pkt->isMetadataRequest());

    const Tick when = curTick() + parent.delayResp(pkt) + receive_delay;

    parent.responsePort.schedTimingResp(pkt, when);

    return true;
}

PacketPtr
AbstractIntegrityVerifier::generateMetadataRequest(PacketPtr pkt)
{
    size_t parentNode = getParentNode(pkt);

    // Create the metadata request and packet.
    RequestPtr req = std::make_shared<Request>(
        pkt->getAddr(),
        64, // Size
        0, // No flags
        pkt->requestorId()
    );
    DPRINTF(AbstractIntegrityVerifier,
        "%s: Allocated request %p\n",
        __func__, req);
    PacketPtr metadataRequestPkt = Packet::createRead(req);
    // Set the flag that this is a metadata request.
    metadataRequestPkt->setMetadataRequest();

    // Indicate the integrity tree node that will be accessed.
    metadataRequestPkt->setMetadataNode(parentNode);

    return metadataRequestPkt;
}

PacketPtr
AbstractIntegrityVerifier::generateMetadataRequest(size_t node)
{
    // Create the metadata request and packet.
    RequestPtr req = std::make_shared<Request>(
        integrityTree.blockIndexToAddress(node),
        64, // Size
        0, // No flags
        _requestorId
    );
    DPRINTF(AbstractIntegrityVerifier,
        "%s: Allocated request %p\n",
        __func__, req);
    PacketPtr metadataRequestPkt = Packet::createRead(req);
    // Set the flag that this is a metadata request.
    metadataRequestPkt->setMetadataRequest();

    // Indicate the integrity tree node that will be accessed.
    metadataRequestPkt->setMetadataNode(node);

    return metadataRequestPkt;
}

bool
AbstractIntegrityVerifier::handlePacket(PacketPtr pkt)
{
    DPRINTF(AbstractIntegrityVerifier,
            "%s: Handling verification of packet %s\n",
            __func__, pkt->print());

    // We aren't ready for this packet. Don't accept it until the parent node
    // is fully evicted.
    if (parentNodeIsPendingEviction(pkt)) {
        DPRINTF(AbstractIntegrityVerifier,
            "%s: Rejecting %s due to parent pending eviction.\n",
            __func__, pkt->print());
        return false;
    }

    if (pkt->isResponse()) {
        markReqEnd(pkt);
    }

    // Save a valid requestor ID internally just in case it is needed.
    if (!hasRequestorId) {
        _requestorId = pkt->requestorId();
        hasRequestorId = true;
    }

    // We are either getting a read response from memory or a writeback request
    // from the LLC. Integrity metadata (at least in the cache) should be
    // updated for this data's parent node first before being allowed to be
    // sent to the CPU (for read responses) or to be written to memory (for
    // write requests).

    // TODO This will start with just basic integrity. No encryption. Just
    // integrity/cryptographic hashing. The data is thus already decrypted.
    // We just need to verify that this data is what we expect it to be.

    // Kick off hashing. Add to a pending hashing list. Schedule an event
    // when the hashing completes. Keep in mind we are essentially holding
    // hostage the memory packet until all verification is complete.
    // TODO For now, we will assume there will be unlimited space in the
    // pending hashing list. A packet should never bounce back and clog up for
    // now. However, in the future, there should be a capacity check here and
    // ask packets to try again later.
    DPRINTF(AbstractIntegrityVerifier, "%s: Scheduling hash for pkt %s\n",
        __func__, pkt->print());
    schedule(
        new HashCompletionEvent(this, pkt),
        curTick() + integrityHashingLatency
    );
    // This packet should not already be in the process of being verified.
    assert(outstandingIntegrityHashes.find(pkt->req) ==
            outstandingIntegrityHashes.end());
    assert(outstandingIntegrityVerification.find(pkt) ==
            outstandingIntegrityVerification.end());
    outstandingIntegrityHashes.insert(pkt->req);
    outstandingIntegrityVerification.insert(pkt);
    if (pkt->isRead() && pkt->isResponse()) {
        // A read response should already be put in after being requested.
        assert(packetLookup.find(pkt->req) != packetLookup.end());
    } else {
        assert(packetLookup.find(pkt->req) == packetLookup.end());
        packetLookup.emplace(pkt->req, pkt);
        DPRINTF(AbstractIntegrityVerifier,
            "%s: Associating req 0x%x (%p) with pkt %s (%p)\n",
            __func__,
            pkt->req->hasPaddr() ? pkt->req->getPaddr() : 9999999,
            pkt->req,
            pkt->print(),
            pkt);
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
    }

    if (parentNodeAvailable(pkt)) {
        // If the parent is the secure root, or the parent node exists in
        // the metadata cache, we are just waiting for the hashing to
        // complete. We are done here.

        // Account for the request being complete.
        DPRINTF(AbstractIntegrityVerifier, "%s: pkt %s has parent available\n",
            __func__, pkt->print());
        completeIntegrityVerification(pkt);

        return true;
    }

    // If there is already an outstanding request for this parent node, we will
    // batch this with the existing request.
    if (outstandingMetadataRequests.find(parentNode) !=
        outstandingMetadataRequests.end()) {
        DPRINTF(AbstractIntegrityVerifier,
            "%s: %d is already being requested, batching\n",
            __func__, parentNode);
        outstandingMetadataRequests.insert({parentNode, pkt->req});

        return true;
    }

    // A request has not yet been sent. We will craft a request packet for
    // metadata to memory to get the parent node. Then we schedule the
    // request.

    PacketPtr metadataRequestPkt = generateMetadataRequest(pkt);

    // Add to outstanding metadata requests
    assert(outstandingMetadataRequests.find(parentNode) ==
           outstandingMetadataRequests.end());
    outstandingMetadataRequests.insert({parentNode, pkt->req});

    // TODO Set the packet delay

    // Submit the packet to the memory controller.
    sendReqToMem(metadataRequestPkt);

    // TODO Update stats

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
    completeIntegrityVerification(pkt);
}


size_t
AbstractIntegrityVerifier::getParentNode(PacketPtr pkt)
{
    if (pkt->isMetadataRequest()) {
        // This function should not be called if this is already the root
        // metadata node.
        assert(pkt->getMetadataNode() != 0);

        return integrityTree.parentBlockIndex(pkt->getMetadataNode());
    } else {
        return integrityTree.addressToBlockIndex(pkt->getAddr());
    }
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
    if (!metadataCache.containsPendingOkay(parentNode)) {
        return false;
    }
    auto search = metadataCache.find(parentNode);

    return (search.second.pending_eviction);
}


bool
AbstractIntegrityVerifier::parentNodeAvailable(PacketPtr pkt)
{
    if (parentNodeIsSecureRoot(pkt)) {
        // The parent of this node is the secure root.
        return true;
    }

    auto parentNode = getParentNode(pkt);
    return (metadataCache.contains(parentNode));
}


bool
AbstractIntegrityVerifier::completeIntegrityVerification(PacketPtr pkt)
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
    } else if (!parentNodeAvailable(pkt)) {
        // The parent node is not yet available. We are not ready to verify.
        DPRINTF(AbstractIntegrityVerifier, "%s: Not ready to verify pkt %s, "
            "parent unavailable\n",
            __func__, pkt->print());
        return false;
    }

    // We are now ready to verify.
    // Assume that the verification was successful, and effectively instant.

    // Metadata requests have more logic involved so this is handled
    // separately.
    if (pkt->isMetadataRequest()) {
        return handleMetadataAddition(pkt);
    }

    // The rest of this is for handling data packets.
    assert(!pkt->isMetadataRequest());

    // Officially consider this verified.
    outstandingIntegrityVerification.erase(pkt);
    assert(packetLookup.find(pkt->req) != packetLookup.end());
    packetLookup.erase(pkt->req);
    DPRINTF(AbstractIntegrityVerifier,
        "%s: Verified pkt %s\n", __func__, pkt->print());

    if (pkt->isRead()) {
        // Handling finishing integrity verification for read responses.
        // This means we can now forward the data to the CPU to be used.
        DPRINTF(AbstractIntegrityVerifier, "%s: Sending back pkt %s to CPU\n",
            __func__, pkt->print());
        assert(!pkt->isMetadataRequest());
        assert(packetLookup.find(pkt->req) == packetLookup.end());
        // This packet can now be properly returned up to the CPU to complete.
        Tick when = curTick() + Cycles(1);
        responsePort.schedTimingResp(pkt, when);
    } else if (pkt->isWrite()) {
        // Handling finishing integrity verification for write requests.
        // This means we can now update the metadata cache and forward the data
        // to memory for storage.
        auto parentNode = getParentNode(pkt);
        metadataCache.modify(parentNode);
        DPRINTF(AbstractIntegrityVerifier,
            "%s: Modifying cache line %lu in metadata cache\n",
            __func__, parentNode);
        // This packet can now be properly forwarded to memory to complete.
        sendReqToMem(pkt);
    }

    return true;
}


bool
AbstractIntegrityVerifier::handleMetadataAddition(PacketPtr pkt)
{
    // Attempt to add the metadata to the cache.
    bool inserted = metadataCache.insert(pkt->getMetadataNode());
    if (!inserted) {
        // We must evict something to make room for more.
        DPRINTF(AbstractIntegrityVerifier,
            "%s: %s could not be inserted into the cache. "
            "Conducting eviction.\n",
            __func__, pkt->print());

        auto evictedData = metadataCache.evict(0);
        if (evictedData.second.pending_eviction) {
            DPRINTF(AbstractIntegrityVerifier,
                "%s: %lld was selected to evict but is dirty.\n",
                __func__, evictedData.first);
            // If this line is marked as pending eviction, we must first
            // make sure its parent is available in the metadata cache.
            auto evictParent = integrityTree.parentBlockIndex(
                                                evictedData.first);
            if (!metadataCache.contains(evictParent)) {
                DPRINTF(AbstractIntegrityVerifier,
                    "%s: The parent of %lld, %lld, is not cached.\n",
                    __func__, evictedData.first, evictParent);
                // The parent of the cache line being evicted is not
                // cached. We will request this first and come back to
                // evicting once the parent is in the cache.

                // If there is already an outstanding request for this
                // parent node, we will batch this with the existing
                // request.
                if (outstandingMetadataRequests.find(evictParent) !=
                    outstandingMetadataRequests.end()) {
                    DPRINTF(AbstractIntegrityVerifier,
                        "%s: %d is already being requested, batching\n",
                        __func__, evictParent);
                } else {
                    DPRINTF(AbstractIntegrityVerifier,
                        "%s: %d is not yet requested\n",
                        __func__, evictParent);
                    // Request does not already exist. Create and send out.
                    PacketPtr metadataReq = generateMetadataRequest(
                                        evictParent);
                    sendReqToMem(metadataReq);
                }

                outstandingMetadataRequests.insert(
                                    {evictParent, nullptr});
                outstandingMetadataEvictions.insert(
                    {evictParent, {evictedData.first, pkt->req}});

                // Stop here, and we will call this function again later once
                // the eviction is complete and we have a new free space.
                return false;
            }
            DPRINTF(AbstractIntegrityVerifier,
                "%s: The parent of %lld is cached. Evicting %lld.\n",
                __func__, evictParent, evictedData.first);
            // The parent is in the cache, so we can safely evict (writeback).
            metadataCache.finishEvict(evictedData.first);
            // TODO Create writeback packet
        }
        DPRINTF(AbstractIntegrityVerifier,
            "%s: Evicted %lu from metadata cache.\n",
            __func__, evictedData.first);
        inserted = metadataCache.insert(pkt->getMetadataNode());
    }
    assert(inserted);

    // Now that the data is cached, we can officially call this verified and
    // done.
    outstandingIntegrityVerification.erase(pkt);
    assert(packetLookup.find(pkt->req) != packetLookup.end());
    packetLookup.erase(pkt->req);
    DPRINTF(AbstractIntegrityVerifier,
        "%s: Verified pkt %s\n", __func__, pkt->print());

    // Check to see if there were evictions that were waiting for this (parent)
    // metadata.
    DPRINTF(AbstractIntegrityVerifier,
        "%s: Triggering evictions that were waiting for %s to verify\n",
        __func__, pkt->print());
    auto evictions = outstandingMetadataEvictions.equal_range(
                                                pkt->getMetadataNode());
    std::vector<std::pair<uint64_t, PacketPtr>> toEvict;
    for (auto it = evictions.first; it != evictions.second; ++it) {
        uint64_t evicted_node_id = it->second.first;
        PacketPtr original_req = packetLookup.find(it->second.second)->second;
        toEvict.push_back({evicted_node_id, original_req});
    }

    for (auto e : toEvict) {
        DPRINTF(AbstractIntegrityVerifier,
            "%s: %s is verified. %llu can now be evicted for %s.\n",
            __func__, pkt->print(), e.first, e.second->print());

        metadataCache.finishEvict(e.first);
        bool result = completeIntegrityVerification(e.second);

        // Resend requests that were waiting for this eviction.
        rescheduleReqFromEviction(e.first);
    }
    outstandingMetadataEvictions.erase(pkt->getMetadataNode());


    // We must handle here that if a metadata request is verified, we can
    // trigger to verify the node(s) below this one that are still waiting.
    // Attempt to verify any applicable outstanding verifications.
    DPRINTF(AbstractIntegrityVerifier,
        "%s: Triggering requests that were waiting for %s to verify\n",
        __func__, pkt->print());
    auto range = outstandingMetadataRequests.equal_range(
                                                pkt->getMetadataNode());
    std::vector<PacketPtr> toVerify;
    for (auto it = range.first; it != range.second; ++it) {
        // Find the packet that is associated with this request.
        if (it->second == pkt->req || it->second == nullptr) {
            // Skip the request we're already in the middle of doing,
            // or placeholders (not to be handled here).
            continue;
        }
        PacketPtr packet = packetLookup.find(it->second)->second;
        toVerify.push_back(packet);
    }

    for (auto packet : toVerify) {
        DPRINTF(AbstractIntegrityVerifier,
            "%s: %s is verified. %s is now ready for verification.\n",
            __func__, pkt->print(), packet->print());
        completeIntegrityVerification(packet);
    }

    // Consider this metadata request now received.
    outstandingMetadataRequests.erase(pkt->getMetadataNode());

    delete pkt;

    return true;
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
    // Under no means should we be getting a metadata request.
    // They are only sent from here.
    assert(!pkt->isMetadataRequest());

    // We want to just bypass immediately if this is an express snoop.
    if (pkt->isExpressSnoop()) {
        parent.requestPort.sendTimingReq(pkt);
        return true;
    }

    DPRINTF(AbstractIntegrityVerifier, "%s: Recv req %s\n",
        __func__, pkt->print());

    // Read data must be verified first before it can be used.
    // Don't do anything special for memory requests that are not actually
    // for memory.
    if (pkt->getAddr() < parent.system->memSize()) {
        if (pkt->isWrite()) {
            return parent.handlePacket(pkt);
        }
        else if (pkt->isRead()) {
            // Forward read request.
            parent.sendReqToMem(pkt);
            return true;
        }
        // If this is something else (e.g., CleanEvict), drop to the default
        // behavior below.
    }

    // technically the packet only reaches us after the header
    // delay, and typically we also need to deserialise any
    // payload
    Tick receive_delay = pkt->headerDelay + pkt->payloadDelay;
    pkt->headerDelay = pkt->payloadDelay = 0;

    const Tick when = curTick() + parent.delayReq(pkt) + receive_delay;

    parent.requestPort.schedTimingReq(pkt, when);

    return true;
}


void
AbstractIntegrityVerifier::rescheduleReqFromEviction(uint64_t data)
{
    // TODO stub
}


void
AbstractIntegrityVerifier::sendReqToMem(PacketPtr pkt)
{
    DPRINTF(AbstractIntegrityVerifier, "%s: Scheduling req %s to memory\n",
        __func__, pkt->print());
    requestPort.schedTimingReq(pkt, curTick() + Cycles(1));

    if (!pkt->needsResponse()) {
        // Packets that aren't getting a response should not be tracked for
        // response timing.
        return;
    }

    assert(packetLookup.find(pkt->req) == packetLookup.end());
    packetLookup.emplace(pkt->req, pkt);
    DPRINTF(AbstractIntegrityVerifier,
        "%s: Associating req 0x%x (%p) with pkt %s (%p)\n",
        __func__,
        pkt->req->hasPaddr() ? pkt->req->getPaddr() : 9999999,
        pkt->req,
        pkt->print(),
        pkt);
    markReqStart(pkt);
}


void
AbstractIntegrityVerifier::markReqStart(PacketPtr pkt)
{
    assert(pkt->needsResponse());

    // This request should not already have been marked to start.
    assert(arrivalTime.find(pkt->req) == arrivalTime.end());

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

    requestsHandled++;
    totalRequestingTime += curTick() - arrivalTime[pkt->req];
    if (pkt->isMetadataRequest()) {
        metadataReqHandled++;
        totalMetadataReqTime += curTick() - arrivalTime[pkt->req];
    } else {
        dataReqHandled++;
        totalDataReqTime += curTick() - arrivalTime[pkt->req];
    }

    arrivalTime.erase(pkt->req);
    DPRINTF(AbstractIntegrityVerifier,
        "%s: arrivalTime decreased. size: %d\n",
        __func__, arrivalTime.size());
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


void
AbstractIntegrityVerifier::regStats()
{
    ClockedObject::regStats();

    requestsHandled
        .name(name() + ".requestsHandled")
        .desc("Total number of requests handled")
        .unit(statistics::units::Count::get());

    metadataReqHandled
        .name(name() + ".metadataReqHandled")
        .desc("Total number of metadata requests handled")
        .unit(statistics::units::Count::get());

    dataReqHandled
        .name(name() + ".dataReqHandled")
        .desc("Total number of data requests handled")
        .unit(statistics::units::Count::get());

    totalRequestingTime
        .name(name() + ".totalRequestingTime")
        .desc("Total amount of time where a request is out then in")
        .unit(statistics::units::Tick::get());

    totalMetadataReqTime
        .name(name() + ".totalMetadataReqTime")
        .desc("Total amount of time where a metadata request is out then in")
        .unit(statistics::units::Tick::get());

    totalDataReqTime
        .name(name() + ".totalDataReqTime")
        .desc("Total amount of time where a data request is out then in")
        .unit(statistics::units::Tick::get());

    avgReqLatency
        .name(name() + ".avgReqLatency")
        .desc("Average request latency from leaving to entering "
              "IntegrityVerifier")
        .unit(statistics::units::Tick::get());

    avgMetadataReqLatency
        .name(name() + ".avgMetadataReqLatency")
        .desc("Average metadata request latency from leaving to entering "
              "IntegrityVerifier")
        .unit(statistics::units::Tick::get());

    avgDataReqLatency
        .name(name() + ".avgDataReqLatency")
        .desc("Average data request latency from leaving to entering "
              "IntegrityVerifier")
        .unit(statistics::units::Tick::get());

    avgReqLatency = totalRequestingTime / requestsHandled;
    avgMetadataReqLatency = totalMetadataReqTime / metadataReqHandled;
    avgDataReqLatency = totalDataReqTime / dataReqHandled;
}



IntegrityVerifier::IntegrityVerifier(const IntegrityVerifierParams &p)
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
