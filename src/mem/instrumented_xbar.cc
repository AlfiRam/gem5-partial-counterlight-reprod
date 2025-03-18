/**
 * @file
 * Definition of a crossbar object.
 */

#include "mem/instrumented_xbar.hh"

#include "base/compiler.hh"
#include "base/logging.hh"
#include "base/trace.hh"
#include "debug/AddrRanges.hh"
#include "debug/CoherentXBar.hh"
#include "sim/system.hh"

namespace gem5
{

InstrumentedCoherentXBar
    ::InstrumentedCoherentXBar(const InstrumentedCoherentXBarParams &p)
    : CoherentXBar(p)
{

}

InstrumentedCoherentXBar::~InstrumentedCoherentXBar()
{

}

void
InstrumentedCoherentXBar::init()
{
    CoherentXBar::init();
}


void
InstrumentedCoherentXBar::regStats()
{
    CoherentXBar::regStats();
}

} // namespace gem5
