#ifndef __MEM_PAGE_SWAPPER_HH__
#define __MEM_PAGE_SWAPPER_HH__

#include <queue>

#include "base/priority_queue_handled.hh"
#include "mem/qport.hh"
#include "params/AbstractPageSwapper.hh"
#include "params/PageSwapper.hh"
#include "sim/clocked_object.hh"
#include "sim/system.hh"

namespace gem5
{

/**
 * TODO Write documentation
 */
class AbstractPageSwapper : public ClockedObject
{

  public:
    AbstractPageSwapper(const AbstractPageSwapperParams &params);

    void init() override;

  protected: // Port interface
    Port &getPort(const std::string &if_name,
                  PortID idx=InvalidPortID) override;

    class RequestPort : public QueuedRequestPort
    {
      public:
        RequestPort(const std::string &_name, AbstractPageSwapper &_parent);

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
        AbstractPageSwapper& parent;
    };

    class ResponsePort : public QueuedResponsePort
    {
      public:
        ResponsePort(const std::string &_name, AbstractPageSwapper &_parent);

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
        AbstractPageSwapper& parent;

    };

    bool trySatisfyFunctional(PacketPtr pkt);

    /**
     * Keep a pointer to the system to allow querying memory properties.
     */
    System *system;

    /**
     * Size of page in bytes.
     */
    const Addr pageBytes;

    /**
     * Number of requests between swap attempts.
     */
    unsigned int swapEpoch;
    unsigned int reqsSinceLastSwap;

    RequestPort requestPort;
    ResponsePort responsePort;

    ReqPacketQueue reqQueue;
    RespPacketQueue respQueue;
    SnoopRespPacketQueue snoopRespQueue;

    /**
     * Used if a new request is generated.
     */
    RequestorID _requestorId;

    AddrRangeList dramFullRanges;
    AddrRangeList dramOsRanges;
    AddrRangeList dramIntegrityRanges;
    AddrRangeList cxlFullRanges;
    AddrRangeList cxlOsRanges;
    AddrRangeList cxlIntegrityRanges;

    /**
     * The time a swap started.
     *
     * This is used for statistics to determine how long a swap takes.
     */
    Tick swapStartTick;

    /**
     * Reverse search for a packet from its request pointer.
     *
     * This is also used as a list of all packets we are still expecting to
     * interact with in this component at some point.
     */
    std::unordered_map<RequestPtr, PacketPtr> packetLookup;

    /**
     * Track when each request arrives (when it is accepted).
     */
    std::unordered_map<RequestPtr, Tick> arrivalTime;

    /**
     * Requests that are ready to send.
     */
    std::unordered_set<RequestPtr> requestReady;

    /**
     * Responses that are ready to send.
     */
    std::unordered_set<RequestPtr> responseReady;

    /**
     * We must enforce that packets return in the same order that they were
     * received.
     */
    std::queue<RequestPtr> requestQueue;

    /**
     * We must enforce that packets return in the same order that they were
     * received.
     */
    std::queue<RequestPtr> responseQueue;

    /**
     * Packets that are being deferred until swapping is complete.
     *
     * NOTE: This assumes that the pre-address-translation queue will only
     * contain data for a single swap at a time.
     */
    std::queue<PacketPtr> preTranslationQueue;

    /**
     * Track when a packet arrived to the pre-address-translation queue,
     * to find out how long it was there.
     */
    std::unordered_map<PacketPtr, Tick> stallStartTime;

    /**
     * Contains the last tick that each page was accessed. If an entry does not
     * exist, it has not (yet) been accessed before.
     *
     * Note this is tracking the last access times of *translated* addresses.
     */
    // Max heap
    HandledPriorityQueue<Addr, Tick, std::less<Tick>> cxlPageLastAccessed;
    // Min heap
    HandledPriorityQueue<Addr, Tick, std::greater<Tick>> dramPageLastAccessed;

    /**
     * List of requests that must be fulfilled before we are permitted to swap.
     */
    std::unordered_set<RequestPtr> pendingReqForSwap;

    /**
     * Contains all address translation mappings.
     *
     * If an entry does not exist, the address maps to the same address. It
     * should then be added to the table for reference.
     */
    std::unordered_map<Addr, Addr> pageTable;

    /**
     * Reversed translation mappings.
     *
     * This allows translating back from the translated address to the original
     * address.
     */
    std::unordered_map<Addr, Addr> pageTableReverse;

    std::string printPageTable();

    std::string printDramPageHeap(size_t max = 16);
    std::string printCxlPageHeap(size_t max = 16);

    /**
     * Contains any mappings from DRAM to CXL memory.
     *
     * This should only contain starting addresses of pages.
     *
     * This is a mirror of cxlToDramMap.
     */
    // std::unordered_map<Addr, Addr> dramToCxlMap;

    /**
     * Contains any mappings from CXL memory to DRAM.
     *
     * This should only contain starting addresses of pages.
     *
     * This is a mirror of dramToCxlMap.
     */
    // std::unordered_map<Addr, Addr> cxlToDramMap;

    /**
     * Currently-ongoing swaps.
     *
     * The first item is the CXL page, the second item is the DRAM page.
     *
     * This is a mirror of dramToCxlSwaps.
     */
    std::unordered_map<Addr, Addr> cxlToDramSwaps;

    /**
     * Currently-ongoing swaps.
     *
     * The first item is the DRAM page, the second item is the CXL page.
     *
     * This is a mirror of cxlToDramSwaps.
     */
    std::unordered_map<Addr, Addr> dramToCxlSwaps;

    /**
     * Pages that are locked from processing further requests.
     *
     * Pages that are being swapped will temporarily be locked to avoid
     * conflicts. Incoming requests for locked pages will remain in a
     * pre-address-translation queue.
     */
    std::unordered_set<Addr> lockedPages;

    /**
     * Addresses of data that have not yet been retrieved during the swap
     * process.
     */
    std::unordered_set<Addr> pendingSwapRead;

    /**
     * Addresses of data (destination) that have not yet been edited during
     * the swap process.
     */
    std::unordered_set<Addr> pendingSwapWrite;

    /**
     * Data that is buffered during the swap process.
     *
     * This creates a mapping between the original address and the packet that
     * contains the data needed.
     */
    std::unordered_map<Addr, PacketPtr> savedSwapData;

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

    /**
     * Return if this integrity verifier has valid DRAM and CXL ranges stored.
     */
    bool hasValidRanges();

    /**
     * Get the address of the page that corresponds to an address.
     */
    Addr getPageAddr(Addr addr);

    /**
     * Get the address of the page that corresponds to a packet.
     */
    Addr getPageAddr(PacketPtr pkt);

    /**
     * Get the address of the CXL page that corresponds to a packet.
     *
     * Helpful when finding the pairing CXL page for a DRAM packet.
     */
    Addr getCxlPageAddr(PacketPtr pkt);

    /**
     * Schedule a request to go to memory.
     *
     * Requests will be mandated to be sent in the same order that they were
     * received in.
     *
     * NOTE: For data requests, it is expected that they have already been
     * added to `packetLookup`.
     */
    void schedReq(PacketPtr pkt);

    /**
     * Schedule a response to go to the CPU.
     *
     * Responses will be mandated to be sent in the same order they were
     * received in.
     */
    void schedResp(PacketPtr pkt);

    /**
     * Send a request to memory.
     *
     * The packet will be sent at the next available time.
     *
     * For data requests, this expects the packet to already be added to
     * `packetLookup`.
     */
    void sendReqToMem(PacketPtr pkt);

    /**
     * Send a response to the CPU.
     *
     * The packet will be sent at the next available time.
     *
     * This expects the packet to already be added to `packetLookup`.
     */
    void sendRespToCpu(PacketPtr pkt);

    /**
     * Make note of when a (request) packet is about to be scheduled for
     * sending to memory.
     *
     * This is used for finding timing information for how long packets take
     * before they return to this component.
     */
    void markReqStart(PacketPtr pkt);

    /**
     * Make node of when a (response) packet is accepted from memory.
     */
    void markReqEnd(PacketPtr pkt);

    /**
     * Add a pairing of a request pointer with a packet pointer. As the request
     * pointer is stored within the packet, only the packet is needed here.
     */
    void addToPacketLookup(PacketPtr pkt);

    /**
     * Update a pairing of a request pointer with a packet pointer.
     */
    void updatePacketLookup(PacketPtr pkt);

    /**
     * Remove a pairing of a request pointer with a packet pointer. As the
     * request pointer is stored within the packet, only the packet is needed
     * here.
     */
    void removeFromPacketLookup(PacketPtr pkt);

    bool handleReq(PacketPtr pkt);

    bool handleResp(PacketPtr pkt);

    /**
     * Mark a request as received by adding it to the proper tracking
     * structures.
     *
     * This should be called as soon as a request arrives.
     *
     * Associates a request with its packet and notes the arrival of the
     * request, so that the correct order may be maintained.
     */
    void markReqReceived(PacketPtr pkt);

    /**
     * Mark a response as received by ensuring it has arrived and update
     * the proper tracking structures.
     *
     * This should be called as soon as a response arrives.
     */
    void markRespReceived(PacketPtr pkt);

    /**
     * Count a page as accessed.
     *
     * Used for the purposes of finding candidates for pages to swap.
     */
    void countPageAccess(PacketPtr pkt);

    enum SwapProcessStage
    {
      DetermineSwapped,
      QueueReads,
      QueueWrites,
      Unlock
    };

    /**
     * Perform a page swap.
     */
    void performSwap();

    /**
     * Perform a page swap.
     *
     * @param stage Stage of the swap to perform.
     * @param cxlPageKey The address of the CXL page being swapped out. Used
     *                   to resume a swap from a specific stage.
     */
    void performSwap(SwapProcessStage stage, Addr cxlPageKey);

    /**
     * Determine which pages should be swapped.
     *
     * Part of the swapping process.
     *
     * @returns A pair, (starting address of CXL, starting address of DRAM),
     *          if there should be a swap. If no swap should be made, (0, 0)
     *          will be returned.
     */
    std::pair<Addr, Addr> determineSwappedPages();

    /**
     * Translate an address to the corresponding address based on the page
     * translation table.
     */
    Addr translateAddr(Addr addr, bool reverse);

    /**
     * Translate the address of a request into the translated page (if needed).
     */
    void translateReq(PacketPtr pkt);

    /**
     * Translate the address of a response into the original address
     * (if needed).
     */
    void translateResp(PacketPtr pkt);

    bool shouldHandlePacket(PacketPtr pkt);

  private:
    struct PageSwapperStats : public statistics::Group
    {
      PageSwapperStats(statistics::Group *parent);

      statistics::Scalar totalSwapCount;
      statistics::Scalar bytesSwapped;
      statistics::Scalar totalSwapTime;
      statistics::Formula avgSwapTime;

      // Measuring how long requests sit in a pre-translation-queue, because
      // they were requested during a page swap.

      statistics::Scalar totalStalled;
      statistics::Scalar totalSwapStallTime;
      statistics::Formula avgSwapStallTime;
      statistics::Scalar totalStalledOs;
      statistics::Scalar totalSwapStallTimeOs;
      statistics::Formula avgSwapStallTimeOs;
      statistics::Scalar totalStalledIntegrity;
      statistics::Scalar totalSwapStallTimeIntegrity;
      statistics::Formula avgSwapStallTimeIntegrity;

      // Number of pages swapped, given the original region label.

      statistics::Scalar pagesSwappedDramOs;
      statistics::Scalar pagesSwappedDramIntegrity;
      statistics::Scalar pagesSwappedCxlOs;
      statistics::Scalar pagesSwappedCxlIntegrity;

      // Number of accesses post-translation.

      statistics::Scalar accessesTransDram;
      statistics::Scalar accessesTransCxl;

      // Amount of requests or data that have been "improved" or "worsened"
      // by swaps.
      // "Improved" means a request for CXL is now coming from DRAM.
      // "Worsened" means a request for DRAM is now coming from CXL.
      // Then there are also subsets for these for just integrity data or
      // just application data.

      statistics::Scalar accessesImproved;
      statistics::Scalar bytesImproved;
      statistics::Scalar accessesImprovedOs;
      statistics::Scalar bytesImprovedOs;
      statistics::Scalar accessesImprovedIntegrity;
      statistics::Scalar bytesImprovedIntegrity;
      statistics::Scalar accessesUnaffected;
      statistics::Scalar bytesUnaffected;
      statistics::Scalar accessesUnaffectedOs;
      statistics::Scalar bytesUnaffectedOs;
      statistics::Scalar accessesUnaffectedIntegrity;
      statistics::Scalar bytesUnaffectedIntegrity;
      statistics::Scalar accessesWorsened;
      statistics::Scalar bytesWorsened;
      statistics::Scalar accessesWorsenedOs;
      statistics::Scalar bytesWorsenedOs;
      statistics::Scalar accessesWorsenedIntegrity;
      statistics::Scalar bytesWorsenedIntegrity;

      // DRAM swap page hit  = Page that was swapped into DRAM was accessed.
      // DRAM swap page miss = Page in DRAM (not swapped; in original place)
      //                       was accessed.
      // DRAM swap page hit rate = Rate of DRAM accesses that are a swapped
      //                           page.
      // These metrics use the post-translation address.
      //
      // Same for CXL; replace DRAM with CXL.

      statistics::Scalar swapPageHitsTransDram;
      statistics::Scalar swapPageMissesTransDram;
      statistics::Formula swapPageHitRateTransDram;
      statistics::Scalar swapPageHitsTransCxl;
      statistics::Scalar swapPageMissesTransCxl;
      statistics::Formula swapPageHitRateTransCxl;

      statistics::Scalar requestsHandled;
      statistics::Scalar bytesHandled;
      statistics::Scalar metadataReqHandled;
      statistics::Scalar metadataBytesHandled;
      statistics::Scalar dataReqHandled;
      statistics::Scalar dataBytesHandled;

      statistics::Scalar reqHandledPageSwap;
      statistics::Scalar reqHandledDram;
      statistics::Scalar reqHandledDramOs;
      statistics::Scalar reqHandledDramIntegrity;
      statistics::Scalar reqHandledCxl;
      statistics::Scalar reqHandledCxlOs;
      statistics::Scalar reqHandledCxlIntegrity;

      statistics::Scalar bytesHandledPageSwap;
      statistics::Scalar bytesHandledDram;
      statistics::Scalar bytesHandledDramOs;
      statistics::Scalar bytesHandledDramIntegrity;
      statistics::Scalar bytesHandledCxl;
      statistics::Scalar bytesHandledCxlOs;
      statistics::Scalar bytesHandledCxlIntegrity;

      statistics::Scalar reqHandledTransDram;
      statistics::Scalar reqHandledTransDramOs;
      statistics::Scalar reqHandledTransDramIntegrity;
      statistics::Scalar reqHandledTransCxl;
      statistics::Scalar reqHandledTransCxlOs;
      statistics::Scalar reqHandledTransCxlIntegrity;

      statistics::Scalar bytesHandledTransDram;
      statistics::Scalar bytesHandledTransDramOs;
      statistics::Scalar bytesHandledTransDramIntegrity;
      statistics::Scalar bytesHandledTransCxl;
      statistics::Scalar bytesHandledTransCxlOs;
      statistics::Scalar bytesHandledTransCxlIntegrity;

      statistics::Scalar totalReqTime;
      statistics::Scalar totalMetadataReqTime;
      statistics::Scalar totalDataReqTime;

      statistics::Scalar totalReqTimePageSwap;
      statistics::Scalar totalReqTimeDram;
      statistics::Scalar totalReqTimeDramOs;
      statistics::Scalar totalReqTimeDramIntegrity;
      statistics::Scalar totalReqTimeCxl;
      statistics::Scalar totalReqTimeCxlOs;
      statistics::Scalar totalReqTimeCxlIntegrity;

      statistics::Scalar totalReqTimeTransDram;
      statistics::Scalar totalReqTimeTransDramOs;
      statistics::Scalar totalReqTimeTransDramIntegrity;
      statistics::Scalar totalReqTimeTransCxl;
      statistics::Scalar totalReqTimeTransCxlOs;
      statistics::Scalar totalReqTimeTransCxlIntegrity;

      statistics::Formula avgReqLatency;
      statistics::Formula avgMetadataReqLatency;
      statistics::Formula avgDataReqLatency;

      statistics::Formula avgReqTimePageSwap;
      statistics::Formula avgReqTimeDram;
      statistics::Formula avgReqTimeDramOs;
      statistics::Formula avgReqTimeDramIntegrity;
      statistics::Formula avgReqTimeCxl;
      statistics::Formula avgReqTimeCxlOs;
      statistics::Formula avgReqTimeCxlIntegrity;

      statistics::Formula avgReqTimeTransDram;
      statistics::Formula avgReqTimeTransDramOs;
      statistics::Formula avgReqTimeTransDramIntegrity;
      statistics::Formula avgReqTimeTransCxl;
      statistics::Formula avgReqTimeTransCxlOs;
      statistics::Formula avgReqTimeTransCxlIntegrity;
    } stats;
};

/**
 * TODO Documentation
 */
class PageSwapper : public AbstractPageSwapper
{
  public:
    PageSwapper(const PageSwapperParams &params);

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

#endif //__MEM_PAGE_SWAPPER_HH__
