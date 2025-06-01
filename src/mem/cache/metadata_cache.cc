#include "mem/cache/metadata_cache.hh"

#include <cstdlib>

#include "base/trace.hh"
#include "debug/MetadataCache.hh"
#include "debug/SimpleMetadataCache.hh"

namespace gem5
{
  SimpleMetadataCache::SimpleMetadataCache(unsigned int capacity) :
    capacity(capacity), dirty_lines(0), lines_pending_eviction(0),
    locked_lines(0)
  {
    srand(time(0));
  }

  SimpleMetadataCache::~SimpleMetadataCache()
  {

  }

  bool
  SimpleMetadataCache::insert(EntryKey new_data)
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

    EntryValue entry_value = {
      .dirty = false,
      .pending_eviction = false,
      .locked = false
    };
    _data.emplace(new_data, entry_value);
    DPRINTF(SimpleMetadataCache,
      "%s: Inserted %lu into metadata cache. (New size: %lu)\n",
      __func__, new_data, getSize());

    return true;
  }

  std::pair<SimpleMetadataCache::EntryKey, SimpleMetadataCache::EntryValue>
  SimpleMetadataCache::find(EntryKey search_data)
  {
    return *(_data.find(search_data));
  }

  bool
  SimpleMetadataCache::contains(EntryKey search_data)
  {
    auto search = _data.find(search_data);
    if (search != _data.end() && search->second.pending_eviction) {
      panic("Someone is checking for a cacheline that is pending eviction.");
    }

    return (search != _data.end());
  }

  bool
  SimpleMetadataCache::containsPendingOkay(EntryKey search_data)
  {
    auto search = _data.find(search_data);
    return (search != _data.end());
  }

  void
  SimpleMetadataCache::modify(EntryKey modified_data)
  {
    assert(contains(modified_data));
    assert(!find(modified_data).second.pending_eviction);

    if (_data[modified_data].dirty) {
      // This data is already marked dirty. Do nothing.
      DPRINTF(SimpleMetadataCache,
        "%s: Dirty cache entry %llu is modified again.\n",
        __func__, modified_data);
      return;
    }

    // Mark the data item as dirty.
    _data[modified_data].dirty = true;
    dirty_lines++;

    DPRINTF(SimpleMetadataCache, "%s: Dirty lines count increased to %u\n",
      __func__, dirty_lines);
  }

  void
  SimpleMetadataCache::lock(EntryKey data)
  {
    assert(contains(data));
    assert(!_data[data].locked);

    DPRINTF(SimpleMetadataCache, "%s: Locking line %llu.\n",
      __func__, data);
    _data[data].locked = true;
    locked_lines++;
    DPRINTF(SimpleMetadataCache, "%s: locked_lines increased to %d\n",
      __func__, locked_lines);
  }

  void
  SimpleMetadataCache::lockDupeOkay(EntryKey data)
  {
    assert(contains(data));
    DPRINTF(SimpleMetadataCache, "%s: Locking line %llu.\n",
      __func__, data);

    if (_data[data].locked) {
      DPRINTF(SimpleMetadataCache, "%s: %llu already locked.\n",
      __func__, data);
    } else {
      _data[data].locked = true;
      locked_lines++;
      DPRINTF(SimpleMetadataCache, "%s: locked_lines increased to %d\n",
        __func__, locked_lines);
    }
  }

  void
  SimpleMetadataCache::unlock(EntryKey data)
  {
    assert(contains(data));
    assert(_data[data].locked);

    DPRINTF(SimpleMetadataCache, "%s: Unlocking line %llu.\n",
      __func__, data);
    _data[data].locked = false;
    locked_lines--;
    DPRINTF(SimpleMetadataCache, "%s: locked_lines decreased to %d\n",
      __func__, locked_lines);
  }

  size_t
  SimpleMetadataCache::getSize()
  {
    return _data.size();
  }

  bool
  SimpleMetadataCache::isFull()
  {
    return getSize() >= capacity;
  }

  std::pair<SimpleMetadataCache::EntryKey, SimpleMetadataCache::EntryValue>
  SimpleMetadataCache::evict(EntryKey ignored_data)
  {
    assert(getSize() > 0);

    // Calculate the number of cache lines that may be evicted.
    unsigned int potential_evicts = getSize()
                                      - lines_pending_eviction
                                      - locked_lines;

    // Change this number based on if the ignored data is in the cache.
    if (contains(ignored_data)) {
      potential_evicts--;
    }
    assert(potential_evicts > 0);

    // For now, we will use random eviction. No dirty lines will be evicted.
    size_t randomIndex = rand() % potential_evicts;
    auto iterator = _data.begin();
    for (size_t i = 0; i < getSize();) {
      if (iterator->first != ignored_data &&
          !iterator->second.pending_eviction &&
          !iterator->second.locked) {
        // If this is not an ignored cache line, the line isn't already pending
        // eviction, and the line isn't locked, count this as a
        // potentially-selected item to evict.
        if (i == randomIndex) {
          // We have found the element we are looking for.
          break;
        }
        i++;
      }

      iterator++;
    }
    assert(!iterator->second.pending_eviction);
    // The iterator is now on the element to remove.

    auto evictedData = iterator->first;
    auto dirty = iterator->second.dirty;

    DPRINTF(SimpleMetadataCache,
      "%s: %lld selected for eviction.\n",
      __func__, evictedData);

    if (!dirty) {
      // If this line is clean, we can just evict this without issue.
      DPRINTF(SimpleMetadataCache,
        "%s: %lld is clean and can be evicted now.\n",
        __func__, evictedData);
      _data.erase(iterator);
    } else {
      // If this line is dirty, the eviction is marked as pending, as
      // additional checks by the caller should be made.
      DPRINTF(SimpleMetadataCache,
        "%s: %lld is dirty. Marking as pending eviction.\n",
        __func__, evictedData);
      iterator->second.pending_eviction = true;
      lines_pending_eviction++;
      // _data.emplace(iterator->first, iterator->second);
    }

    // Returns a copy of this entry in the metadata cache.
    return *iterator;
  }

  void
  SimpleMetadataCache::finishEvict(EntryKey evicted_data)
  {
    // The data we're evicting should actually be in the cache.
    assert(containsPendingOkay(evicted_data));

    auto iterator = _data.find(evicted_data);
    assert(iterator != _data.end());
    assert(iterator->second.pending_eviction);

    auto dirty = iterator->second.dirty;
    assert(dirty);

    _data.erase(iterator);
    lines_pending_eviction--;

    dirty_lines--;
    DPRINTF(SimpleMetadataCache, "%s: Dirty lines count decreased to %u\n",
      __func__, dirty_lines);

    DPRINTF(SimpleMetadataCache,
      "%s: %llu evicted. Lines pending eviction: %u\n",
      __func__, evicted_data, lines_pending_eviction);
  }

} // namespace gem5
