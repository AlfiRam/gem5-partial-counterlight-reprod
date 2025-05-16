#include "mem/cache/metadata_cache.hh"

#include <cstdlib>

#include "base/trace.hh"
#include "debug/MetadataCache.hh"
#include "debug/SimpleMetadataCache.hh"

namespace gem5
{
  SimpleMetadataCache::SimpleMetadataCache(unsigned int capacity) :
    capacity(capacity), size(0)
  {
    srand(time(0));
  }

  SimpleMetadataCache::~SimpleMetadataCache()
  {

  }

  bool
  SimpleMetadataCache::insert(uint64_t new_data)
  {
    if (isFull()) {
      // The cache is full. Do not insert more.
      DPRINTF(SimpleMetadataCache,
        "%s: Cannot insert %lu into metadata cache. Full. (Size: %lu)\n",
      __func__, new_data, getSize());
      return false;
    }

    // The data should not yet exist in the cache already.
    assert(!contains(new_data));

    data.insert(new_data);
    DPRINTF(SimpleMetadataCache,
      "%s: Inserted %lu into metadata cache. (New size: %lu)\n",
      __func__, new_data, getSize());

    return true;
  }

  bool
  SimpleMetadataCache::contains(uint64_t search_data)
  {
    return (data.find(search_data) != data.end());
  }

  size_t
  SimpleMetadataCache::getSize()
  {
    return data.size();
  }

  bool
  SimpleMetadataCache::isFull()
  {
    return getSize() >= capacity;
  }

  uint64_t
  SimpleMetadataCache::evict()
  {
    assert(getSize() > 0);

    // For now, we will use random eviction.
    size_t randomIndex = rand() % getSize();
    auto iterator = data.begin();
    for (size_t i = 0; i < randomIndex; i++) {
      iterator++;
    }
    // The iterator is now on the element to remove.

    uint64_t evictedData = *iterator;

    data.erase(iterator);

    return evictedData;
  }

} // namespace gem5
