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
Script to run SPEC 2017 benchmarks with gem5.
The script expects a benchmark program name and the simulation
size.

This script will count the total number of instructions executed
in the ROI. It also tracks how much wallclock and simulated time.

Usage:
------

```
scons build/X86/gem5.opt
./build/X86/gem5.opt <script> \
    --benchmark <benchmark_name> \
    --size <simulation_size>
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

# Following are the list of benchmark programs for SPEC2017.
benchmark_choices = [
    "500.perlbench_r",
    "502.gcc_r",  # Validated
    "503.bwaves_r",  # peak is not built
    "505.mcf_r",
    "507.cactusBSSN_r",
    "508.namd_r",
    "510.parest_r",
    "511.povray_r",
    "519.lbm_r",
    "520.omnetpp_r",
    "521.wrf_r",
    "523.xalancbmk_r",
    "525.x264_r",
    "527.cam4_r",
    "531.deepsjeng_r",
    "538.imagick_r",
    "541.leela_r",
    "544.nab_r",
    "548.exchange2_r",
    "549.fotonik3d_r",
    "554.roms_r",
    "557.xz_r",
    "600.perlbench_s",
    "602.gcc_s",
    "603.bwaves_s",
    "605.mcf_s",
    "607.cactusBSSN_s",
    "608.namd_s",
    "610.parest_s",
    "611.povray_s",
    "619.lbm_s",
    "620.omnetpp_s",
    "621.wrf_s",
    "623.xalancbmk_s",
    "625.x264_s",
    "627.cam4_s",
    "631.deepsjeng_s",
    "638.imagick_s",
    "641.leela_s",
    "644.nab_s",
    "648.exchange2_s",
    "649.fotonik3d_s",
    "654.roms_s",
    "996.specrand_fs",
    "997.specrand_fr",
    "998.specrand_is",
    "999.specrand_ir",
]

# Following are the input sizes.
size_choices = [
    "test",
    "train",
    "ref",
]


# Argument parsing.
parser = argparse.ArgumentParser(
    description="SPEC 2017 benchmark runner for gem5."
)
add_arguments(parser)

parser.add_argument(
    "--benchmark",
    type=str,
    required=True,
    help="Input the benchmark program to execute.",
    choices=benchmark_choices,
)

parser.add_argument(
    "--size",
    type=str,
    required=True,
    help="Simulation size the benchmark program.",
    choices=size_choices,
)

parser.add_argument(
    "--app-on-device",
    type=str,
    required=False,
    help="Select which memory device the application should exist on. Requires special kernel support.",
    default="Auto",
    choices=[
        "DRAM",
        "CXL",
        "Auto",  # Use usual OS memory allocation
    ],
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
    default="x86-spec2017-ubuntu-22-04",
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

board, processor, extras = create_board(args)

if "global_inst_tracker" in extras.keys():
    global_inst_tracker = extras.get("global_inst_tracker")
else:
    global_inst_tracker = None

if "all_trackers" in extras.keys():
    all_trackers = extras.get("all_trackers")
else:
    all_trackers = None


match args.app_on_device:
    case "DRAM":
        numa_cmd = "numactl --membind=0 --cpunodebind=0 "
    case "CXL":
        numa_cmd = "numactl --membind=1 --cpunodebind=0 "
    case _:
        numa_cmd = ""


# This is the command to run after the system has booted. The first `m5 exit`
# written here (which is really the third exit in total from the start of
# boot) will signal that we have finished booting. During the simulation or
# after it ends, you may inspect `m5out/system.pc.com_1.device` to see the
# emulated echo output.
command = (
    "m5 exit;"  # Third exit event
    + "cd spec2017;"
    + "source shrc;"
    + "numactl -H;"
    + f'{numa_cmd}runcpu --size {args.size} --iterations 1 --config myconfig.x86.cfg --define gcc_dir="/usr" --noreportable --nobuild {args.benchmark};'
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

roi_start_tick = 0


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
    print("Caught workbegin signal.")

    # Track the start tick to find how long inside the ROI was simulated.
    global roi_start_tick
    roi_start_tick = simulator.get_current_tick()

    print("Resetting stats at the start of ROI.")
    m5.stats.reset()

    # If we're tracking instruction counts, we will skip/fast-forward some number
    # of instructions using the starting cores. Following this, later, we will
    # execute a specified number of instructions on the other core type.
    if global_inst_tracker is not None:
        # For sanity checking, we will take a note of how many instructions have been
        # executed. Once we reach the target fast-forward instruction count, we will
        # get the new number of instructions executed to make sure what we wanted
        # actually happened. For some reason, sometimes KVM cores will stop at a much
        # earlier point than when they really should.
        global roi_start_insts
        roi_start_insts = processor._switchable_cores[processor._start_key][
            0
        ].core.totalInsts()
        print(
            f"Number of instructions executed up to this point: {roi_start_insts}"
        )

        # Specify number of instructions to fast-forward by.
        global ff_inst
        ff_inst = args.ff_insts
        print(f"Will skip {ff_inst} instructions of the workload.")

        # Apply the instruction limit to the starting cores.
        for core in processor._switchable_cores[processor._start_key]:
            core._set_inst_stop_any_thread(ff_inst, simulator._instantiated)
    elif not args.kvm_only:
        # Default behavior: Switch cores on ROI start.
        print("Switching KVM cores to Timing cores.")
        processor.switch()

    yield False


def handle_workend():
    print("Caught workend signal.")

    # We either collect stats at the end of ROI, or after a certain
    # number of instructions, but not both.
    if global_inst_tracker is None:
        print("Dumping stats collected at the end of the ROI.")
        m5.stats.dump()
        m5.stats.reset()
    else:
        # We were probably expecting to stop after max instructions,
        # but the workend signal came first. Consider this an issue.
        print("Unexpected workend before instruction count reached.")
        exit(2)

    # Stop the simulation immediately at the end of ROI
    if args.no_stop_after_roi:
        yield False
    else:
        yield True


# If this function gets called, we are assuming we are counting
# instructions.
def handle_max_insts():
    print("Handling max instructions reached (First time).")

    # Find the number of instructions executed and sanity check that
    # the amount that we wanted to fast-forward was actually how much
    # was fast forwarded.
    roi_ff_insts = processor._switchable_cores[processor._start_key][
        0
    ].core.totalInsts()
    print(f"Number of instructions executed up to this point: {roi_ff_insts}")
    print(f"Instructions fast-forwarded: {roi_ff_insts - roi_start_insts}")
    if roi_ff_insts - roi_start_insts < ff_inst:
        print(
            "The number of instructions fast-forwarded is lower than it should be. Aborting."
        )
        exit(1)

    print("Resetting stats before switching cores.")
    # m5.stats.dump()
    m5.stats.reset()

    print("Unsetting instruction threshold for start cores.")
    for core in processor._switchable_cores[processor._start_key]:
        # core._set_inst_stop_any_thread(0, True)
        core.core.max_insts_any_thread = 0
    # print(f"Global instruction tracker count: {global_inst_tracker.getCounter()}")
    # print(f"Current thresholds: {global_inst_tracker.getThresholds()}")

    print("Switching KVM to Timing cores.")
    processor.switch()

    # If we're counting instructions, now we will specify a certain number
    # of instructions to run in the Timing cores. The way this count is added
    # is different with Timing cores than with KVM. The method available with
    # Timing cores is more flexible.
    if global_inst_tracker is not None:
        global_inst_tracker.resetCounter()
        run_insts = args.exec_insts
        print(f"Will run {run_insts} instructions.")
        global_inst_tracker.addThreshold(run_insts)
        for tracker in all_trackers:
            tracker.startListening()
    yield False

    print("Handling max instructions reached (Second time).")
    print("Dumping stats after target instruction count reached.")
    m5.stats.dump()

    print(
        f"Global instruction tracker count: {global_inst_tracker.getCounter()}"
    )
    # print(f"Current thresholds: {global_inst_tracker.getThresholds()}")

    # This is buggy to switch back to KVM right now.
    # if args.no_stop_after_roi:
    #     print("Continuing simulation based on user preference to continue.")
    #     # print("Switching Timing to KVM cores to skip the rest of the run.")
    #     # processor.switch()
    #     yield False
    # else:
    print("Stopping simulation.")
    yield True


def handle_interrupt():
    print("Interrupted by user. Stopping.")
    exit(1)
    yield True


simulator = Simulator(
    board=board,
    on_exit_event={
        ExitEvent.EXIT: handle_exit_event(),
        ExitEvent.WORKBEGIN: handle_workbegin(),
        ExitEvent.WORKEND: handle_workend(),
        ExitEvent.MAX_INSTS: handle_max_insts(),
        ExitEvent.USER_INTERRUPT: handle_interrupt(),
    },
)

start_time = time.time()

simulator.run()

end_time = time.time()

try:
    print(
        "Simulated time in ROI: %.2f seconds"
        % (simulator.get_roi_ticks()[0] / 1e12)
    )
except IndexError:
    print("ROI ticks not available. Maybe stopping before end of ROI?")
    print(
        "Simulated time from ROI to end: %.2f seconds"
        % ((simulator.get_current_tick() - roi_start_tick) / 1e12)
    )

print(
    "Ran a total of %.2f simulated seconds"
    % (simulator.get_current_tick() / 1e12)
)
duration = end_time - start_time
print(
    "Total wallclock time: %.2fhr / %.2fmin / %.2fs"
    % (duration / 3600, duration / 60, duration)
)
