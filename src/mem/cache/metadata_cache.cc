#include "mem/cache/metadata_cache.hh"

#include <cstdlib>

#include "base/trace.hh"
#include "debug/MetadataCache.hh"
#include "debug/SimpleMetadataCache.hh"

namespace gem5
{
  // template <typename T>
  // CacheSet<T>::CacheSet(unsigned int ways) :
  CacheSet::CacheSet(unsigned int ways) :
    ways(ways)
  {
    // entries(ways, T());
    entries = std::vector<BasicCacheEntry*>();
    for (size_t i = 0; i < ways; i++) {
      entries.push_back(new BasicCacheEntry());
    }
  }


  // template <typename T>
  // CacheSet<T>::~CacheSet()
  CacheSet::~CacheSet()
  {
    // delete entries;
    for (auto e : entries) {
      delete e;
    }
  }


  // template <typename T>
  // MetadataCache<T>::MetadataCache(
  //    unsigned int set_count,
  //    unsigned int associativity
  // ) :
  MetadataCache::MetadataCache(
    unsigned int set_count,
    unsigned int associativity
  ) :
    associativity(associativity),
    set_count(set_count)
  {
    assert(set_count > 0);
    assert(associativity > 0);

    // sets(set_count, CacheSet<T>(associativity));
    // sets = new CacheSet<T>(associativity)[set_count];
    sets = std::vector<CacheSet*>();
    for (size_t i = 0; i < set_count; i++) {
      sets.push_back(new CacheSet(associativity));
    }

    // size_t setSize = T::entrySize() * associativity;
    size_t setSize = BasicCacheEntry::entrySize() * associativity;
    capacity = setSize * set_count;

    printInitDetails();
  }


  // template <typename T>
  // MetadataCache<T>::MetadataCache(
  //    size_t total_bytes,
  //    unsigned int associativity
  // ) :
  MetadataCache::MetadataCache(
    size_t total_bytes,
    unsigned int associativity
  ) :
    associativity(associativity)
  {
    assert(total_bytes > 0);
    assert(associativity > 0);

    // size_t setSize = associativity * T::entrySize();
    size_t setSize = associativity * BasicCacheEntry::entrySize();
    set_count = total_bytes / setSize;
    assert(set_count > 0);

    // sets = new CacheSet<T>(associativity)[set_count];
    // sets(set_count, CacheSet<T>(associativity));
    sets = std::vector<CacheSet*>();
    for (size_t i = 0; i < set_count; i++) {
      sets.push_back(new CacheSet(associativity));
    }

    // The capacity here may be different than the "requested" number in
    // total_bytes due to the fact that this might not evenly align with a
    // multiple of the entry size.
    capacity = setSize * set_count;

    printInitDetails();
  }


  // template <typename T>
  // MetadataCache<T>::~MetadataCache()
  MetadataCache::~MetadataCache()
  {
    // delete sets;
    for (auto s : sets) {
      delete s;
    }
  }

  void
  MetadataCache::printInitDetails()
  {
    DPRINTF(MetadataCache, "%s: Metadata cache initialized! Details:\n",
      __func__);
    DPRINTF(MetadataCache, "%s: Single entry size: %dB\n",
      __func__, BasicCacheEntry::entrySize());
    DPRINTF(MetadataCache, "%s: Total metadata cache size: %dB\n",
      __func__, capacity);
    DPRINTF(MetadataCache, "%s: Number of sets: %d\n",
      __func__, set_count);
    DPRINTF(MetadataCache, "%s: Associativity: %d\n",
      __func__, associativity);
  }


  SimpleMetadataCache::SimpleMetadataCache(unsigned int capacity) :
    capacity(capacity), dirty_lines(0), lines_pending_eviction(0),
    locked_lines(0), _tree(nullptr)
  {
    srand(time(0));
  }

  SimpleMetadataCache::SimpleMetadataCache(
    unsigned int capacity, TimingTree *tree
  ) : SimpleMetadataCache(capacity)
  {
    _tree = tree;
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
  SimpleMetadataCache::access(EntryKey data)
  {
    return contains(data);
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

  void
  SimpleMetadataCache::unlockDupeOkay(EntryKey data)
  {
    assert(contains(data));
    DPRINTF(SimpleMetadataCache, "%s: Unlocking line %llu.\n",
      __func__, data);

    if (!_data[data].locked) {
      DPRINTF(SimpleMetadataCache, "%s: %llu already unlocked.\n",
      __func__, data);
    } else {
      _data[data].locked = false;
      locked_lines--;
      DPRINTF(SimpleMetadataCache, "%s: locked_lines decreased to %d\n",
        __func__, locked_lines);
    }
  }

  SimpleMetadataCache::EntryKey
  SimpleMetadataCache::getLowestCachedAncestor(EntryKey data) {
    assert(_tree != nullptr);

    size_t index = data;
    while (index > 0) {
      index = _tree->parentBlockIndex(index);

      if (containsPendingOkay(index) && !_data[index].pending_eviction) {
        return index;
      }

      if (index == 0) {
        break;
      }
    }

    // If no such ancestor, return back `data`
    return data;
  }

  size_t
  SimpleMetadataCache::getSize()
  {
    return _data.size();
  }

  unsigned int SimpleMetadataCache::getDirtyLineCount()
  {
    return dirty_lines;
  }

  unsigned int SimpleMetadataCache::getPendingEvictionCount()
  {
    return lines_pending_eviction;
  }

  unsigned int SimpleMetadataCache::getLockedLineCount()
  {
    return locked_lines;
  }

  std::string
  SimpleMetadataCache::printLockedLines()
  {
      std::ostringstream str;

      ccprintf(str, "locked line count: %d\n", locked_lines);

      ccprintf(str, "locked: [");
      for (auto line : _data) {
        if (line.second.locked) {
          ccprintf(str, "%llu ", line.first);
        }
      }
      ccprintf(str, "]\n");

      return str.str();
  }

  bool
  SimpleMetadataCache::isFull()
  {
    return getSize() >= capacity;
  }

  bool
  SimpleMetadataCache::evictionCausesCircularDependencyWithIgnoredData(
    std::unordered_set<EntryKey> ignored_data,
    EntryKey potential_victim
  )
  {
    if (_tree == nullptr) {
      panic("This function cannot be called without initializing _tree.\n");
    }

    for (auto it : ignored_data) {
      if (it == 0) {
        continue;
      }

      if (it == potential_victim) {
        return true;
      }

      bool result = evictionCausesCircularDependencyWithIgnoredData(
        it, potential_victim);
      if (result) {
        return true;
      }
    }

    return false;
  }

  bool
  SimpleMetadataCache::evictionCausesCircularDependencyWithIgnoredData(
    EntryKey ignored_data,
    EntryKey potential_victim
  )
  {
    if (_tree == nullptr) {
      panic("This function cannot be called without initializing _tree.\n");
    }

    EntryKey ignored_data_parent = 0;
    if (ignored_data_parent != 0) {
      ignored_data_parent = _tree->parentBlockIndex(ignored_data);
    }

    EntryKey lowestCachedAncestor = getLowestCachedAncestor(potential_victim);

    return (
      _tree->isAncestor(ignored_data, potential_victim) &&
      (
        //lowestCachedAncestor == potential_victim ||
        lowestCachedAncestor == ignored_data ||
        lowestCachedAncestor == ignored_data_parent ||
        _tree->isAncestor(lowestCachedAncestor, ignored_data))
    );
  }

  std::pair<SimpleMetadataCache::EntryKey, SimpleMetadataCache::EntryValue>
  SimpleMetadataCache::evict(
    std::unordered_set<EntryKey> ignored_data,
    EntryKey replacement)
  {
    assert(getSize() > 0);

    // Calculate the number of cache lines that may be evicted.
    unsigned int potential_evicts = getSize()
                                      - lines_pending_eviction
                                      - locked_lines;

    // Change this number based on if the ignored data is in the cache.
    for (auto it : ignored_data) {
      if (contains(it)) {
        potential_evicts--;
      }
    }

    EntryKey replacementParent = 0;
    if (replacement != 0 && _tree != nullptr) {
      replacementParent = _tree->parentBlockIndex(replacement);
    }

    // Go through the cache and see if any nodes depend on something on the
    // ignore list.
    if (_tree != nullptr) {
      for (auto it : _data) {
        if (it.first != 0 &&
            !it.second.pending_eviction &&
            !it.second.locked &&
            ignored_data.find(it.first) == ignored_data.end() &&
            ignored_data.find(_tree->parentBlockIndex(it.first)) !=
                              ignored_data.end()) {
          // The parent of this node is in the ignore list.
          potential_evicts--;
          continue;
        } else if (it.first != 0 &&
            !it.second.pending_eviction &&
            !it.second.locked &&
            replacement != 0 &&
            _tree->isAncestor(replacement, it.first) &&
            getLowestCachedAncestor(it.first) == replacementParent
            ) {
          // Trying to evict this node would create a circular dependency for
          // this particular replacement.
          potential_evicts--;
          continue;
        }

        for (auto ignored : ignored_data) {
          if (it.first != 0 &&
            !it.second.pending_eviction &&
            !it.second.locked &&
            ignored != 0 &&
            ignored != it.first &&
            evictionCausesCircularDependencyWithIgnoredData(ignored, it.first))
          {
            potential_evicts--;
            break;
          }
        }
      }
    }

    assert(potential_evicts > 0);

    // For now, we will use random eviction.
    size_t randomIndex = rand() % potential_evicts;
    auto iterator = _data.begin();
    for (size_t i = 0; i < getSize();) {
      if (// Not an ignored cache line,
          ignored_data.find(iterator->first) == ignored_data.end() &&
          // Parent of this entry is not an ignored cache line,
          (_tree == nullptr ||
            iterator->first == 0 ||
            ignored_data.find(_tree->parentBlockIndex(iterator->first))
              == ignored_data.end()) &&
          // Trying to evict this entry would not create a circular dependency
          // for this particular replacement,
          (_tree == nullptr ||
            iterator->first == 0 ||
            replacement == 0 ||
            !_tree->isAncestor(replacement, iterator->first) ||
            getLowestCachedAncestor(iterator->first) != replacementParent) &&
          // Trying to evict this entry would not create a circular dependency
          // for any of the ignored data items,
          (_tree == nullptr ||
            iterator->first == 0 ||
            !evictionCausesCircularDependencyWithIgnoredData(
                ignored_data, iterator->first)) &&
          // Not pending eviction, and
          !iterator->second.pending_eviction &&
          // Not locked
          !iterator->second.locked)
      {
        // Count this as a potentially-selected item to evict.

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

  std::pair<SimpleMetadataCache::EntryKey, SimpleMetadataCache::EntryValue>
  SimpleMetadataCache::evict(std::unordered_set<EntryKey> ignored_data)
  {
    return evict(ignored_data, 0);
  }

  std::pair<SimpleMetadataCache::EntryKey, SimpleMetadataCache::EntryValue>
  SimpleMetadataCache::evict(EntryKey ignored_data)
  {
    std::unordered_set<EntryKey> _ignored_data;
    _ignored_data.insert(ignored_data);

    return evict(_ignored_data);
  }

  std::pair<SimpleMetadataCache::EntryKey, SimpleMetadataCache::EntryValue>
  SimpleMetadataCache::evict()
  {
    return evict(std::unordered_set<EntryKey>());
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
