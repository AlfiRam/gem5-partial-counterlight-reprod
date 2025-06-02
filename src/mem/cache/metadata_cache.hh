#ifndef __MEM_CACHE_METADATA_CACHE_HH__
#define __MEM_CACHE_METADATA_CACHE_HH__

#include <cassert>
#include <cstddef>
#include <cstdint>
#include <type_traits>
#include <unordered_map>
#include <unordered_set>
#include <vector>

#include "mem/mtree/timing_tree.hh"

namespace gem5
{

class SimpleMetadataCache
{
  public:
    typedef uint64_t EntryKey;
    typedef struct
    {
      bool dirty;
      bool pending_eviction;
      bool locked;
    } EntryValue;

  private:
    unsigned int capacity;

    /**
     * Internal data structure.
     */
    std::unordered_map<EntryKey, EntryValue> _data;

    /**
     * Internal count for the number of dirty cache lines in the metadata
     * cache.
     */
    unsigned int dirty_lines;

    /**
     * Internal count for the number of cache lines in the metadata cache that
     * are currently pending eviction. These lines can be considered
     * inaccessible until they are properly evicted.
     */
    unsigned int lines_pending_eviction;

    /**
     * Internal count for the number of cache lines that are locked and cannot
     * be evicted. This is the case if a cache line is depended on by another
     * cache line that is pending insertion.
     */
    unsigned int locked_lines;

    /**
     * Reference to integrity tree. Can be helpful for finding certain
     * relationships between nodes.
     */
    TimingTree *_tree;

  public:
    SimpleMetadataCache(unsigned int capacity);

    SimpleMetadataCache(unsigned int capacity, TimingTree *tree);

    ~SimpleMetadataCache();

    /**
     * Insert a piece of data to the metadata cache. If there is no space,
     * nothing will be inserted.
     *
     * @returns True if the insertion was successful, false otherwise.
     */
    bool insert(EntryKey new_data);

    std::pair<EntryKey, EntryValue> find(EntryKey new_data);

    /**
     * Check for the existence of `data` in the metadata cache.
     */
    bool contains(EntryKey data);

    /**
     * Check for the existence of `data` in the metadata cache.
     *
     * Do not panic if the data being checked is pending eviction.
     */
    bool containsPendingOkay(EntryKey data);

    /**
     * Simulate modification of a cache line by specifying the entry to edit.
     * This will cause the line to be marked as dirty.
     *
     * This assumes that `data` already exists in the cache.
     */
    void modify(EntryKey modified_data);

    /**
     * Lock a node to prevent it from being evicted.
     */
    void lock(EntryKey data);

    /**
     * Lock a node, but do not panic if this is called on an already-locked
     * node.
     */
    void lockDupeOkay(EntryKey data);

    /**
     * Unlock a node to allow it to be evicted.
     */
    void unlock(EntryKey data);

    /**
     * Unlock a node, but do not panic if this is called on an already-unlocked
     * node.
     */
    void unlockDupeOkay(EntryKey data);

    size_t getSize();

    unsigned int getDirtyLineCount();

    unsigned int getPendingEvictionCount();

    unsigned int getLockedLineCount();

    bool isFull();

    /**
     * Evict a random cache line from the metadata cache. If the selected cache
     * line is dirty, then it will be marked as 'pending eviction', and require
     * the caller to perform additional checks as needed and call
     * `finishEvict(evicted_data)`, where `evicted_data` is
     * `evict(...).first`.
     *
     * It is guaranteed that a line already pending eviction will not be
     * selected for eviction.
     *
     * @param ignored_data Data that should not be evicted.
     * @return The data that was evicted. Note that if the entry returned has
     *         the 'pending eviction' flag set to true, the eviction is not
     *         complete.
     */
    std::pair<EntryKey, EntryValue> evict(
      std::unordered_set<EntryKey> ignored_data);

    std::pair<EntryKey, EntryValue> evict(EntryKey ignored_data);

    std::pair<EntryKey, EntryValue> evict();

    /**
     * Finish an eviction as followed from `evict()`.
     */
    void finishEvict(EntryKey evicted_data);
};

} // namespace gem5

#endif // __MEM_CACHE_METADATA_CACHE_HH__
