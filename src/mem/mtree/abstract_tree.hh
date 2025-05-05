#ifndef __MEM_MTREE_ABSTRACT_TREE_HH__
#define __MEM_MTREE_ABSTRACT_TREE_HH__

#include <cstddef>
#include <vector>

namespace gem5 {

class AbstractIntegrityTree
{
  public:
    ////// Basic Functionality //////

    virtual ~AbstractIntegrityTree() {};

    virtual void processWrite(
      size_t address,
      std::vector<unsigned char> newData
    ) = 0;

    /**
     * Returns whether this tree is actually storing data, or is just here to
     * simulate other properties about the tree.
     */
    virtual bool isMocking() = 0;
};

} // namespace gem5

#endif // __MEM_MTREE_ABSTRACT_TREE_HH__
