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
      requestPort(name() + "-mem_side_port", *this),
      responsePort(name() + "-cpu_side_port", *this),
      reqQueue(*this, requestPort),
      respQueue(*this, responsePort),
      snoopRespQueue(*this, requestPort),
      integrityTree(TimingTree(4, system->memSize())),
      metadataCache(SimpleMetadataCache(300000))
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
    if (pkt->isRead() && pkt->getAddr() < parent.system->memSize()) {
        return parent.handleResp(pkt);
    }

    // technically the packet only reaches us after the header delay,
    // and typically we also need to deserialise any payload
    const Tick receive_delay = pkt->headerDelay + pkt->payloadDelay;
    pkt->headerDelay = pkt->payloadDelay = 0;

    const Tick when = curTick() + parent.delayResp(pkt) + receive_delay;

    parent.responsePort.schedTimingResp(pkt, when);

    return true;
}

bool
AbstractIntegrityVerifier::handleResp(PacketPtr pkt)
{
    DPRINTF(AbstractIntegrityVerifier,
            "%s: Handling verification of packet %s\n",
            __func__, pkt->print());

    // TODO This will start with just basic integrity. No encryption. Just
    // integrity/cryptographic hashing. The data is thus already decrypted.
    // We just need to verify that this data is what we expect it to be.

    // Kick off hashing. Add to a pending hashing list. Schedule an event
    // when the hashing completes. Keep in mind we are essentially holding
    // hostage the memory response until all verification is complete.
    // TODO For now, we will assume there will be unlimited space in the
    // pending hashing list. A response packet should never bounce back
    // and clog up for now. However, in the future, there should be a
    // capacity check here and ask packets to try again later.
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
    packetLookup.emplace(pkt->req, pkt);


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

    // Add to outstanding metadata requests
    outstandingMetadataRequests.insert({parentNode, pkt->req});

    // TODO Set the packet delay

    // Submit the packet to the memory controller.
    DPRINTF(AbstractIntegrityVerifier, "%s: Sending metadata req %s\n",
        __func__, metadataRequestPkt->print());
    requestPort.schedTimingReq(metadataRequestPkt, curTick() + Cycles(1));

    // TODO Update stats

    // We will hold on to the original response packet until the time comes to
    // forward this to the CPU.
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
AbstractIntegrityVerifier::parentNodeAvailable(PacketPtr pkt)
{
    if (parentNodeIsSecureRoot(pkt)) {
        // The parent of this node is the secure root.
        return true;
    }

    auto parentNode = getParentNode(pkt);
    return (metadataCache.contains(parentNode));
}


void
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
        return;
    } else if (!parentNodeAvailable(pkt)) {
        // The parent node is not yet available. We are not ready to verify.
        DPRINTF(AbstractIntegrityVerifier, "%s: Not ready to verify pkt %s, "
            "parent unavailable\n",
            __func__, pkt->print());
        return;
    }

    // We are now ready to verify.
    // Assume that the verification was successful, and effectively instant.
    outstandingIntegrityVerification.erase(pkt);
    packetLookup.erase(pkt->req);
    DPRINTF(AbstractIntegrityVerifier,
        "%s: Verified pkt %s\n", __func__, pkt->print());

    if (pkt->isMetadataRequest()) {
        // Add this to the cache. We are done here.
        bool inserted = metadataCache.insert(pkt->getMetadataNode());
        // TODO Handle eviction.
        assert(inserted);

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
            if (it->second == pkt->req) {
                // Skip the request we're already in the middle of doing.
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
    } else if (pkt->isRead()) {
        // Handling finishing integrity verification for read responses.
        // This means we can now forward the data to the CPU to be used.
        DPRINTF(AbstractIntegrityVerifier, "%s: Sending back pkt %s to CPU\n",
            __func__, pkt->print());
        // This packet can now be properly returned up to the CPU to complete.
        Tick when = curTick() + Cycles(1);
        responsePort.schedTimingResp(pkt, when);
    } else if (pkt->isWrite()) {
        // Handling finishing integrity verification for write requests.
        // This means we can now forward the data to memory for storage.
        DPRINTF(AbstractIntegrityVerifier, "%s: Sending pkt %s to memory\n",
            __func__, pkt->print());
        // This packet can now be properly forwarded to memory to complete.
        Tick when = curTick() + Cycles(1);
        requestPort.schedTimingReq(pkt, when);
    }
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
    if (pkt->isWrite() && pkt->getAddr() < parent.system->memSize()) {
        return parent.handleReq(pkt);
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


bool
AbstractIntegrityVerifier::handleReq(PacketPtr pkt)
{
    DPRINTF(AbstractIntegrityVerifier,
            "%s: Handling verification of packet %s\n",
            __func__, pkt->print());

    // We are getting a writeback from LLC. Integrity metadata (at least in
    // the cache) should be updated for this data's parent node first before
    // being allowed to be written to memory.

    // Hash the data from this line. Schedule a delay.
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
    packetLookup.emplace(pkt->req, pkt);

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

    // Add to outstanding metadata requests
    outstandingMetadataRequests.insert({parentNode, pkt->req});

    // TODO Set the packet delay

    // Submit the packet to the memory controller.
    DPRINTF(AbstractIntegrityVerifier, "%s: Sending metadata req %s\n",
        __func__, metadataRequestPkt->print());
    requestPort.schedTimingReq(metadataRequestPkt, curTick() + Cycles(1));

    // TODO Update stats

    // We will hold on to the original request packet until the time comes to
    // forward this to memory.
    return true;
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
