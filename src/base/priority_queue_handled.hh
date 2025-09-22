#ifndef __BASE_PRIORITY_QUEUE_HANDLED_HH__
#define __BASE_PRIORITY_QUEUE_HANDLED_HH__

#include <cassert>
#include <unordered_map>
#include <vector>

namespace gem5 {

/**
 * Priority queue structure with handles.
 *
 * This can be considered a mix between a priority queue and a hash map, as
 * this provides a priority queue of key-value pairs. The value in the pair
 * determines the position in the queue, and the key can be used to retrieve
 * the value (or modify it).
 *
 * This allows accessing the top of the heap (i.e., max or min value, depending
 * on the comparator object used), as well as accessing an arbitrary element in
 * constant time. An arbitrary element in the heap can be
 * added/modified/removed in logarithmic time.
 *
 * Max heap is default configuration. Use std::greater for min heap.
 */
template<
    typename KeyType,
    typename ValueType,
    typename Compare = std::less<ValueType>
>
class HandledPriorityQueue
{
    public:
        struct Entry
        {
            KeyType handle;
            ValueType value;
        };

    private:
        // Heap/priority queue structure.
        std::vector<Entry> heap;

        /**
         * Mapping of handles/keys to the corresponding index in the heap.
         *
         * Allows accessing an arbitrary element in the heap in constant time.
         */
        std::unordered_map<KeyType, size_t> handleToIndex;

        /**
         * Comparator object.
         *
         * In essence, use std::less<ValueType> for a max heap (maximum value
         * at the top of the heap), or std::greater<ValueType> for a min heap
         * (minimum value at the top of the heap).
         */
        Compare comp;

        /**
         * Return true if `a` has higher priority than `b`.
         */
        bool isHigherPriority(const Entry& a, const Entry& b) const {
            return comp(b.value, a.value);
        }

        /**
         * Move an element up the heap until it is in the right position.
         */
        void heapifyUp(size_t i) {
            while (i > 0) {
                size_t parent = (i - 1) / 2;
                if (!isHigherPriority(heap[i], heap[parent])) break;
                swapNodes(i, parent);
                i = parent;
            }
        }

        /**
         * Move an element down the heap until it is in the right position.
         */
        void heapifyDown(size_t i) {
            size_t n = heap.size();
            while (true) {
                size_t left = 2*i + 1, right = 2*i + 2, best = i;
                if (left < n &&
                    isHigherPriority(heap[left], heap[best])) best = left;
                if (right < n &&
                    isHigherPriority(heap[right], heap[best])) best = right;
                if (best == i) break;
                swapNodes(i, best);
                i = best;
            }
        }

        /**
         * Swap two nodes by their index in the heap.
         */
        void swapNodes(size_t i, size_t j) {
            std::swap(heap[i], heap[j]);
            handleToIndex[heap[i].handle] = i;
            handleToIndex[heap[j].handle] = j;
        }

    public:
        HandledPriorityQueue(Compare c = Compare()) : comp(c) {}

        bool empty() const { return heap.empty(); }
        size_t size() const { return heap.size(); }
        bool contains(KeyType handle) const {
            return handleToIndex.find(handle) != handleToIndex.end();
        }

        const Entry& top() const {
            assert(!heap.empty());
            return heap.front();
        }

        /**
         * Add a new element to the priority queue.
         *
         * Does not expect duplicates.
         */
        void push(KeyType handle, ValueType val) {
            // assert(!contains(handle));
            heap.push_back({handle, val});
            handleToIndex[handle] = heap.size() - 1;
            heapifyUp(heap.size() - 1);
        }

        /**
         * Remove the top element.
         */
        void pop() {
            assert(!heap.empty());
            // assert(contains(handle));
            swapNodes(0, heap.size()-1);
            handleToIndex.erase(heap.back().handle);
            heap.pop_back();
            if (!heap.empty()) heapifyDown(0);
        }

        /**
         * Modify an element's value based on its handle/key.
         *
         * Assumes the element with the given handle exists.
         */
        void modify(KeyType handle, ValueType newVal) {
            // assert(contains(handle));
            size_t i = handleToIndex.at(handle);
            heap[i].value = newVal;
            heapifyUp(i);
            heapifyDown(i);
        }

        const Entry& getByHandle(KeyType handle) const {
            return heap.at(handleToIndex.at(handle));
        }

        const Entry& getByIndex(size_t index) const {
            return heap.at(index);
        }
};

} // namespace gem5

#endif //__BASE_PRIORITY_QUEUE_HANDLED_HH__
