/**
 * @file
 * Declaration of a coherent crossbar, with extra instrumentation.
 */

#ifndef __MEM_INSTRUMENTED_XBAR_HH__
#define __MEM_INSTRUMENTED_XBAR_HH__

#include "mem/coherent_xbar.hh"
#include "params/InstrumentedCoherentXBar.hh"

namespace gem5
{

/**
 * A coherent crossbar with extra instrumentation.
 */
class InstrumentedCoherentXBar : public CoherentXBar
{
  public:

    virtual void init();

    InstrumentedCoherentXBar(const InstrumentedCoherentXBarParams &p);

    virtual ~InstrumentedCoherentXBar();

    virtual void regStats();
};

} // namespace gem5

#endif //__MEM_INSTRUMENTED_XBAR_HH__
