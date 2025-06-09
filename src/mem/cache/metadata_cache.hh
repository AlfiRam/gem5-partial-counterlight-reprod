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

/**
 * Basic class that represents a cache entry. This allows the entry to be
 * flexible and implement other functionality or data (i.e., counters).
 */
class AbstractCacheEntry
{
  private:
    /**
     * Whether or not this entry contains valid data.
     */
    bool valid;

    /**
     * Whether or not this entry is dirty (modified).
     */
    bool dirty;

  public:
    AbstractCacheEntry() {};
    virtual ~AbstractCacheEntry() {};

    /**
     * Return the size (in bytes) that one cache entry takes.
     */
    static size_t entrySize() { return 0; }
};


class BasicCacheEntry : public AbstractCacheEntry
{
  private:
    /**
     * Each cache entry is simply an ID to a Merkle tree block (for now).
     *
     * However, if this was a real cache, we would be storing the block itself.
     */
    size_t mtBlock;

  public:
    BasicCacheEntry() {};
    ~BasicCacheEntry() {};

    /**
     * Return the size (in bytes) that one cache entry takes. Rounded up to the
     * nearest byte when necessary.
     *
     * For this cache entry type, you store the following:
     *   - Valid bit (1 bit)
     *   - Dirty bit (1 bit)
     *   - Merkle tree node (size of one cacheline = 64 bytes)
     *   - Tree node ID (technically this is 8 bytes at most, but really
     *     depends on the size of the tree)
     */
    static size_t entrySize() { return 1 + 64 + 8; }
};


// template <typename T>
class CacheSet
{
  // static_assert(std::is_base_of<AbstractCacheEntry, T>::value,
  //    "CacheSet type T must derive from AbstractCacheEntry.");

  private:
    unsigned int ways;

    // std::vector<T> entries;
    std::vector<BasicCacheEntry*> entries;

  public:
    CacheSet(unsigned int ways);

    ~CacheSet();
};


/**
 * A basic metadata cache. This can store an arbitrary class that derives
 * AbstractCacheEntry.
 */
// template <typename T>
class MetadataCache
{
  // static_assert(std::is_base_of<AbstractCacheEntry, T>::value,
  //    "CacheSet type T must derive from AbstractCacheEntry.");

  private:
    unsigned int associativity;
    unsigned int set_count;

    /**
     * Size of how much data can be stored in total (in bytes).
     */
    unsigned int capacity;

    /**
     * Individual sets being stored.
     */
    // std::vector<CacheSet<T>> sets;
    std::vector<CacheSet*> sets;

    unsigned int read_buffer_capacity;
    std::vector<BasicCacheEntry*> read_buffer;



  public:
    // Constructor based on sets and associativity
    MetadataCache(unsigned int set_count, unsigned int associativity);

    // Constructor based on total size (and entry size)
    MetadataCache(size_t total_bytes, unsigned int associativity);


    ~MetadataCache();

    void printInitDetails();

    // Returns whether or not something was evicted.
    // bool insert(size_t data);
};

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
     * Mock the access of a metadata cache entry.
     *
     * @returns True if cache hit, false if cache miss.
     */
    bool access(EntryKey data);

    /**
     * Check for the existence of `search_data` in the metadata cache.
     */
    bool contains(EntryKey search_data);

    /**
     * Check for the existence of `search_data` in the metadata cache.
     *
     * Do not panic if the data being checked is pending eviction.
     */
    bool containsPendingOkay(EntryKey search_data);

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

    /**
     * Return the lowest cached entry that is an ancestor of `data`. If no
     * entry exists, `data` is returned back.
     */
    EntryKey getLowestCachedAncestor(EntryKey data);

    size_t getSize();

    unsigned int getDirtyLineCount();

    unsigned int getPendingEvictionCount();

    unsigned int getLockedLineCount();

    std::string printLockedLines();

    bool isFull();

    bool evictionCausesCircularDependencyWithIgnoredData(
      std::unordered_set<EntryKey> ignored_data,
      EntryKey potential_victim
    );

    bool evictionCausesCircularDependencyWithIgnoredData(
      EntryKey ignored_data,
      EntryKey potential_victim
    );

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
     * @param replacement The node that is intended to replace the evicted
     *                    cache line. If no replacement is specified, `0` can
     *                    be used to indicate the replacement.
     * @return The data that was evicted. Note that if the entry returned has
     *         the 'pending eviction' flag set to true, the eviction is not
     *         complete.
     */
    std::pair<EntryKey, EntryValue> evict(
      std::unordered_set<EntryKey> ignored_data, EntryKey replacement);

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
