# Full-system emulation example using Ubuntu 22.04 and the latest version of
# gem5, at the time of writing. This is an experimental file for the purposes
# of learning.
#
# This configuration will boot Ubuntu 22.04 using KVM cores, then after
# finishing, switch to the more accurate timing cores.
#
# This config file is based on
# configs/example/gem5_library/x86-ubuntu-run-with-kvm-no-perf.py

"""
Script to run simple microbenchmarks with gem5.
The script expects a benchmark program name and the simulation
size.

This script will count the total number of instructions executed
in the ROI. It also tracks how much wallclock and simulated time.

Usage:
------

```
scons build/X86/gem5.opt
./build/X86/gem5.opt <script> \
    --benchmark <benchmark_name>
```
"""

import argparse
import time

from create_board import *

import m5

from gem5.resources.resource import (
    DiskImageResource,
    KernelResource,
    obtain_resource,
)
from gem5.simulate.exit_event import ExitEvent
from gem5.simulate.simulator import Simulator

# Following are the list of microbenchmark programs.
benchmark_choices = [
    "widepass",
    "widerandom",
]

# Argument parsing.
parser = argparse.ArgumentParser(description="Microbenchmark runner for gem5.")
add_arguments(parser)


parser.add_argument(
    "--benchmark",
    type=str,
    required=True,
    help="Input the benchmark program to execute.",
    choices=benchmark_choices,
)

parser.add_argument(
    "--page-size", type=int, required=True, help="Page size in bytes."
)

parser.add_argument(
    "--page-count", type=int, required=True, help="Number of pages."
)

parser.add_argument(
    "--passes", type=int, required=True, help="Number of passes."
)

parser.add_argument(
    "--seed",
    type=int,
    required=False,
    default=0,
    help="Seed for random number generation (0 for time-based seed).",
)

parser.add_argument(
    "--no-stop-after-roi",
    action="store_true",
    help="Stop the simulation after all commands are completely finished, not just at the end of the ROI. Helpful for debugging or getting extra output.",
)

parser.add_argument(
    "--resource",
    type=str,
    required=False,
    help="Specify a custom workload resource to use.",
    default="x86-microbenchmarks-ubuntu-22-04",
)

parser.add_argument(
    "--resource-version",
    type=str,
    required=False,
    help="Version for custom resource.",
    default="1.0.2",
)

parser.add_argument(
    "--kernel-path",
    type=str,
    required=False,
    help="Specify a path to a custom kernel to use. This must be used in combination with --img-path.",
)

parser.add_argument(
    "--img-path",
    type=str,
    required=False,
    help="Specify a path to a custom disk image to use. This must be used in combination with --kernel-path.",
)
args = parser.parse_args()

board, processor = create_board(args)

# This is the command to run after the system has booted. The first `m5 exit`
# written here (which is really the third exit in total from the start of
# boot) will signal that we have finished booting. During the simulation or
# after it ends, you may inspect `m5out/system.pc.com_1.device` to see the
# emulated echo output.
command = (
    "m5 exit;"  # Third exit event
    + "cd microbenchmarks;"
    # Arguments: <page_size> <pages> <passes> <show_progress: 0 or 1> <progress_frequency> <use_m5: 0 or 1> <seed: 0 for TIME, else to set>
    + f'echo "12345" | ./{args.benchmark} {args.page_size} {args.page_count} {args.passes} 1 10 1 {args.seed};'
    # The end of ROI hook will stop the simulation from here.
    + "sleep 5;"  # This delay is to allow any print statements to finish before the simulation abruptly stops.
    + "m5 exit;"
    # + "echo 'Workload complete. Exiting.';"
    # + "sleep 10;" # This delay is here to prevent gem5 from exploding. If you do an `m5 exit` too quick, you might stop before things are actually ready to stop.
    # + "m5 exit;" # "Fourth" exit event
)

# Check if a custom kernel and disk image pair are used.
if args.kernel_path and not args.img_path:
    print(
        "It appears you provided a kernel with no disk image. Make sure to add the --img-path option."
    )
    print("Stopping.")
    quit()
elif not args.kernel_path and args.img_path:
    print(
        "It appears you provided a disk image with no kernel. Make sure to add the --kernel-path option."
    )
    print("Stopping.")
    quit()

if args.kernel_path and args.img_path:
    # We are using a manual kernel and disk image.
    #
    # Assistance from configs/example/gem5_library/x86-cxl-run.py in CXL-DMSim.
    board.set_kernel_disk_workload(
        kernel=KernelResource(local_path=args.kernel_path),
        disk_image=DiskImageResource(local_path=args.img_path),
        readfile_contents=command,
        kernel_args=[
            "earlyprintk=ttyS0",
            "console=ttyS0",
            "lpj=7999923",
            "root=/dev/sda2",
            "no_systemd=true",
        ],
    )
else:
    # We are using a workload resource.
    #
    # Here we set the Full System workload.
    # More information about the Ubuntu image is located at:
    # https://github.com/gem5/gem5-resources/tree/44455adfdb5451c5d2a5b4fd921a00cb8cc2a9c0/src/x86-ubuntu
    # The file 'x86-ubuntu.pkr.hcl' is for Ubuntu 22.04.2.
    workload = obtain_resource(
        args.resource, resource_version=args.resource_version
    )
    workload.set_parameter("readfile_contents", command)
    board.set_workload(workload)


# Define what happens when `m5 exit` is received. The exact number of exit
# events necessary before switching processors is related to the structure
# of the Ubuntu 22.04 image.
# Returning `false` means to continue the simulation.
# Returning `true` means to stop the simulation.
def handle_exit_event():
    print("Caught first exit event: Kernel booted.")
    yield False

    print("Caught second exit event: Running after_boot script.")
    yield False

    print(
        "Caught third exit event: Finished run script and reading script file."
    )
    yield False

    print("Caught fourth exit event: After workload finished.")
    yield True


def handle_workbegin():
    print("Resetting stats at the start of ROI.")
    m5.stats.reset()
    print("Switching KVM cores to Timing cores.")
    processor.switch()
    yield False


def handle_workend():
    print("Dumping stats collected at the end of the ROI.")
    m5.stats.dump()

    # Stop the simulation immediately at the end of ROI
    if args.no_stop_after_roi:
        yield False
    else:
        yield True


simulator = Simulator(
    board=board,
    on_exit_event={
        ExitEvent.EXIT: handle_exit_event(),
        ExitEvent.WORKBEGIN: handle_workbegin(),
        ExitEvent.WORKEND: handle_workend(),
    },
)


start_time = time.time()

simulator.run()

end_time = time.time()

print("Simulated time in ROI: " + (str(simulator.get_roi_ticks()[0])))
print(
    "Ran a total of", simulator.get_current_tick() / 1e12, "simulated seconds"
)
print(
    "Total wallclock time: %.2fs, %.2f min"
    % (end_time - start_time, (end_time - start_time) / 60)
)
