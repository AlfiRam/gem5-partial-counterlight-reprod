# Generate a common board configuration across workloads. This also provides
# some additional relevant arguments.

import sys

from m5.objects import (
    BadAddr,
    GlobalInstTracker,
    LocalInstTracker,
    SystemXBar,
)
from m5.util import warn
from m5.util.convert import toMemorySize

from gem5.components.boards.x86_board import X86Board
from gem5.components.cachehierarchies.classic.no_cache import NoCache
from gem5.components.cachehierarchies.classic.private_l1_private_l2_shared_l3_cache_hierarchy import (
    PrivateL1PrivateL2SharedL3CacheHierarchy,
)
from gem5.components.cachehierarchies.classic.private_l1_private_l2_shared_l3_cache_hierarchy_integrity_verifier import (
    PrivateL1PrivateL2SharedL3CacheHierarchyIntegrityVerifier,
)
from gem5.components.memory.mtree.TimingBmt import TimingBmt
from gem5.components.memory.mtree.TimingTree import TimingTree
from gem5.components.memory.single_channel import DIMM_DDR5_4400
from gem5.components.processors.cpu_types import CPUTypes
from gem5.components.processors.simple_processor import SimpleProcessor
from gem5.components.processors.simple_switchable_processor import (
    SimpleSwitchableProcessor,
)
from gem5.isas import ISA
from gem5.utils.requires import requires


def add_arguments(parser):
    # CPU Configuration
    parser.add_argument(
        "--cores",
        type=int,
        required=False,
        help="Number of CPU cores to simulate.",
        default=2,
    )

    parser.add_argument(
        "--inst-tracking",
        action="store_true",
        required=False,
        help="Add instruction tracking functionality.",
    )

    parser.add_argument(
        "--ff-insts",
        type=int,
        required="--inst-tracking" in sys.argv,
        help="Specify number of instructions to fast-forward. This may have issues if the workload is shorter than the number of instructions specified. Only applies if --inst-tracking is used.",
        default=1_000_000_000,
    )

    parser.add_argument(
        "--exec-insts",
        type=int,
        required="--inst-tracking" in sys.argv,
        help="Specify number of instructions to execute. This may have issues if the workload is shorter than the number of instructions specified. Only applies if --inst-tracking is used.",
        default=500_000_000,
    )

    parser.add_argument(
        "--no-cache",
        action="store_true",
        required=False,
        help="Use no cache.",
    )

    parser.add_argument(
        "--unified-l1-cache",
        action="store_true",
        required=False,
        help="Use a unified I/D L1 cache.",
    )

    parser.add_argument(
        "--l2-size",
        type=str,
        required=False,
        help="Size of L2 cache.",
        default="2MiB",
    )

    parser.add_argument(
        "--l2-assoc",
        type=int,
        required=False,
        help="Associativity of L2 cache.",
        default=16,
    )

    parser.add_argument(
        "--l3-size",
        type=str,
        required=False,
        help="Size of L3 cache.",
        default="16MiB",
    )

    parser.add_argument(
        "--l3-assoc",
        type=int,
        required=False,
        help="Associativity of L3 cache.",
        default=32,
    )

    # Memory sizes
    parser.add_argument(
        "--dram-size",
        type=str,
        required=True,
        help="Total size of DRAM.",
    )

    parser.add_argument(
        "--dram-os-size",
        type=str,
        required=False,
        help="Total OS-visible size of DRAM. Overrides any auto-calculated values.",
    )

    # Integrity verification
    parser.add_argument(
        "--use-integrity-verifier",
        action="store_true",
        help="Add an 'integrity verifier' component to add integrity management behavior.",
    )

    parser.add_argument(
        "--integrity-tree-type",
        type=str,
        required=False,
        default="TimingBmt",
        choices=[
            "TimingTree",
            "TimingBmt",
            "None",
        ],
    )

    parser.add_argument(
        "--integrity-tree-arity",
        type=int,
        required=False,
        default=8,
    )

    parser.add_argument(
        "--kvm-only",
        action="store_true",
        help="Use KVM cores exclusively.",
    )

    # Simulation modeling
    parser.add_argument(
        "--timing-from-start",
        action="store_true",
        help="Instead of switching from KVM cores to timing cores when reaching the POI, use timing cores starting at boot.",
    )

    parser.add_argument(
        "--atomic-from-start",
        action="store_true",
        help="Switch from Atomic cores to timing cores when reaching the POI.",
    )

    # Integrity metadata cache
    parser.add_argument(
        "--metadata-cache-type",
        type=str,
        required=False,
        default="PartitionedMetadataCache",
        choices=[
            "MetadataCache",
            "PartitionedMetadataCache",
        ],
    )

    parser.add_argument(
        "--metadata-cache-size",
        type=int,
        required=False,
        help="Number of entries in the (unified) metadata cache, if applicable.",
        default=2048,
    )

    parser.add_argument(
        "--metadata-cache-size-tree-nodes",
        type=int,
        required=False,
        help="Number of tree node entries in the (split) metadata cache, if applicable.",
        default=2048,
    )

    parser.add_argument(
        "--metadata-cache-size-counter-nodes",
        type=int,
        required=False,
        help="Number of counter node entries in the (split) metadata cache, if applicable.",
        default=2048,
    )

    parser.add_argument(
        "--metadata-cache-size-mac-nodes",
        type=int,
        required=False,
        help="Number of MAC node entries in the (split) metadata cache, if applicable.",
        default=2048,
    )

    parser.add_argument(
        "--metadata-cache-assoc",
        type=int,
        required=False,
        help="Associativity of metadata cache.",
        default=16,
    )

    parser.add_argument(
        "--unified-upstream-cache",
        action="store_true",
        required=False,
        help="Enable using the LLC as a metadata cache.",
    )

    parser.add_argument(
        "--enable-partition-manager",
        action="store_true",
        required=False,
        help="Enable dynamic partitioning of data.",
    )

    parser.add_argument(
        "--main-memory-type",
        type=str,
        help="Type of memory used as primary memory. (Starting at address 0.)",
        default="DRAM",
        choices=[
            "DRAM",
        ],
    )

    parser.add_argument(
        "--no-apps-on-secondary-memory",
        action="store_true",
        help="Disable the use of secondary memory for application/OS data.",
    )

    parser.add_argument(
        "--use-ncx",
        action="store_true",
        help="Use noncoherent xbar structure.",
    )

    return parser


def create_board(args):
    # This simulation requires X86 simulation
    requires(
        isa_required=ISA.X86,
    )

    extras = {}

    baseline_os_size = "256MiB"

    tree_classes = {
        "TimingTree": TimingTree,
        "TimingBmt": TimingBmt,
    }

    if args.use_integrity_verifier:
        # DRAM holds both application/OS data and integrity data. Its
        # OS-visible size shrinks by the Merkle tree footprint.
        min_variable_memory = (
            baseline_os_size
            if args.dram_os_size is None
            else args.dram_os_size
        )
        max_variable_memory = (
            "0B" if args.dram_os_size is None else args.dram_os_size
        )

        tree_class = tree_classes[args.integrity_tree_type]

        dram_os_size, _static_os_size = (
            tree_class.determine_max_protected_size(
                min_local_size=toMemorySize(min_variable_memory),
                max_local_size=toMemorySize(max_variable_memory),
                total_local_size=toMemorySize(args.dram_size),
                total_remote_size=0,
                arity=args.integrity_tree_arity,
            )
        )
    else:
        dram_os_size = toMemorySize(args.dram_size)

    print(f"Computed DRAM OS Size: {dram_os_size}")

    if args.dram_os_size:
        dram_os_size = toMemorySize(args.dram_os_size)
        print(f"Overriding DRAM OS Size to {dram_os_size}")

    # DRAM
    if toMemorySize(args.dram_size) > 0:
        memory = []

        if toMemorySize(args.dram_size) <= toMemorySize("3GiB"):
            memory.append(
                DIMM_DDR5_4400(size=args.dram_size, os_size=f"{dram_os_size}B")
            )
        else:
            warn(
                f"Physical memory size specified is {args.dram_size} which "
                "is greater than 3GiB. Twice the number of memory "
                "controllers will be created."
            )
            if dram_os_size <= toMemorySize("3GiB"):
                first_dram_os_size = dram_os_size
                remaining_dram_os_size = 0
            else:
                first_dram_os_size = toMemorySize("3GiB")
                remaining_dram_os_size = dram_os_size - toMemorySize("3GiB")
            memory.append(
                DIMM_DDR5_4400(size="3GiB", os_size=f"{first_dram_os_size}B")
            )

            remaining_dram_size = toMemorySize(args.dram_size) - toMemorySize(
                "3GiB"
            )
            memory.append(
                DIMM_DDR5_4400(
                    size=f"{remaining_dram_size}B",
                    os_size=f"{remaining_dram_os_size}B",
                )
            )
    else:
        memory = []

    membus = SystemXBar(width=64)
    membus.badaddr_responder = BadAddr()
    membus.default = membus.badaddr_responder.pio

    # Cache
    if args.use_integrity_verifier:
        cache_hierarchy = PrivateL1PrivateL2SharedL3CacheHierarchyIntegrityVerifier(
            l1d_size="32KiB",
            l1d_assoc=8,
            l1i_size="32KiB",
            l1i_assoc=8,
            l2_size=args.l2_size,
            l2_assoc=args.l2_assoc,
            l3_size=args.l3_size,
            l3_assoc=args.l3_assoc,
            unified_l1_cache=args.unified_l1_cache,
            membus=membus,
            metadata_cache_type=args.metadata_cache_type,
            metadata_cache_size=args.metadata_cache_size,
            metadata_cache_size_tree_nodes=args.metadata_cache_size_tree_nodes,
            metadata_cache_size_counter_nodes=args.metadata_cache_size_counter_nodes,
            metadata_cache_size_mac_nodes=args.metadata_cache_size_mac_nodes,
            metadata_cache_assoc=args.metadata_cache_assoc,
            unified_upstream_cache=args.unified_upstream_cache,
            enable_partition_manager=args.enable_partition_manager,
            integrity_tree_type=args.integrity_tree_type,
            integrity_tree_arity=args.integrity_tree_arity,
        )
    elif args.no_cache:
        cache_hierarchy = NoCache(
            membus=membus,
        )
    else:
        cache_hierarchy = PrivateL1PrivateL2SharedL3CacheHierarchy(
            l1d_size="32KiB",
            l1d_assoc=8,
            l1i_size="32KiB",
            l1i_assoc=8,
            l2_size=args.l2_size,
            l2_assoc=args.l2_assoc,
            l3_size=args.l3_size,
            l3_assoc=args.l3_assoc,
            unified_l1_cache=args.unified_l1_cache,
            membus=membus,
        )

    if args.timing_from_start:
        processor = SimpleProcessor(
            cpu_type=CPUTypes.TIMING, isa=ISA.X86, num_cores=args.cores
        )
        if args.inst_tracking:
            print(
                "Note: Instruction tracking is enabled, but this does nothing in this configuration."
            )
    elif args.atomic_from_start:
        processor = SimpleSwitchableProcessor(
            starting_core_type=CPUTypes.ATOMIC,
            switch_core_type=CPUTypes.TIMING,
            isa=ISA.X86,
            num_cores=args.cores,
        )
        if args.inst_tracking:
            print(
                "Note: Instruction tracking is enabled, but this does nothing in this configuration."
            )
    else:
        # Boot under KVM, switch to Timing via the config's exit handler.
        requires(
            kvm_required=True,
        )
        processor = SimpleSwitchableProcessor(
            starting_core_type=CPUTypes.KVM,
            switch_core_type=CPUTypes.TIMING,
            isa=ISA.X86,
            num_cores=args.cores,
        )
        if args.inst_tracking:
            global_inst_tracker = GlobalInstTracker(
                inst_thresholds=[],
                # Hack to allow this to work with KVM and
                # SimpleSwitchableProcessor
                use_approximate_exit=True,
            )
            extras["global_inst_tracker"] = global_inst_tracker

            all_trackers = []
            for core in processor._switchable_cores[processor._switch_key]:
                tracker = LocalInstTracker(
                    global_inst_tracker=global_inst_tracker,
                    start_listening=False,
                )
                all_trackers.append(tracker)
                core.core.probeListener = tracker
            extras["all_trackers"] = all_trackers

        if not args.inst_tracking:
            print("Disabling perf for KVM cores.")
            for proc in processor.start:
                proc.core.usePerf = False
        else:
            print(
                "Note: Instruction tracking with KVM cores requires perf to be set up. Assuming perf is working as expected."
            )

    board = X86Board(
        clk_freq="3GHz",
        processor=processor,
        memory=memory,
        cache_hierarchy=cache_hierarchy,
    )

    return board, processor, extras
