# Copyright (c) 2023 The Regents of the University of California
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met: redistributions of source code must retain the above copyright
# notice, this list of conditions and the following disclaimer;
# redistributions in binary form must reproduce the above copyright
# notice, this list of conditions and the following disclaimer in the
# documentation and/or other materials provided with the distribution;
# neither the name of the copyright holders nor the names of its
# contributors may be used to endorse or promote products derived from
# this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

"""

This simulation boots Ubuntu 24.04 using 2 KVM CPUs without using perf.
This is a simple sanity test config for full system emulation.

Based on x86-ubuntu-run-with-kvm-no-perf.py

Usage
-----

```
scons build/X86/gem5.opt -j`nproc`
./build/X86/gem5.opt configs/example/gem5_library/x86-ubuntu-test-classiccache.py
```
"""

import argparse

import m5
from m5.objects import (
    BadAddr,
    SystemXBar,
)

from gem5.coherence_protocol import CoherenceProtocol
from gem5.components.boards.x86_board import X86Board
from gem5.components.cachehierarchies.classic.private_l1_shared_l2_cache_hierarchy import (
    PrivateL1SharedL2CacheHierarchy,
)
from gem5.components.cachehierarchies.classic.private_l1_shared_l2_cache_hierarchy_integrity_verifier import (
    PrivateL1SharedL2CacheHierarchyIntegrityVerifier,
)
from gem5.components.memory.single_channel import DIMM_DDR5_4400
from gem5.components.processors.cpu_types import CPUTypes
from gem5.components.processors.simple_processor import SimpleProcessor
from gem5.components.processors.simple_switchable_processor import (
    SimpleSwitchableProcessor,
)
from gem5.isas import ISA
from gem5.resources.resource import obtain_resource
from gem5.simulate.exit_event import ExitEvent
from gem5.simulate.simulator import Simulator
from gem5.utils.requires import requires

# This simulation requires using KVM with gem5 compiled for X86 simulation
requires(
    isa_required=ISA.X86,
    kvm_required=True,
)

# Argument parsing.
parser = argparse.ArgumentParser(
    description="Demonstration integrity verifier test."
)

parser.add_argument(
    "--use-integrity-verifier",
    action="store_true",
    help="Add an 'integrity verifier' component to add integrity management behavior.",
)

parser.add_argument(
    "--timing-from-start",
    action="store_true",
    help="Instead of switching from KVM cores to timing cores when reaching the POI, use timing cores starting at boot.",
)

parser.add_argument(
    "--metadata-cache-size",
    type=int,
    required=False,
    help="Number of entries in the metadata cache, if applicable.",
    default=2048,
)

args = parser.parse_args()


# Main memory
memory = DIMM_DDR5_4400(size="3GiB")

membus = SystemXBar(width=64)
membus.badaddr_responder = BadAddr()
membus.default = membus.badaddr_responder.pio

# Cache
if args.use_integrity_verifier:
    cache_hierarchy = PrivateL1SharedL2CacheHierarchyIntegrityVerifier(
        l1d_size="32KiB",
        l1d_assoc=8,
        l1i_size="32KiB",
        l1i_assoc=8,
        l2_size="512KiB",
        l2_assoc=16,
        membus=membus,
        metadata_cache_size=args.metadata_cache_size,
    )
else:
    cache_hierarchy = PrivateL1SharedL2CacheHierarchy(
        l1d_size="32KiB",
        l1d_assoc=8,
        l1i_size="32KiB",
        l1i_assoc=8,
        l2_size="512KiB",
        l2_assoc=16,
        membus=membus,
    )


if not args.timing_from_start:
    # This is a switchable CPU. We first boot Ubuntu using KVM, then the guest
    # will exit the simulation by calling "m5 exit" (see the `command` variable
    # below, which contains the command to be run in the guest after booting).
    # Upon exiting from the simulation, the Exit Event handler will switch the
    # CPU type (see the ExitEvent.EXIT line below, which contains a map to
    # a function to be called when an exit event happens).
    processor = SimpleSwitchableProcessor(
        starting_core_type=CPUTypes.KVM,
        switch_core_type=CPUTypes.TIMING,
        isa=ISA.X86,
        num_cores=2,
    )

    # Here we tell the KVM CPU (the starting CPU) not to use perf.
    for proc in processor.start:
        proc.core.usePerf = False
else:
    # Example of a processor that starts in timing mode, rather than switching to timing after boot.
    processor = SimpleProcessor(
        cpu_type=CPUTypes.TIMING, isa=ISA.X86, num_cores=2
    )

# Here we setup the board. The X86Board allows for Full-System X86 simulations.
board = X86Board(
    clk_freq="3GHz",
    processor=processor,
    memory=memory,
    cache_hierarchy=cache_hierarchy,
)

workload = obtain_resource("x86-ubuntu-24.04-boot-with-systemd")
board.set_workload(workload)


def exit_event_handler():
    print("First exit: kernel booted")
    yield False  # gem5 is now executing systemd startup
    print("Second exit: Started `after_boot.sh` script")
    # The after_boot.sh script is executed after the kernel and systemd have
    # booted.
    if not args.timing_from_start:
        # Here we switch the CPU type to Timing.
        print("Switching to Timing CPU")
        processor.switch()
    yield False  # gem5 is now executing the `after_boot.sh` script
    print("Third exit: Finished `after_boot.sh` script")
    # The after_boot.sh script will run a script if it is passed via
    # m5 readfile. This is the last exit event before the simulation exits.
    yield True


simulator = Simulator(
    board=board,
    on_exit_event={
        # Here we want override the default behavior for the first m5 exit
        # exit event.
        ExitEvent.EXIT: exit_event_handler()
    },
)

simulator.run()
