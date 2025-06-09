"""
This simulation boots Ubuntu 24.04 using 2 KVM CPUs without using perf.
This is a simple sanity test config for full system emulation.

Based on x86-ubuntu-run-with-kvm-no-perf.py

Usage
-----

```
scons build/X86/gem5.opt -j`nproc`
./build/X86/gem5.opt configs/integrity_verifier/basic-demo.py
```
"""

import argparse

from create_board import *

from gem5.resources.resource import obtain_resource
from gem5.simulate.exit_event import ExitEvent
from gem5.simulate.simulator import Simulator

# Argument parsing.
parser = argparse.ArgumentParser(
    description="Demonstration integrity verifier test."
)
add_arguments(parser)
args = parser.parse_args()

board, processor = create_board(args)

workload = obtain_resource(
    resource_id="x86-ubuntu-24.04-boot-no-systemd", resource_version="3.0.0"
)
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
