/*
 * Copyright (c) 2018 ARM Limited
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

#ifndef __MEM_INTEGRITY_VERIFIER_HH__
#define __MEM_INTEGRITY_VERIFIER_HH__

#include "mem/cache/metadata_cache.hh"
#include "mem/mtree/timing_tree.hh"
#include "mem/qport.hh"
#include "params/AbstractIntegrityVerifier.hh"
#include "params/IntegrityVerifier.hh"
#include "sim/clocked_object.hh"
#include "sim/system.hh"

namespace gem5
{

// struct AbstractIntegrityVerifierParams;
// struct IntegrityVerifierParams;

/**
 * This abstract component provides a mechanism to perform integrity
 * verification. It can be spliced between arbitrary ports of the memory
 * system and delays packets that pass through it.
 *
 * Specialisations of this abstract class should override at least one
 * of delayReq, delayResp, deleySnoopReq, delaySnoopResp. These
 * methods receive a PacketPtr as their argument and return a delay in
 * Ticks. The base class implements an infinite buffer to hold delayed
 * packets until they are ready. The intention is to use this
 * component for rapid prototyping of other memory system components
 * that introduce a packet processing delays.
 */
class AbstractIntegrityVerifier : public ClockedObject
{

  public:
    AbstractIntegrityVerifier(const AbstractIntegrityVerifierParams &params);

    void init() override;

  protected: // Port interface
    Port &getPort(const std::string &if_name,
                  PortID idx=InvalidPortID) override;

    class RequestPort : public QueuedRequestPort
    {
      public:
        RequestPort(const std::string &_name,
          AbstractIntegrityVerifier &_parent);

      protected:
        bool recvTimingResp(PacketPtr pkt) override;

        void recvFunctionalSnoop(PacketPtr pkt) override;

        Tick recvAtomicSnoop(PacketPtr pkt) override;

        void recvTimingSnoopReq(PacketPtr pkt) override;

        void recvRangeChange() override {
            parent.responsePort.sendRangeChange();
        }

        bool isSnooping() const override {
            return parent.responsePort.isSnooping();
        }

      private:
        AbstractIntegrityVerifier& parent;
    };

    class ResponsePort : public QueuedResponsePort
    {
      public:
        ResponsePort(const std::string &_name,
          AbstractIntegrityVerifier &_parent);

      protected:
        Tick recvAtomic(PacketPtr pkt) override;
        bool recvTimingReq(PacketPtr pkt) override;
        void recvFunctional(PacketPtr pkt) override;
        bool recvTimingSnoopResp(PacketPtr pkt) override;

        AddrRangeList getAddrRanges() const override {
            return parent.requestPort.getAddrRanges();
        }

        bool tryTiming(PacketPtr pkt) override { return true; }

      private:

        AbstractIntegrityVerifier& parent;

    };

    bool trySatisfyFunctional(PacketPtr pkt);

    /**
     * Create a metadata request for the parent node of a given packet `pkt`.
     *
     * Returns the metadata request packet.
     */
    PacketPtr generateMetadataRequest(PacketPtr pkt);

    bool handleResp(PacketPtr pkt);

    bool handleReq(PacketPtr pkt);

    /**
     * Called when hash generation for a (read) response packet is received.
     */
    void completeIntegrityHash(PacketPtr pkt);

    /**
     * Get the parent integrity node ID associated with a packet.
     */
    size_t getParentNode(PacketPtr pkt);

    bool parentNodeIsSecureRoot(PacketPtr pkt);

    bool parentNodeAvailable(PacketPtr pkt);

    /**
     * Called when a request should attempt to be verified, and the original
     * data request packet can be properly forwarded back to the CPU side if
     * the leaf was verified.
     */
    void completeIntegrityVerification(PacketPtr pkt);

    /**
     * Keep a pointer to the system to allow querying memory properties.
     */
    System *system;

    int metadataCacheSize;

    RequestPort requestPort;
    ResponsePort responsePort;

    ReqPacketQueue reqQueue;
    RespPacketQueue respQueue;
    SnoopRespPacketQueue snoopRespQueue;

    typedef TimingTree IntegrityTree;
    /**
     * The simulated integrity tree. For now, this is a very basic tree.
     */
    IntegrityTree integrityTree;

    /**
     * Metadata cache.
     */
    SimpleMetadataCache metadataCache;

    bool hasRequestorId;

    /**
     * Used if a new metadata request is generated and a phony (but realistic)
     * requestor ID is needed.
     */
    RequestorID _requestorId;

    /**
     * Store the outstanding hash generation (for reads) while we wait for the
     * hash to complete. Once it is done, we can use it to verify the
     * integrity of a read response, and if everything passes, the original
     * data response will be properly forwarded back to LLC.
     */
    std::unordered_set<RequestPtr> outstandingIntegrityHashes;

    /**
     * Store the outstanding request pkts that have not been verified yet. This
     * may or may not be used based on whether there should be a lazy
     * verification strategy (start speculatively using the data received
     * before verification has completed).
     */
    std::unordered_set<PacketPtr> outstandingIntegrityVerification;

    /**
     * Reverse search for a packet from its request pointer.
     */
    std::unordered_map<RequestPtr, PacketPtr> packetLookup;

    /**
     * Store the outstanding requests for integrity metadata. This associates
     * a tree ID with a pointer to the (child) request that caused this.
     */
    std::unordered_multimap<uint64_t, RequestPtr> outstandingMetadataRequests;

    /**
     * Time (in ticks) to complete hashing.
     *
     * TODO Define a default value
     */
    Tick integrityHashingLatency = 800;

    /**
     * An event that represents when the hash generation for the data in a
     * response packet is finished. This will usually trigger verification
     * by comparing the generated hash to a parent integrity node.
     */
    class HashCompletionEvent : public Event
    {
      private:
        // Pointer to the related verifier object.
        AbstractIntegrityVerifier *verifier;

        // Pointer to the original request packet that we are verifying.
        PacketPtr pkt;

      public:
        HashCompletionEvent(
          AbstractIntegrityVerifier *verifier,
          PacketPtr pkt
        ) : Event(Default_Pri, AutoDelete),
          verifier(verifier),
          pkt(pkt)
        { }

        void process() override {
          verifier->completeIntegrityHash(pkt);
        }
    };

  protected:
    /**
     * Delay a request by some number of ticks.
     *
     * @return Ticks to delay packet.
     */
    virtual Tick delayReq(PacketPtr pkt) { return 0; }

    /**
     * Delay a response by some number of ticks.
     *
     * @return Ticks to delay packet.
     */
    virtual Tick delayResp(PacketPtr pkt) { return 0; }

    /**
     * Delay a snoop response by some number of ticks.
     *
     * @return Ticks to delay packet.
     */
    virtual Tick delaySnoopResp(PacketPtr pkt) { return 0; }
};

/**
 * Delay packets by a constant time. Delays can be specified
 * separately for read requests, read responses, write requests, and
 * write responses.
 *
 * This class does not delay snoops or requests/responses that are
 * neither reads or writes.
 */
class IntegrityVerifier : public AbstractIntegrityVerifier
{
  public:
    IntegrityVerifier(const IntegrityVerifierParams &params);

  protected:
    Tick delayReq(PacketPtr pkt) override;
    Tick delayResp(PacketPtr pkt) override;

  protected: // Params
    const Tick readReqDelay;
    const Tick readRespDelay;

    const Tick writeReqDelay;
    const Tick writeRespDelay;
};

} // namespace gem5

#endif //__MEM_INTEGRITY_VERIFIER_HH__
