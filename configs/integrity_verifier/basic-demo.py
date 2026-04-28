"""
Integrity-verifier demo: boots gapbs.img under KVM, fast-forwards a fixed
number of retired instructions via KVM+perf, then measures a fixed-length
Timing window using the GlobalInstTracker.

Canonical invocation:

    ./build/X86/gem5.opt \\
        --outdir=m5out-test-cl-bfs19 \\
        configs/integrity_verifier/basic-demo.py --workload bfs

Flow:
  1. KVM cores boot gapbs.img.
  2. /home/gem5/runscript.sh exec's the chosen GAPBS binary at scale 22
     (./<workload> -g 22 -n 20). Scale 22 generates ~600 MB of working
     set (~37.5x the 16 MiB L3, matched by SimpleNamespace.l3_size
     above) to drive strong DRAM pressure on the integrity-verifier
     path. `-n 20` matches the GAPBS reference default for these
     benchmarks (Jerrett confirmed); MAX_INSTS terminates the sim
     before all 20 trials run.
  3. Binary calls m5_work_begin -> WORKBEGIN handler arms KVM
     max_insts_any_thread for `ff_insts` more retired instructions, then
     yields forever (absorbs subsequent per-trial WORKBEGINs so they
     don't fall through to the stdlib default reset_stats_generator
     that would silently reset our FF window).
  4. After ff_insts retired in KVM -> MAX_INSTS first fires -> dump FF
     stats, reset, switch to Timing, arm GlobalInstTracker for
     `exec_insts` more retired instructions.
  5. Per-trial WORKEND firings during the Timing window fall through to
     the stdlib default dump_stats_generator, producing clean per-trial
     stats snapshots in the Timing region.
  6. After exec_insts retired in Timing -> MAX_INSTS second fires ->
     dump final stats and terminate.

Handler also registered for safety:
  * EXIT: safety-net terminator. Fires if the workload completes before
    ff_insts+exec_insts is reached (runscript's trailing `m5 exit`).
"""

import argparse
import os
from pathlib import Path
from types import SimpleNamespace

from create_board import create_board

import m5

from gem5.resources.resource import (
    DiskImageResource,
    KernelResource,
)
from gem5.simulate.exit_event import ExitEvent
from gem5.simulate.simulator import Simulator

parser = argparse.ArgumentParser(
    description="Integrity-verifier GAPBS demo."
)
parser.add_argument(
    "--read-path-mode",
    choices=[
        "FullBmt",
        "BmtStripped",
        "CounterLight",
        "CounterLightBmt",
        "CounterLightMacBmt",
    ],
    default="FullBmt",
    help="Integrity verifier read-path mode. Default FullBmt.",
)
parser.add_argument(
    "--workload",
    choices=["bfs", "sssp", "pr"],
    default="bfs",
    help="GAPBS workload to run. Default bfs.",
)
parser.add_argument(
    "--ff-insts",
    type=int,
    default=100_000_000,
    help="KVM fast-forward instruction count.",
)
parser.add_argument(
    "--exec-insts",
    type=int,
    default=200_000_000,
    help="Timing-mode measurement window instruction count.",
)
cli_args = parser.parse_args()

args = SimpleNamespace(
    cores=1,
    inst_tracking=True,
    ff_insts=cli_args.ff_insts,
    exec_insts=cli_args.exec_insts,
    no_cache=False,
    unified_l1_cache=False,
    l2_size="2MiB",
    l2_assoc=16,
    l3_size="16MiB",
    l3_assoc=32,
    dram_size="3GiB",
    dram_os_size=None,
    use_integrity_verifier=True,
    integrity_tree_type="TimingBmt",
    integrity_tree_arity=8,
    kvm_only=False,
    timing_from_start=False,
    atomic_from_start=False,
    metadata_cache_type="PartitionedMetadataCache",
    # 3072 / (assoc=8 * 3 partitions) = 128 sets. 2048 gives 85.3 sets
    # and trips the power-of-2 assertion in BaseSetAssoc.
    metadata_cache_size=3072,
    metadata_cache_size_tree_nodes=2048,
    metadata_cache_size_counter_nodes=2048,
    metadata_cache_size_mac_nodes=2048,
    metadata_cache_assoc=8,
    unified_upstream_cache=False,
    enable_partition_manager=False,
)

board, processor, extras = create_board(args)
global_inst_tracker = extras.get("global_inst_tracker")
all_trackers = extras.get("all_trackers")

# The hierarchy's `verifier` SimObject is only created inside
# `incorporate_cache()`, which fires from `board._connect_things()` during
# `simulator._instantiate()`. Wrap `_connect_things` so the override lands
# after the verifier exists but before `m5.instantiate()` freezes params.
_orig_connect_things = board._connect_things


def _connect_things_with_read_path_override():
    _orig_connect_things()
    board.get_cache_hierarchy().verifier.read_path_mode = (
        cli_args.read_path_mode
    )
    print(
        f"[basic-demo] IntegrityVerifier read_path_mode = "
        f"{cli_args.read_path_mode}"
    )


board._connect_things = _connect_things_with_read_path_override

_FS_FILES = Path(
    os.environ.get("CXL_HAMMER_FS_FILES", "/home/malfiram/CXL-Hammer/fs_files")
)

# gapbs.img's /home/gem5/runscript.sh reads `workload arg size` then runs
# `./$workload $arg $size`. `read` assigns the trailing words to the last
# var, and unquoted `$size` re-splits in the shell — so passing
# "<workload> -g 22 -n 20" yields `./<workload> -g 22 -n 20`. Scale 22
# generates ~4M vertices / ~64M edges / ~600 MB working set, which is
# ~37.5x the 16 MiB L3 (matched by SimpleNamespace.l3_size above) and
# drives strong DRAM pressure on the integrity-verifier path while
# leaving comfortable headroom under the 3 GiB gem5 DRAM limit. `-n 20`
# matches the GAPBS reference default for these benchmarks (Jerrett
# confirmed); MAX_INSTS terminates the sim once the FF+Timing window
# completes, so trials beyond that are never reached and cost no extra
# wall-clock time. Multi-trial WORKBEGIN noise from the trials that DO
# run during the window is absorbed by handle_workbegin's forever-yield.
# Per-trial WORKEND firings fall through to the stdlib default
# dump_stats_generator, giving clean per-trial Timing-region snapshots.
command = f"{cli_args.workload} -g 22 -n 20"

board.set_kernel_disk_workload(
    kernel=KernelResource(local_path=str(_FS_FILES / "vmlinux-4.19.83")),
    disk_image=DiskImageResource(local_path=str(_FS_FILES / "gapbs.img")),
    # gapbs.img's root is on the first partition, so override explicitly —
    # otherwise the kernel panics mounting hda.
    disk_device="/dev/hda1",
    readfile_contents=command,
)


def handle_workbegin():
    # WORKBEGIN signals graph build is done, algorithm about to start.
    # Arm KVM's max_insts to fast-forward ff_insts more retired insts
    # before switching to Timing. Do NOT switch yet. Yield forever after
    # arming so per-trial WORKBEGINs from `-n 20` (or any spurious ones)
    # don't fall through to the stdlib default reset_stats_generator
    # that would silently reset the FF window.
    print(
        f"Caught WORKBEGIN. Arming KVM FF for {cli_args.ff_insts} insts."
    )
    for core in processor._switchable_cores[processor._start_key]:
        core._set_inst_stop_any_thread(
            cli_args.ff_insts, simulator._instantiated
        )
    while True:
        yield False


def handle_exit():
    # Safety net: if the workload completes before ff_insts+exec_insts is
    # reached, the runscript's trailing `m5 exit` fires and we terminate
    # here instead of hanging.
    print("Caught EXIT: workload completed before MAX_INSTS. Terminating.")
    yield True


def handle_max_insts():
    # First fire: KVM FF complete. Dump FF-region stats, reset, switch to
    # Timing, then arm the GlobalInstTracker for the exec_insts Timing
    # window.
    print("MAX_INSTS first fire: KVM FF done.")
    m5.stats.dump()
    m5.stats.reset()
    for core in processor._switchable_cores[processor._start_key]:
        core.core.max_insts_any_thread = 0
    processor.switch()
    print(
        f"Arming GlobalInstTracker for {cli_args.exec_insts} Timing insts."
    )
    global_inst_tracker.resetCounter()
    global_inst_tracker.addThreshold(cli_args.exec_insts)
    for tracker in all_trackers:
        tracker.startListening()
    yield False

    # Second fire: Timing window complete. Dump and terminate.
    print("MAX_INSTS second fire: Timing window done.")
    m5.stats.dump()
    yield True


simulator = Simulator(
    board=board,
    on_exit_event={
        ExitEvent.WORKBEGIN: handle_workbegin(),
        ExitEvent.MAX_INSTS: handle_max_insts(),
        ExitEvent.EXIT: handle_exit(),
    },
)

simulator.run()
