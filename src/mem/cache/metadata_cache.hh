#ifndef __MEM_CACHE_METADATA_CACHE_HH__
#define __MEM_CACHE_METADATA_CACHE_HH__

#include <cassert>
#include <cstddef>
#include <cstdint>
#include <type_traits>
#include <unordered_set>
#include <vector>

namespace gem5
{

class SimpleMetadataCache
{
  private:
    unsigned int capacity;
    unsigned int size;

    /**
     * Internal data structure.
     */
    std::unordered_set<uint64_t> data;

  public:
    SimpleMetadataCache(unsigned int capacity);

    ~SimpleMetadataCache();

    /**
     * Insert a piece of data to the metadata cache. If there is no space,
     * nothing will be inserted.
     *
     * @returns True if the insertion was successful, false otherwise.
     */
    bool insert(uint64_t new_data);

    /**
     * Check for the existence of `data` in the metadata cache.
     */
    bool contains(uint64_t data);

    size_t getSize();

    bool isFull();

    uint64_t evict();
};

} // namespace gem5

#endif // __MEM_CACHE_METADATA_CACHE_HH__
