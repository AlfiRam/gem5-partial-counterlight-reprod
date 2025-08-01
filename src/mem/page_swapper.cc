#include "mem/page_swapper.hh"

#include "debug/AbstractPageSwapper.hh"
#include "debug/AbstractPageSwapperTest.hh"

namespace gem5
{

AbstractPageSwapper::AbstractPageSwapper(const AbstractPageSwapperParams &p)
    : ClockedObject(p),
      system(p.system),
      pageBytes(p.page_bytes),
      swapEpoch(p.swap_epoch),
      reqsSinceLastSwap(0),
      requestPort(name() + "-mem_side_port", *this),
      responsePort(name() + "-cpu_side_port", *this),
      reqQueue(*this, requestPort),
      respQueue(*this, responsePort),
      snoopRespQueue(*this, requestPort),
      _requestorId(p.system->getRequestorId(this)),
      dramFullRange(p.dram_full_range),
      dramOsRange(p.dram_os_range),
      dramIntegrityRange(AddrRange(dramOsRange.end(), dramFullRange.end())),
      cxlFullRange(p.cxl_full_range),
      cxlOsRange(p.cxl_os_range),
      cxlIntegrityRange(AddrRange(cxlOsRange.end(), cxlFullRange.end())),
      stats(this)
{
    DPRINTF(AbstractPageSwapper,
        "%s: dramFullRange: %s (%llu:%llu, size %llu)\n",
        __func__, dramFullRange.to_string(),
        dramFullRange.start(), dramFullRange.end(), dramFullRange.size());
    DPRINTF(AbstractPageSwapper,
        "%s: dramOsRange: %s (%llu:%llu, size %llu)\n",
        __func__, dramOsRange.to_string(),
        dramOsRange.start(), dramOsRange.end(), dramOsRange.size());
    DPRINTF(AbstractPageSwapper,
        "%s: dramIntegrityRange: %s (%llu:%llu, size %llu)\n",
        __func__, dramIntegrityRange.to_string(),
        dramIntegrityRange.start(), dramIntegrityRange.end(),
        dramIntegrityRange.size());

    DPRINTF(AbstractPageSwapper,
        "%s: cxlFullRange: %s (%llu:%llu, size %llu)\n",
        __func__, cxlFullRange.to_string(),
        cxlFullRange.start(), cxlFullRange.end(), cxlFullRange.size());
    DPRINTF(AbstractPageSwapper,
        "%s: cxlOsRange: %s (%llu:%llu, size %llu)\n",
        __func__, cxlOsRange.to_string(),
        cxlOsRange.start(), cxlOsRange.end(), cxlOsRange.size());
    DPRINTF(AbstractPageSwapper,
        "%s: cxlIntegrityRange: %s (%llu:%llu, size %llu)\n",
        __func__, cxlIntegrityRange.to_string(),
        cxlIntegrityRange.start(), cxlIntegrityRange.end(),
        cxlIntegrityRange.size());
}

void
AbstractPageSwapper::init()
{
    if (!responsePort.isConnected() || !requestPort.isConnected())
        fatal("Page swapper is not connected on both sides.\n");
}


Port &
AbstractPageSwapper::getPort(const std::string &if_name, PortID idx)
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
AbstractPageSwapper::trySatisfyFunctional(PacketPtr pkt)
{
    return responsePort.trySatisfyFunctional(pkt) ||
        requestPort.trySatisfyFunctional(pkt);
}


AbstractPageSwapper::ResponsePort::
ResponsePort(const std::string &_name, AbstractPageSwapper &_parent)
    : QueuedResponsePort(_name, _parent.respQueue),
      parent(_parent)
{
}

Tick
AbstractPageSwapper::ResponsePort::recvAtomic(PacketPtr pkt)
{
    const Tick delay = parent.delayReq(pkt) + parent.delayResp(pkt);

    return delay + parent.requestPort.sendAtomic(pkt);
}

bool
AbstractPageSwapper::ResponsePort::recvTimingReq(PacketPtr pkt)
{
    // We want to just bypass immediately if this is an express snoop.
    // However, at least the translation needs to still be done for
    // consistency.
    if (pkt->isExpressSnoop()) {
        // parent.translateReq(pkt);
        return parent.requestPort.sendTimingReq(pkt);
    }

    return parent.handleReq(pkt);
}

void
AbstractPageSwapper::ResponsePort::recvFunctional(PacketPtr pkt)
{
    if (parent.trySatisfyFunctional(pkt)) {
        pkt->makeResponse();
    } else {
        parent.requestPort.sendFunctional(pkt);
    }
}

bool
AbstractPageSwapper::ResponsePort::recvTimingSnoopResp(PacketPtr pkt)
{
    // parent.translateResp(pkt);

    const Tick when = curTick() + parent.delaySnoopResp(pkt);

    parent.requestPort.schedTimingSnoopResp(pkt, when);

    return true;
}


AbstractPageSwapper::RequestPort::RequestPort(
    const std::string &_name,
    AbstractPageSwapper &_parent
) : QueuedRequestPort(_name, _parent.reqQueue, _parent.snoopRespQueue),
      parent(_parent)
{
}

bool
AbstractPageSwapper::RequestPort::recvTimingResp(PacketPtr pkt)
{
    return parent.handleResp(pkt);
}

void
AbstractPageSwapper::RequestPort::recvFunctionalSnoop(PacketPtr pkt)
{
    if (parent.trySatisfyFunctional(pkt)) {
        pkt->makeResponse();
    } else {
        parent.responsePort.sendFunctionalSnoop(pkt);
    }
}

Tick
AbstractPageSwapper::RequestPort::recvAtomicSnoop(PacketPtr pkt)
{
    const Tick delay = parent.delaySnoopResp(pkt);

    return delay + parent.responsePort.sendAtomicSnoop(pkt);
}

void
AbstractPageSwapper::RequestPort::recvTimingSnoopReq(PacketPtr pkt)
{
    // parent.translateReq(pkt);
    parent.responsePort.sendTimingSnoopReq(pkt);
}


bool
AbstractPageSwapper::hasValidRanges()
{
    // TODO Function not being used.
    return (
        dramFullRange.end() != Addr(0) &&
        dramOsRange.end() != Addr(0) &&
        dramIntegrityRange.end() != Addr(0) &&
        cxlFullRange.end() != Addr(0) &&
        cxlOsRange.end() != Addr(0) &&
        cxlIntegrityRange.end() != Addr(0)
    );
}


Addr
AbstractPageSwapper::getPageAddr(Addr addr)
{
    return addr & ~(pageBytes - 1);
}


Addr
AbstractPageSwapper::getPageAddr(PacketPtr pkt)
{
    return getPageAddr(pkt->getAddr());
    // return pkt->getAddr() & ~(pageBytes - 1);
}


Addr
AbstractPageSwapper::getCxlPageAddr(PacketPtr pkt)
{
    if (cxlFullRange.contains(pkt->getAddr())) {
        // This is a CXL address already and we can get the page as-is.
        return getPageAddr(pkt);
    } else {
        assert(dramFullRange.contains(pkt->getAddr()));
        // Check the already swapped pages first for a matching page, and if
        // not here, check the pages that are in-progress swapping.
        if (pageTable.find(getPageAddr(pkt)) != pageTable.end()) {
            assert(cxlFullRange.contains(pageTable[getPageAddr(pkt)]));
            return pageTable[getPageAddr(pkt)];
        } else {
            panic("Unable to find paired CXL page for pkt %s", pkt->print());
        }
    }

    // panic("Unreachable statement");
    // return Addr(0);
}


void
AbstractPageSwapper::schedReq(PacketPtr pkt)
{
    // Metadata requests do not need to have strict ordering, so it can be
    // sent right away.
    // if (pkt->isMetadataRequest()) {
    //     // addToPacketLookup(pkt);
    //     sendReqToMem(pkt);
    //     return;
    // }

    // Mark this packet as ready to request.
    requestReady.insert(pkt->req);

    // There should be something in the request queue, or otherwise we are
    // attempting to send a request we know nothing about.
    assert(!requestQueue.empty());

    // If this is a data request, this should already be added to
    // `packetLookup`.
    assert(packetLookup.find(pkt->req) != packetLookup.end());

    // Check if there's anything we can take off the queue now.
    while (!requestQueue.empty()) {
        auto front = requestQueue.front();

        bool isReady = requestReady.find(front) != requestReady.end();
        if (isReady) {
            // This request is now the front of the queue and has been
            // determined ready to send. Let's send it off!
            sendReqToMem(packetLookup[front]);

            requestReady.erase(front);
            DPRINTF(AbstractPageSwapper, "%s: Popping %p from requestQueue\n",
                    __func__, front);
            requestQueue.pop();
        } else {
            // The request at the front of the queue is not ready to send.
            // Stop.
            break;
        }
    }
}

void
AbstractPageSwapper::schedResp(PacketPtr pkt)
{
    assert(!pkt->isForPageSwap());

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
AbstractPageSwapper::sendReqToMem(PacketPtr pkt)
{
    // Data requests should already be accounted for.
    if (!pkt->isForPageSwap()) {
        assert(packetLookup[pkt->req] == pkt);
        // Make sure we aren't sending off something that's supposed to be on a
        // locked page.
        assert(lockedPages.find(getPageAddr(pkt)) == lockedPages.end());

        if (shouldHandlePacket(pkt)) {
            assert(pkt->isTranslatedPageSwap());
        }
    }

    DPRINTF(AbstractPageSwapper, "%s: Scheduling req %s to memory\n",
        __func__, pkt->print());
    // TODO Add delay as needed (or `when` param)
    requestPort.schedTimingReq(pkt, clockEdge(Cycles(1)));

    if (!pkt->needsResponse()) {
        // Packets that aren't getting a response should not be tracked for
        // response timing, and are ready to discard.
        removeFromPacketLookup(pkt);
        return;
    }

    // If this was a packet generated by this component, add it to the packet
    // lookup now.
    if (pkt->isForPageSwap()) {
        addToPacketLookup(pkt);
    }

    markReqStart(pkt);
}


void
AbstractPageSwapper::sendRespToCpu(PacketPtr pkt)
{
    DPRINTF(AbstractPageSwapper, "%s: Scheduling resp %s to CPU\n",
        __func__, pkt->print());
    // TODO Add delay as needed (or `when` param)
    responsePort.schedTimingResp(pkt, clockEdge(Cycles(1)));
    assert(!pkt->isTranslatedPageSwap());

    removeFromPacketLookup(pkt);
}


void
AbstractPageSwapper::markReqStart(PacketPtr pkt)
{
    // TODO Update this function as needed

    assert(pkt->needsResponse());

    // This request should not already have been marked to start.
    assert(arrivalTime.find(pkt->req) == arrivalTime.end());

    arrivalTime[pkt->req] = curTick();

    DPRINTF(AbstractPageSwapper,
        "%s: arrivalTime increased. size: %d\n",
        __func__, arrivalTime.size());
}


void
AbstractPageSwapper::markReqEnd(PacketPtr pkt)
{
    // TODO Update this function as needed

    // This request should have been entered prior.
    assert(arrivalTime.find(pkt->req) != arrivalTime.end());

    stats.requestsHandled++;
    stats.totalReqTime += curTick() - arrivalTime[pkt->req];

    // TODO Add all the other stats

    arrivalTime.erase(pkt->req);
    DPRINTF(AbstractPageSwapper,
        "%s: arrivalTime decreased. size: %d\n",
        __func__, arrivalTime.size());
}


void
AbstractPageSwapper::addToPacketLookup(PacketPtr pkt)
{
    assert(packetLookup.find(pkt->req) == packetLookup.end());
    packetLookup.emplace(pkt->req, pkt);
    DPRINTF(AbstractPageSwapper,
        "%s: packetLookup increased. size: %d\n",
        __func__, packetLookup.size());
    DPRINTF(AbstractPageSwapper,
        "%s: Associating req 0x%x (%p) with pkt %s (%p)\n",
        __func__,
        pkt->req->hasPaddr() ? pkt->req->getPaddr() : 9999999,
        pkt->req,
        pkt->print(),
        pkt);
}

void
AbstractPageSwapper::updatePacketLookup(PacketPtr pkt)
{
    assert(packetLookup.find(pkt->req) != packetLookup.end());

    packetLookup[pkt->req] = pkt;

    DPRINTF(AbstractPageSwapper,
        "%s: packetLookup updated. size: %d\n",
        __func__, packetLookup.size());
    DPRINTF(AbstractPageSwapper,
        "%s: Associating req 0x%x (%p) with new pkt %s (%p)\n",
        __func__,
        pkt->req->hasPaddr() ? pkt->req->getPaddr() : 9999999,
        pkt->req,
        pkt->print(),
        pkt);
}

void
AbstractPageSwapper::removeFromPacketLookup(PacketPtr pkt)
{
    assert(packetLookup.find(pkt->req) != packetLookup.end());
    // Ensure that the packet surrounding the request has not somehow changed.
    assert(packetLookup[pkt->req] == pkt);
    DPRINTF(AbstractPageSwapper,
        "%s: Un-associating req 0x%x (%p) with pkt %s (%p)\n",
        __func__,
        pkt->req->hasPaddr() ? pkt->req->getPaddr() : 9999999,
        pkt->req,
        pkt->print(),
        pkt);
    packetLookup.erase(pkt->req);
    DPRINTF(AbstractPageSwapper,
        "%s: packetLookup decreased. size: %d\n",
        __func__, packetLookup.size());

    // Handle the cases where stalls were waiting for a request to be finished.
    if (pendingReqForSwap.find(pkt->req) != pendingReqForSwap.end()) {
        pendingReqForSwap.erase(pkt->req);
        DPRINTF(AbstractPageSwapper, "%s: Pending requests for swap: %u\n",
                __func__, pendingReqForSwap.size());

        if (pendingReqForSwap.size() == 0) {
            DPRINTF(AbstractPageSwapper,
                    "%s: All requests waited by swap are complete. Continuing "
                    "swap process.\n",
                    __func__);
            Addr cxlPage = getCxlPageAddr(pkt);
            performSwap(SwapProcessStage::QueueReads, cxlPage);
        }
    }
}


bool
AbstractPageSwapper::handleReq(PacketPtr pkt)
{
    markReqReceived(pkt);

    Addr pageAddr = getPageAddr(pkt);

    // If a request corresponds to a page that is currently locked, do not
    // let it proceed and place it in a pre-address-translation queue.
    if (lockedPages.find(pageAddr) != lockedPages.end()) {
        DPRINTF(AbstractPageSwapper,
                "%s: %s belongs to a locked page 0x%lx; storing in "
                "pre-address-translation queue.\n",
                __func__, pkt->print(), pageAddr);
        DPRINTF(AbstractPageSwapperTest,
                "%s: %s belongs to a locked page 0x%lx; storing in "
                "pre-address-translation queue.\n",
                __func__, pkt->print(), pageAddr);
        preTranslationQueue.push(pkt);
        return true;
    } else if (lockedPages.find(pageTable[pageAddr]) != lockedPages.end()) {
        DPRINTF(AbstractPageSwapper,
                "%s: Translation of %s belongs to a locked page 0x%lx; "
                "storing in pre-address-translation queue.\n",
                __func__, pkt->print(), pageTable[pageAddr]);
        DPRINTF(AbstractPageSwapperTest,
                "%s: Translation of %s belongs to a locked page 0x%lx; "
                "storing in pre-address-translation queue.\n",
                __func__, pkt->print(), pageTable[pageAddr]);
        preTranslationQueue.push(pkt);
        return true;
    }

    // All pending requests that are expecting a response should be
    // recorded.

    // Perform address translation
    if (shouldHandlePacket(pkt)) {
        translateReq(pkt);
    }

    // TODO Once we start translating addresses, add a few extra cycles of
    // delay for the translation.

    // Account for header delay and deserialization time
    // Tick receive_delay = pkt->headerDelay + pkt->payloadDelay;
    // pkt->headerDelay = pkt->payloadDelay = 0;

    // const Tick when = curTick() + delayReq(pkt) + receive_delay;

    // requestPort.schedTimingReq(pkt, when);
    // sendReqToMem(pkt);
    schedReq(pkt);

    DPRINTF(AbstractPageSwapper,
            "%s: Requests since last swap: %u / %u\n",
            __func__, reqsSinceLastSwap, swapEpoch);

    if (reqsSinceLastSwap >= swapEpoch && lockedPages.size() == 0) {
        // We have seen enough requests since the last swap and there is no
        // ongoing swap.
        performSwap();
    }

    return true;
}


bool
AbstractPageSwapper::handleResp(PacketPtr pkt)
{
    markRespReceived(pkt);

    if (pkt->isForPageSwap()) {
        // This is for the read phase of the swap.
        if (pkt->isRead()) {
            // Make this part of the buffer for swapping if this is applicable.
            assert(pendingSwapRead.find(pkt->getAddr()) !=
                pendingSwapRead.end());
            pendingSwapRead.erase(pkt->getAddr());
            savedSwapData.emplace(pkt->getAddr(), pkt);

            // Check if the response is the last of the pending requests for
            // pages that are being swapped.
            if (pendingSwapRead.empty()) {
                DPRINTF(AbstractPageSwapper,
                    "%s: All reads for swap completed.\n",
                    __func__);

                // Find the CXL page address associated with the swap as the
                // key.
                Addr cxlPageKey;
                if (dramFullRange.contains(pkt->getAddr())) {
                    // Translate DRAM address to CXL address.
                    cxlPageKey = dramToCxlSwaps[getPageAddr(pkt)];
                } else {
                    // This is already a CXL address, get the address of the
                    // page.
                    assert(cxlFullRange.contains(pkt->getAddr()));
                    cxlPageKey = getPageAddr(pkt);
                }

                // Trigger the next stage of the swap.
                performSwap(SwapProcessStage::QueueWrites, cxlPageKey);
            } else {
                DPRINTF(AbstractPageSwapper,
                        "%s: Remaining reads for swap: %lu\n",
                        __func__, pendingSwapRead.size());
            }
        } else {
            // This is for the write phase of the swap.
            assert(pkt->isWrite());
            assert(pendingSwapWrite.find(pkt->getAddr()) !=
                pendingSwapWrite.end());
            pendingSwapWrite.erase(pkt->getAddr());

            // Check if the response is the last of the writes needed for the
            // swap.
            if (pendingSwapWrite.empty()) {
                DPRINTF(AbstractPageSwapper,
                    "%s: All writes for swap completed.\n",
                    __func__);

                // Find the CXL page address associated with the swap as the
                // key.
                Addr cxlPageKey;
                if (dramFullRange.contains(pkt->getAddr())) {
                    // Translate DRAM address to CXL address.
                    cxlPageKey = dramToCxlSwaps[getPageAddr(pkt)];
                } else {
                    // This is already a CXL address, get the address of the
                    // page.
                    assert(cxlFullRange.contains(pkt->getAddr()));
                    cxlPageKey = getPageAddr(pkt);
                }

                // Trigger the last stage of the swap.
                performSwap(SwapProcessStage::Unlock, cxlPageKey);
            } else {
                DPRINTF(AbstractPageSwapper,
                    "%s: Remaining writes for swap: %lu\n",
                    __func__, pendingSwapWrite.size());
            }

            // This write packet is now no longer needed and can be disposed.
            removeFromPacketLookup(pkt);
            delete pkt;
        }

        return true;
    }


    if (shouldHandlePacket(pkt)) {
        translateResp(pkt);
    }
    // Account for header delay and deserialization time
    // const Tick receive_delay = pkt->headerDelay + pkt->payloadDelay;
    // pkt->headerDelay = pkt->payloadDelay = 0;

    // const Tick when = curTick() + parent.delayResp(pkt) + receive_delay;

    // responsePort.schedTimingResp(pkt, when);

    // sendRespToCpu(pkt);
    schedResp(pkt);

    return true;
}


void
AbstractPageSwapper::markReqReceived(PacketPtr pkt)
{
    DPRINTF(AbstractPageSwapper,
        "%s: Recv req %s (pkt addr %p, req addr %p)\n",
        __func__, pkt->print(), pkt, pkt->req);

    countPageAccess(pkt);

    // Associate this packet with its request. This should only be removed
    // from packet lookup once the packet will no longer be expected to be
    // handled here anymore (either when sent to memory if it doesn't need
    // a response, or when returned to the CPU if it did need a response).
    addToPacketLookup(pkt);

    // Account for the ordering of this packet with respect to forwarding to
    // memory.
    requestQueue.push(pkt->req);
    DPRINTF(AbstractPageSwapper, "%s: pushing %p to requestQueue\n",
            __func__, pkt->req);
    if (pkt->needsResponse()) {
        responseQueue.push(pkt->req);
    }
}


void
AbstractPageSwapper::markRespReceived(PacketPtr pkt)
{
    DPRINTF(AbstractPageSwapper,
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
AbstractPageSwapper::countPageAccess(PacketPtr pkt)
{
    // Ensure the packet has not yet been translated coming in.
    assert(pkt->isRequest());
    assert(!pkt->isTranslatedPageSwap());

    // Get the address representing the beginning of the physical page.
    Addr pageAddr = translateAddr(getPageAddr(pkt), false);

    // // Currently, only consider pages for integrity data.
    // if (dramIntegrityRange.contains(pageAddr)) {
    //     // This packet was intended for DRAM.
    //     dramPageLastAccessed[pageAddr] = curTick();
    //     reqsSinceLastSwap++;
    // } else if (cxlIntegrityRange.contains(pageAddr)) {
    //     // This packet was intended for CXL.
    //     cxlPageLastAccessed[pageAddr] = curTick();
    //     reqsSinceLastSwap++;
    // }

    // TODO TEST: Swap anything.
    pageLastAccessed[pageAddr] = curTick();
    if (dramFullRange.contains(pageAddr) || cxlFullRange.contains(pageAddr)) {
        reqsSinceLastSwap++;
    }
}


void
AbstractPageSwapper::performSwap()
{
    performSwap(SwapProcessStage::DetermineSwapped, Addr(0));
}


void
AbstractPageSwapper::performSwap(SwapProcessStage stage, Addr cxlPageKey)
{
    /////////////////// Stage 1: Determine swapped pages, complete pending
    //                  requests. Do a lock to prevent additional requests for
    //                  the time being. (NOW, to prevent more coming in.)
    if (stage == SwapProcessStage::DetermineSwapped) {
        DPRINTF(AbstractPageSwapper, "%s: SWAP STAGE DetermineSwapped\n",
                __func__);
        // Decide which pages should be swapped.
        auto result = determineSwappedPages();
        Addr cxlPage = result.first;
        Addr dramPage = result.second;

        if (cxlPage == Addr(0) && dramPage == Addr(0)) {
            // It has been determined that no page should be swapped
            // (this time).
            return;
        }

        swapStartTick = curTick();

        // Mark what pages (in DRAM and CXL) are being swapped, so that
        // requests for those pages are frozen until the swap is complete.
        // Any new requests that are received (relevant to these pages)
        // should stay in a pre-address-translation queue. (All ongoing
        // requests can finish up and pass through as normal.)
        cxlToDramSwaps.emplace(cxlPage, dramPage);
        dramToCxlSwaps.emplace(dramPage, cxlPage);
        lockedPages.emplace(cxlPage);
        lockedPages.emplace(dramPage);

        // Wait for any pending requests for the relevant pages to
        // complete.
        // Check if there are already pending requests, or if we are
        // free to move to the next step.

        bool pendingRequests = false;
        for (auto search : packetLookup) {
            PacketPtr pkt = search.second;
            Addr page = getPageAddr(pkt);
            if (page == cxlPage || page == dramPage) {
                pendingReqForSwap.emplace(pkt->req);
                pendingRequests = true;
            }
        }

        if (!pendingRequests) {
            DPRINTF(AbstractPageSwapper,
                    "%s: It appears there are no ongoing requests "
                    "involving the swapped pages. This is free to swap "
                    "now.\n",
                    __func__);
            DPRINTF(AbstractPageSwapperTest,
                    "%s: It appears there are no ongoing requests "
                    "involving the swapped pages. This is free to swap "
                    "now.\n",
                    __func__);
            performSwap(SwapProcessStage::QueueReads, cxlPage);
        } else {
            DPRINTF(AbstractPageSwapper,
                    "%s: There are %u ongoing request(s) involving the "
                    "swapped pages. Waiting until they are completed "
                    "before swapping.\n",
                    __func__, pendingReqForSwap.size());
            DPRINTF(AbstractPageSwapperTest,
                    "%s: There are %u ongoing request(s) involving the "
                    "swapped pages. Waiting until they are completed "
                    "before swapping.\n",
                    __func__, pendingReqForSwap.size());
        }
    }

    ///////////////////// Stage 2: There are no more pending requests. You can
    //                    queue up the reads for the swap.
    else if (stage == SwapProcessStage::QueueReads) {
        // Only allow one swap at a time.
        assert(lockedPages.size() == 2);
        assert(pendingReqForSwap.empty());

        DPRINTF(AbstractPageSwapper, "%s: SWAP STAGE QueueReads(0x%lx)\n",
                __func__, cxlPageKey);
        DPRINTF(AbstractPageSwapperTest, "%s: SWAP STAGE QueueReads(0x%lx)\n",
                __func__, cxlPageKey);
        Addr dramPage = cxlToDramSwaps[cxlPageKey];
        auto cacheLineSize = system->cacheLineSize();

        // Queue up reads for the entire page of DRAM
        for (Addr dramAddr = dramPage;
                dramAddr < dramPage + pageBytes;
                dramAddr += cacheLineSize) {
            RequestPtr req = std::make_shared<Request>(
                dramAddr,
                cacheLineSize, // Size
                0, // No flags
                _requestorId
            );
            uint8_t* pkt_data = new uint8_t[req->getSize()];

            PacketPtr pkt = Packet::createRead(req);
            pkt->dataDynamic(pkt_data);
            pkt->req->setFlags(Request::UNCACHEABLE);
            pkt->setForPageSwap();
            DPRINTF(AbstractPageSwapper,
                "%s: Created packet %s\n",
                __func__, pkt->print());

            // Send request
            sendReqToMem(pkt);

            pendingSwapRead.emplace(dramAddr);
        }

        // Queue up reads for the entire page of CXL
        for (Addr cxlAddr = cxlPageKey;
                cxlAddr < cxlPageKey + pageBytes;
                cxlAddr += cacheLineSize) {
            RequestPtr req = std::make_shared<Request>(
                cxlAddr,
                cacheLineSize, // Size
                0, // No flags
                _requestorId
            );
            uint8_t* pkt_data = new uint8_t[req->getSize()];

            PacketPtr pkt = Packet::createRead(req);
            pkt->dataDynamic(pkt_data);
            pkt->req->setFlags(Request::UNCACHEABLE);
            pkt->setForPageSwap();
            DPRINTF(AbstractPageSwapper,
                "%s: Created packet %s\n",
                __func__, pkt->print());

            // Send request
            sendReqToMem(pkt);

            pendingSwapRead.emplace(cxlAddr);
        }
    }

    //////////////////// Stage 3: All the data is stored for the swap. Queue
    //                   up the write portion of the swap.
    else if (stage == SwapProcessStage::QueueWrites) {
        DPRINTF(AbstractPageSwapper, "%s: SWAP STAGE QueueWrites(0x%lx)\n",
                __func__, cxlPageKey);
        DPRINTF(AbstractPageSwapperTest, "%s: SWAP STAGE QueueWrites(0x%lx)\n",
                __func__, cxlPageKey);
        // (Once both of those reads are complete, queue up writes for the
        // entire page of DRAM and CXL.)
        // We will use the real data read from DRAM and CXL, even if it isn't
        // technically used, because swapping could involve real application
        // pages as well.

        Addr dramPage = cxlToDramSwaps[cxlPageKey];
        auto cacheLineSize = system->cacheLineSize();

        DPRINTF(AbstractPageSwapper, "%s: Creating write packets.\n",
                __func__);
        // Print contents for debugging (DRAM -> CXL)
        for (Addr pageOffset = 0;
                pageOffset < pageBytes;
                pageOffset += cacheLineSize) {
            Addr dramAddr = dramPage + pageOffset;
            Addr cxlAddr = cxlPageKey + pageOffset;

            PacketPtr originalDramPkt = savedSwapData[dramAddr];
            uint8_t* cacheline = new uint8_t[originalDramPkt->getSize()];
            originalDramPkt->writeData(cacheline);

            std::ostringstream data;
            for (size_t i = 0; i < originalDramPkt->getSize(); i++) {
                ccprintf(data, "%02x", cacheline[i]);
            }
            DPRINTF(AbstractPageSwapper, "%s: DRAM -> CXL 0x%0x: %s\n",
                    __func__, cxlAddr, data.str());

            delete [] cacheline;
        }

        // Queue up writes for the entire page of DRAM (now going to CXL)
        for (Addr pageOffset = 0;
                pageOffset < pageBytes;
                pageOffset += cacheLineSize) {
            Addr dramAddr = dramPage + pageOffset;
            Addr cxlAddr = cxlPageKey + pageOffset;
            RequestPtr req = std::make_shared<Request>(
                cxlAddr,
                cacheLineSize, // Size
                0, // No flags
                _requestorId
            );
            uint8_t* pkt_data = new uint8_t[req->getSize()];

            PacketPtr pkt = Packet::createWrite(req);

            // Retrieve the saved data, and since we made this request,
            // we now deallocate the packet.
            PacketPtr originalDramPkt = savedSwapData[dramAddr];
            originalDramPkt->writeData(pkt_data);
            savedSwapData.erase(dramAddr);
            removeFromPacketLookup(originalDramPkt);
            delete originalDramPkt;

            pkt->dataDynamic(pkt_data);
            pkt->req->setFlags(Request::UNCACHEABLE);
            pkt->setForPageSwap();
            DPRINTF(AbstractPageSwapper,
                "%s: Created packet %s\n",
                __func__, pkt->print());

            // Send request
            sendReqToMem(pkt);

            pendingSwapWrite.emplace(cxlAddr);
        }

        // Print contents for debugging (CXL -> DRAM)
        for (Addr pageOffset = 0;
                pageOffset < pageBytes;
                pageOffset += cacheLineSize) {
            Addr dramAddr = dramPage + pageOffset;
            Addr cxlAddr = cxlPageKey + pageOffset;

            PacketPtr originalCxlPkt = savedSwapData[cxlAddr];
            uint8_t* cacheline = new uint8_t[originalCxlPkt->getSize()];
            originalCxlPkt->writeData(cacheline);

            std::ostringstream data;
            for (size_t i = 0; i < originalCxlPkt->getSize(); i++) {
                ccprintf(data, "%02x", cacheline[i]);
            }
            DPRINTF(AbstractPageSwapper, "%s: CXL -> DRAM 0x%0x: %s\n",
                    __func__, dramAddr, data.str());

            delete [] cacheline;
        }

        // Do the same to make requests for CXL (data now goes to DRAM)
        for (Addr pageOffset = 0;
                pageOffset < pageBytes;
                pageOffset += cacheLineSize) {
            Addr dramAddr = dramPage + pageOffset;
            Addr cxlAddr = cxlPageKey + pageOffset;
            RequestPtr req = std::make_shared<Request>(
                dramAddr,
                cacheLineSize, // Size
                0, // No flags
                _requestorId
            );
            uint8_t* pkt_data = new uint8_t[req->getSize()];

            PacketPtr pkt = Packet::createWrite(req);

            // Retrieve the saved data, and since we made this request,
            // we now deallocate the packet.
            PacketPtr originalCxlPkt = savedSwapData[cxlAddr];
            originalCxlPkt->writeData(pkt_data);
            savedSwapData.erase(cxlAddr);
            removeFromPacketLookup(originalCxlPkt);
            delete originalCxlPkt;

            pkt->dataDynamic(pkt_data);
            pkt->req->setFlags(Request::UNCACHEABLE);
            pkt->setForPageSwap();
            DPRINTF(AbstractPageSwapper,
                "%s: Created packet %s\n",
                __func__, pkt->print());

            // Send request
            sendReqToMem(pkt);

            pendingSwapWrite.emplace(dramAddr);
        }

        // Store the translation data in a lookup table.
        pageTable[dramPage] = cxlPageKey;
        pageTableReverse[cxlPageKey] = dramPage;
        pageTable[cxlPageKey] = dramPage;
        pageTableReverse[dramPage] = cxlPageKey;
    }

    ///////////////////// Stage 4: Swap is complete. Unlock and allow requests
    //                    to continue for these pages again.
    else if (stage == SwapProcessStage::Unlock) {
        DPRINTF(AbstractPageSwapper, "%s: SWAP STAGE Unlock(0x%lx)\n",
                __func__, cxlPageKey);
        DPRINTF(AbstractPageSwapperTest, "%s: SWAP STAGE Unlock(0x%lx)\n",
                __func__, cxlPageKey);
        // Mark the swap as complete.
        Addr dramPage = cxlToDramSwaps[cxlPageKey];
        cxlToDramSwaps.erase(cxlPageKey);
        dramToCxlSwaps.erase(dramPage);
        lockedPages.erase(cxlPageKey);
        lockedPages.erase(dramPage);
        stats.totalSwapCount++;
        stats.totalSwapTime += curTick() - swapStartTick;

        // Swap the last access times in tracking.
        Tick dramPageTime = pageLastAccessed[dramPage];
        Tick cxlPageTime = pageLastAccessed[cxlPageKey];
        pageLastAccessed[cxlPageKey] = dramPageTime;
        pageLastAccessed[dramPage] = cxlPageTime;

        DPRINTF(AbstractPageSwapper,
                "%s: Swap complete for DRAM (0x%lx) <-> CXL (0x%lx)\n",
                __func__, dramPage, cxlPageKey);

        reqsSinceLastSwap = 0;

        DPRINTF(AbstractPageSwapper,
                "%s: Scheduling pending requests for newly-swapped pages.\n",
                __func__);

        // Schedule up any pending requests for the newly-swapped pages.
        while (!preTranslationQueue.empty()) {
            PacketPtr pkt = preTranslationQueue.front();
            if (shouldHandlePacket(pkt)) {
                translateReq(pkt);
            }
            schedReq(pkt);
            preTranslationQueue.pop();
        }
    }
}


std::pair<Addr, Addr>
AbstractPageSwapper::determineSwappedPages()
{
    // If there isn't enough data to know what to swap, don't swap.
    if (pageLastAccessed.size() < 2) {
        DPRINTF(AbstractPageSwapper,
            "%s: Not enough data to swap anything. Aborting.\n",
            __func__);
        return std::pair<Addr, Addr>(0, 0);
    }

    Tick mostRecentCxlTime = 0;
    Addr cxlPage = Addr(0);
    Tick leastRecentDramTime = curTick() + 1;
    Addr dramPage = Addr(0);
    for (auto it : pageLastAccessed) {
        // Look for the most-recently used CXL page.
        if (cxlFullRange.contains(it.first) &&
                it.second > mostRecentCxlTime) {
            mostRecentCxlTime = it.second;
            cxlPage = it.first;
        }
        // Look for the least-recently used DRAM page.
        else if (dramFullRange.contains(it.first) &&
                it.second < leastRecentDramTime) {
            leastRecentDramTime = it.second;
            dramPage = it.first;
        }
    }

    if (mostRecentCxlTime == 0 || leastRecentDramTime == curTick() + 1) {
        DPRINTF(AbstractPageSwapper,
            "%s: Not enough data to swap. Aborting.\n",
            __func__);
        return std::pair<Addr, Addr>(0, 0);
    }

    DPRINTF(AbstractPageSwapper,
            "%s: Most-recently used CXL page: 0x%lx (@ %lu)\n",
            __func__, cxlPage, mostRecentCxlTime);
    DPRINTF(AbstractPageSwapper,
            "%s: Least-recently used DRAM page: 0x%lx (@ %lu)\n",
            __func__, dramPage, leastRecentDramTime);

    // Sanity check.
    // TODO TESTING
    // assert(dramIntegrityRange.contains(dramPage));
    // assert(cxlIntegrityRange.contains(cxlPage));
    assert(dramFullRange.contains(dramPage));
    assert(cxlFullRange.contains(cxlPage));

    if (mostRecentCxlTime <= leastRecentDramTime) {
        // If no CXL page has been accessed more recently than DRAM, do not
        // attempt a swap.
        DPRINTF(AbstractPageSwapper,
                "%s: Most recent CXL page time: %lu; "
                "Least recent DRAM page time: %lu; Aborting.\n",
                __func__, mostRecentCxlTime, leastRecentDramTime);
        return std::pair<Addr, Addr>(0, 0);
    }

    if (pageTable[cxlPage] != cxlPage || pageTable[dramPage] != dramPage) {
        DPRINTF(AbstractPageSwapper,
                "%s: It appears that at least one of these pages have already "
                "been swapped. (CXL 0x%lx or DRAM 0x%lx) Aborting.\n",
                __func__, cxlPage, dramPage);
        DPRINTF(AbstractPageSwapperTest,
                "%s: It appears that at least one of these pages have already "
                "been swapped. (CXL 0x%lx or DRAM 0x%lx) Aborting.\n",
                __func__, cxlPage, dramPage);
        return std::pair<Addr, Addr>(0, 0);
    }

    DPRINTF(AbstractPageSwapper,
        "%s: Selected to swap CXL (0x%lx) <-> DRAM (0x%lx)\n",
        __func__, cxlPage, dramPage);
    DPRINTF(AbstractPageSwapperTest,
        "%s: Selected to swap CXL (0x%lx) <-> DRAM (0x%lx)\n",
        __func__, cxlPage, dramPage);
    return std::pair<Addr, Addr>(cxlPage, dramPage);
}


Addr
AbstractPageSwapper::translateAddr(Addr addr, bool reverse)
{
    Addr originalAddr = addr;
    Addr originalPage = getPageAddr(addr);

    bool translationExists;

    if (!reverse) {
        translationExists = pageTable.find(originalPage) != pageTable.end();
    } else {
        translationExists = pageTableReverse.find(originalPage) !=
            pageTableReverse.end();
    }

    if (!translationExists) {
        // This is the first time we've seen this page. We will add it to the
        // table now as a direct mapping.
        pageTable[originalPage] = originalPage;
        pageTableReverse[originalPage] = originalPage;
        translationExists = true;
    }

    assert(translationExists);

    // Calculate the translated address.
    Addr pageOffset = originalAddr - originalPage;

    Addr translatedPage;
    if (!reverse) {
        translatedPage = pageTable[originalPage];
    } else {
        translatedPage = pageTableReverse[originalPage];
    }
    Addr translatedAddr = translatedPage + pageOffset;

    DPRINTF(AbstractPageSwapper, "%s: Translated 0x%lx -> 0x%lx\n",
            __func__, originalAddr, translatedAddr);

    return translatedAddr;
}


void
AbstractPageSwapper::translateReq(PacketPtr pkt)
{
    assert(!pkt->isTranslatedPageSwap());

    Addr originalAddr = pkt->getAddr();

    // Translate from the original address to the potentially modified address.
    Addr translatedAddr = translateAddr(originalAddr, false);

    pkt->setOriginalAddr(originalAddr);
    pkt->setAddr(translatedAddr);
    pkt->req->setPaddr(translatedAddr);
    pkt->setTranslatedPageSwap();

    DPRINTF(AbstractPageSwapper, "%s: Translated req 0x%lx -> 0x%lx\n",
            __func__, originalAddr, translatedAddr);
}


void
AbstractPageSwapper::translateResp(PacketPtr pkt)
{
    assert(pkt->isTranslatedPageSwap());

    Addr addr = pkt->getAddr();

    // Translate from the modified address back to the original address.
    // Addr originalAddr = translateAddr(addr, true);
    // assert(originalAddr == pkt->getOriginalAddr());
    Addr originalAddr = pkt->getOriginalAddr();

    pkt->setAddr(originalAddr);
    pkt->req->setPaddr(originalAddr);
    pkt->unsetTranslatedPageSwap();

    DPRINTF(AbstractPageSwapper, "%s: Translated resp 0x%lx -> 0x%lx\n",
            __func__, addr, originalAddr);
}


AbstractPageSwapper::PageSwapperStats::PageSwapperStats(
    statistics::Group *parent
) : statistics::Group(parent, "page_swapper"),
    ADD_STAT(totalSwapCount, statistics::units::Count::get(),
            "Total number of swaps completed"),
    ADD_STAT(totalSwapTime, statistics::units::Tick::get(),
            "Total amount of time taken swapping"),
    ADD_STAT(avgSwapTime, statistics::units::Tick::get(),
            "Average time taken for each swap"),

    ADD_STAT(requestsHandled, statistics::units::Count::get(),
            "Total number of requests handled"),
    ADD_STAT(metadataReqHandled, statistics::units::Count::get(),
            "Total number of metadata requests handled"),
    ADD_STAT(dataReqHandled, statistics::units::Count::get(),
            "Total number of data requests handled"),

    ADD_STAT(reqHandledDram, statistics::units::Count::get(),
            "Total number of requests to memory in DRAM (post-translation)"),
    ADD_STAT(reqHandledDramOs, statistics::units::Count::get(),
            "Total number of requests to (non-integrity) memory in DRAM "
            "(post-translation)"),
    ADD_STAT(reqHandledDramIntegrity, statistics::units::Count::get(),
            "Total number of requests to integrity memory in DRAM "
            "(post-translation)"),
    ADD_STAT(reqHandledCxl, statistics::units::Count::get(),
            "Total number of requests to memory in CXL (post-translation)"),
    ADD_STAT(reqHandledCxlOs, statistics::units::Count::get(),
            "Total number of requests to (non-integrity) memory in CXL "
            "(post-translation)"),
    ADD_STAT(reqHandledCxlIntegrity, statistics::units::Count::get(),
            "Total number of requests to integrity memory in CXL "
            "(post-translation)"),

    ADD_STAT(totalReqTime, statistics::units::Tick::get(),
            "Total amount of time where a request is out then in"),
    ADD_STAT(totalMetadataReqTime, statistics::units::Tick::get(),
            "Total amount of time where a metadata request is out then in"),
    ADD_STAT(totalDataReqTime, statistics::units::Tick::get(),
            "Total amount of time where a data request is out then in"),

    ADD_STAT(totalReqTimeDram, statistics::units::Tick::get(),
            "Total amount of time where a data request is out then in, "
            "for memory in DRAM (post-translation)"),
    ADD_STAT(totalReqTimeDramOs, statistics::units::Tick::get(),
            "Total amount of time where a data request is out then in, "
            "for (non-integrity) memory in DRAM (post-translation)"),
    ADD_STAT(totalReqTimeDramIntegrity, statistics::units::Tick::get(),
            "Total amount of time where a data request is out then in, "
            "for integrity memory in DRAM (post-translation)"),
    ADD_STAT(totalReqTimeCxl, statistics::units::Tick::get(),
            "Total amount of time where a data request is out then in, "
            "for memory in CXL (post-translation)"),
    ADD_STAT(totalReqTimeCxlOs, statistics::units::Tick::get(),
            "Total amount of time where a data request is out then in, "
            "for (non-integrity) memory in CXL (post-translation)"),
    ADD_STAT(totalReqTimeCxlIntegrity, statistics::units::Tick::get(),
            "Total amount of time where a data request is out then in, "
            "for integrity memory in CXL (post-translation)"),

    ADD_STAT(avgReqLatency, statistics::units::Tick::get(),
            "Average request latency from leaving to entering "
            "PageSwapper"),
    ADD_STAT(avgMetadataReqLatency, statistics::units::Tick::get(),
            "Average metadata request latency from leaving to entering "
            "IntegrityVerifier"),
    ADD_STAT(avgDataReqLatency, statistics::units::Tick::get(),
            "Average data request latency from leaving to entering "
            "IntegrityVerifier"),

    ADD_STAT(avgReqTimeDram, statistics::units::Tick::get(),
            "Average data request latency from leaving to entering "
            "IntegrityVerifier, for memory in DRAM (post-translation)"),
    ADD_STAT(avgReqTimeDramOs, statistics::units::Tick::get(),
            "Average data request latency from leaving to entering "
            "IntegrityVerifier, for (non-integrity) memory in DRAM "
            "(post-translation)"),
    ADD_STAT(avgReqTimeDramIntegrity, statistics::units::Tick::get(),
            "Average data request latency from leaving to entering "
            "IntegrityVerifier, for integrity memory in DRAM "
            "(post-translation)"),
    ADD_STAT(avgReqTimeCxl, statistics::units::Tick::get(),
            "Average data request latency from leaving to entering "
            "IntegrityVerifier, for memory in CXL (post-translation)"),
    ADD_STAT(avgReqTimeCxlOs, statistics::units::Tick::get(),
            "Average data request latency from leaving to entering "
            "IntegrityVerifier, for (non-integrity) memory in CXL "
            "(post-translation)"),
    ADD_STAT(avgReqTimeCxlIntegrity, statistics::units::Tick::get(),
            "Average data request latency from leaving to entering "
            "IntegrityVerifier, for integrity memory in CXL "
            "(post-translation)")
{
    avgSwapTime = totalSwapTime / totalSwapCount;

    avgReqLatency = totalReqTime / requestsHandled;
    avgMetadataReqLatency = totalMetadataReqTime / metadataReqHandled;
    avgDataReqLatency = totalDataReqTime / dataReqHandled;

    avgReqTimeDram = totalReqTimeDram / reqHandledDram;
    avgReqTimeDramOs = totalReqTimeDramOs / reqHandledDramOs;
    avgReqTimeDramIntegrity =
        totalReqTimeDramIntegrity / reqHandledDramIntegrity;
    avgReqTimeCxl = totalReqTimeCxl / reqHandledCxl;
    avgReqTimeCxlOs = totalReqTimeCxlOs / reqHandledCxlOs;
    avgReqTimeCxlIntegrity = totalReqTimeCxlIntegrity / reqHandledCxlIntegrity;
}


bool
AbstractPageSwapper::shouldHandlePacket(PacketPtr pkt)
{
    return (
        (dramFullRange.contains(pkt->getAddr()) ||
            cxlFullRange.contains(pkt->getAddr())) &&
        (pkt->isRead() || pkt->isWrite())
    );
}


std::string
AbstractPageSwapper::printPageTable()
{
    std::ostringstream str;

    ccprintf(str, "Page table:\n");
    for (auto it : pageTable) {
        Addr originalPage = it.first;
        Addr translatedPage = it.second;

        // Don't print linear mappings.
        if (originalPage == translatedPage) continue;

        // Make sure the reverse table is structured the way it should be.
        // assert(pageTableReverse[translatedPage] == originalPage);

        ccprintf(str, "[0x%014x -> 0x%014x]",
                originalPage, translatedPage);
        ccprintf(str, "[0x%014x -> 0x%014x]",
                translatedPage, pageTableReverse[translatedPage]);
        ccprintf(str, "%s\n",
                pageTableReverse[translatedPage] == originalPage ? "" : "(!)");
    }

    return str.str();
}



PageSwapper::PageSwapper(const PageSwapperParams &p)
    : AbstractPageSwapper(p),
      readReqDelay(p.read_req),
      readRespDelay(p.read_resp),
      writeReqDelay(p.write_req),
      writeRespDelay(p.write_resp)
{
}

Tick
PageSwapper::delayReq(PacketPtr pkt)
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
PageSwapper::delayResp(PacketPtr pkt)
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
