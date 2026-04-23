"""
Integrity-verifier demo: boots parsec.img under KVM, switches to Timing
before running an LLC-miss-heavy pointer-chase benchmark with the
integrity verifier in-path.

Canonical invocation:

    ./build/X86/gem5.opt \\
        --outdir=m5out-integrity-stride \\
        configs/integrity_verifier/basic-demo.py

Flow:
  1. KVM cores boot parsec.img.
  2. parsec.img's init writes readfile to script.sh and executes it.
  3. Script's first `m5 exit` signals boot-done. Handler resets stats and
     switches KVM -> Timing. The switch MUST happen here (not WORKBEGIN):
     memory_stride_access calls m5_reset_stats / m5_dump_stats directly
     from user-space, and those magic opcodes fault under KVM.
  4. /home/cxl_benchmark/memory_stride_access runs under Timing. It
     internally invokes m5_reset_stats at ROI start and m5_dump_stats at
     ROI end; gem5 handles those without a Python handler.
  5. Script's second `m5 exit` terminates the simulation.
"""

import argparse
import os
import time
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
    description="Integrity-verifier ptr-chase demo."
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
cli_args = parser.parse_args()

args = SimpleNamespace(
    cores=1,
    inst_tracking=False,
    ff_insts=1_000_000_000,  # unused in this config
    exec_insts=500_000_000,  # unused in this config
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

# Shell script sourced by parsec.img's init (m5 readfile > script.sh;
# ./script.sh; m5 exit). Boot-done `m5 exit` first, then the pointer-chase
# benchmark runs under Timing. The trailing `m5 exit` drives termination.
command = (
    "m5 exit;"
    + "m5 resetstats;"
    + "echo '=== running pr ===';"
    + "/home/gapbs/pr -g 15 -n 1 -i 10;"
    + "m5 exit;"
)

board.set_kernel_disk_workload(
    kernel=KernelResource(local_path=str(_FS_FILES / "vmlinux_20240920")),
    disk_image=DiskImageResource(local_path=str(_FS_FILES / "parsec.img")),
    # parsec.img's root is on the first partition, so override explicitly —
    # otherwise the kernel panics mounting hda.
    disk_device="/dev/hda1",
    readfile_contents=command,
)


roi_start_tick = 0


def handle_exit_event():
    # memory_stride_access calls m5_reset_stats / m5_dump_stats directly from
    # user-space; those are magic opcodes that fault under KVM. We must be in
    # Timing before the benchmark runs, so the switch happens here — not on
    # WORKBEGIN (the binary doesn't fire those).
    print(
        "Caught first exit event: boot done. Resetting stats and switching KVM -> Timing."
    )
    global roi_start_tick
    roi_start_tick = simulator.get_current_tick()
    m5.stats.reset()
    if not args.kvm_only:
        processor.switch()
    yield False

    print("Caught second exit event: post-workload terminate.")
    yield True


simulator = Simulator(
    board=board,
    on_exit_event={
        ExitEvent.EXIT: handle_exit_event(),
    },
)

simulator.run()
